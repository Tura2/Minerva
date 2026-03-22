"""
Mean Reversion Bounce Workflow

Sequential node pipeline (LangGraph-style) — mirrors swing_trade.py structure.
Hunts for oversold bounces in confirmed long-term uptrends.

Node order:
  1. fetch_data       — yfinance OHLC + daily indicators + MR-specific indicators
  2. fetch_rs         — relative strength vs benchmark + universe rank
  3. pre_screen       — mean-reversion gate (7 checks: oversold dip in intact uptrend)
  4. fetch_breadth    — market breadth context
  5. llm_research     — OpenRouter single call (JSON mode, MR prompt)
  6. compute_sizing   — position calculator + scale-out plan
  7. persist_ticket   — Pydantic validation + DB insert

workflow_type = "mean-reversion-bounce"
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import yfinance as yf
import pandas as pd
from pydantic import ValidationError

from app.config import settings
from app.models.ticket_validator import TicketOutputValidator
from app.services.indicators import (
    compute_indicators,
    compute_mean_reversion_indicators,
    compute_weekly_indicators,
)
from app.services.market_breadth import get_market_breadth
from app.services.openrouter_client import OpenRouterClient
from app.services.position_sizer_service import compute_position_size
from app.services.pre_screen import PreScreenResult, pre_screen_mean_reversion
from app.services.prompts_mean_reversion import MR_SYSTEM_PROMPT, build_mr_research_prompt
from app.services.rs_calculator import compute_rs_indicators, compute_rs_rank_in_universe
from app.services.workflows.swing_trade import PreScreenFailed, WorkflowError

logger = logging.getLogger(__name__)

WORKFLOW_TYPE = "mean-reversion-bounce"


@dataclass
class MeanReversionState:
    """Mutable state passed through workflow nodes."""

    symbol: str
    market: str
    portfolio_size: float
    max_risk_pct: float

    df: Optional[pd.DataFrame] = None
    indicators: Dict[str, Any] = field(default_factory=dict)
    mr_indicators: Dict[str, Any] = field(default_factory=dict)
    weekly_indicators: Dict[str, Any] = field(default_factory=dict)
    rs_indicators: Dict[str, Any] = field(default_factory=dict)
    screen_result: Optional[PreScreenResult] = None
    breadth: Dict[str, Any] = field(default_factory=dict)
    llm_raw: Dict[str, Any] = field(default_factory=dict)
    sizing: Dict[str, Any] = field(default_factory=dict)
    scale_out_plan: List[Dict[str, Any]] = field(default_factory=list)
    ticket_id: Optional[str] = None
    debug_logs: List[Dict[str, Any]] = field(default_factory=list)


def _trace(state: MeanReversionState, node: str, data: Dict[str, Any]) -> None:
    state.debug_logs.append({
        "node": node,
        "ts": datetime.now(timezone.utc).isoformat(),
        **data,
    })


async def execute_mean_reversion(
    symbol: str,
    market: str,
    portfolio_size: float,
    max_risk_pct: float,
    db,
    force_research: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Run the full mean-reversion-bounce workflow and persist the ticket.

    Args:
        symbol:         Ticker (without .TA suffix)
        market:         "US" or "TASE"
        portfolio_size: Account size in local currency
        max_risk_pct:   Max risk per trade as % (e.g. 1.0)
        db:             Supabase client instance
        force_research: Skip pre-screen gate and run LLM anyway
        force_refresh:  Bypass 24h dedup check

    Returns:
        research_ticket row as dict

    Raises:
        PreScreenFailed: if pre-screen fails and force_research=False
        WorkflowError:   on data fetch or LLM errors
    """
    # ── Deduplication: return cached ticket if run within last 24h ────────────
    if not force_refresh:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        dedup_result = (
            db.table("research_tickets")
            .select("*")
            .eq("symbol", symbol.upper())
            .eq("market", market.upper())
            .eq("workflow_type", WORKFLOW_TYPE)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if dedup_result.data:
            cached = dedup_result.data[0]
            logger.info(
                f"[mean_reversion] Dedup hit for {symbol}/{market}: returning ticket {cached.get('id')}"
            )
            return cached

    state = MeanReversionState(
        symbol=symbol,
        market=market,
        portfolio_size=portfolio_size,
        max_risk_pct=max_risk_pct,
    )

    state = await _node_fetch_data(state)
    state = await _node_fetch_rs(state, db)
    state = await _node_pre_screen(state, force_research)
    state = await _node_fetch_breadth(state)
    state = await _node_llm_research(state)
    state = _node_compute_sizing(state)
    ticket = await _node_persist_ticket(state, db)

    return ticket


# ── Nodes ──────────────────────────────────────────────────────────────────────


async def _node_fetch_data(state: MeanReversionState) -> MeanReversionState:
    """Fetch 1-year OHLC + compute daily indicators + MR-specific indicators."""
    yf_symbol = f"{state.symbol}.TA" if state.market.upper() == "TASE" else state.symbol

    logger.info(f"[mean_reversion] Fetching data for {yf_symbol}")
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="1y", interval="1d")
    except Exception as e:
        raise WorkflowError(f"yfinance fetch failed for {yf_symbol}: {e}") from e

    if df.empty:
        raise WorkflowError(f"No data returned for {yf_symbol}")

    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    # TASE prices from yfinance are in agorot (1/100 ILS) — convert to ILS
    if state.market.upper() == "TASE":
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] / 100.0

    state.df = df
    state.indicators = compute_indicators(df)

    if not state.indicators:
        raise WorkflowError(f"Insufficient data to compute indicators for {yf_symbol}")

    # MR-specific indicators (BB, capitulation volume, RSI divergence)
    state.mr_indicators = compute_mean_reversion_indicators(df, state.indicators)
    state.weekly_indicators = compute_weekly_indicators(df)

    logger.info(
        f"[mean_reversion] Data fetched: {len(df)} sessions, "
        f"price={state.indicators.get('price')}, "
        f"rsi={state.indicators.get('rsi14')}, "
        f"bb_pct_b={state.mr_indicators.get('bb_pct_b')}, "
        f"cap_detected={state.mr_indicators.get('capitulation_detected')}, "
        f"rsi_divergence={state.mr_indicators.get('rsi_divergence')}"
    )
    _trace(state, "fetch_data", {
        "sessions": len(df),
        "price": state.indicators.get("price"),
        "ma20": state.indicators.get("ma20"),
        "ma200": state.indicators.get("ma200"),
        "rsi14": state.indicators.get("rsi14"),
        "atr14": state.indicators.get("atr14"),
        "rvol": state.indicators.get("rvol"),
        "bb_pct_b": state.mr_indicators.get("bb_pct_b"),
        "bb_lower": state.mr_indicators.get("bb_lower"),
        "capitulation_detected": state.mr_indicators.get("capitulation_detected"),
        "capitulation_vol_ratio": state.mr_indicators.get("capitulation_vol_ratio"),
        "rsi_divergence": state.mr_indicators.get("rsi_divergence"),
        "weekly_trend": state.weekly_indicators.get("weekly_trend"),
    })
    return state


async def _node_fetch_rs(state: MeanReversionState, db) -> MeanReversionState:
    """Compute Relative Strength vs benchmark + universe rank (non-blocking)."""
    try:
        rs = await compute_rs_indicators(state.symbol, state.market)
        state.rs_indicators = rs

        composite = rs.get("rs_composite")
        if composite is not None and not rs.get("error"):
            try:
                result = db.table("watchlist_items").select("symbol").eq("market", state.market.upper()).execute()
                universe = [row["symbol"] for row in result.data]
                rank_pct = await compute_rs_rank_in_universe(composite, universe, state.market)
                state.rs_indicators["rs_rank_pct"] = rank_pct
            except Exception as rank_err:
                logger.warning(f"[mean_reversion] RS rank failed (non-fatal): {rank_err}")
                state.rs_indicators["rs_rank_pct"] = None

        logger.info(
            f"[mean_reversion] RS: composite={rs.get('rs_composite')}, "
            f"rank={state.rs_indicators.get('rs_rank_pct')}"
        )
    except Exception as e:
        logger.warning(f"[mean_reversion] RS node failed (non-fatal): {e}")
        state.rs_indicators = {"error": str(e)}

    _trace(state, "fetch_rs", {
        "rs_63": state.rs_indicators.get("rs_63"),
        "rs_126": state.rs_indicators.get("rs_126"),
        "rs_189": state.rs_indicators.get("rs_189"),
        "rs_composite": state.rs_indicators.get("rs_composite"),
        "rs_rank_pct": state.rs_indicators.get("rs_rank_pct"),
        "benchmark": state.rs_indicators.get("benchmark_used"),
        "error": state.rs_indicators.get("error"),
    })
    return state


async def _node_pre_screen(state: MeanReversionState, force: bool) -> MeanReversionState:
    """Run deterministic mean-reversion gate (7 checks)."""
    result = pre_screen_mean_reversion(
        symbol=state.symbol,
        market=state.market,
        df=state.df,
        indicators=state.indicators,
    )
    state.screen_result = result
    logger.info(f"[mean_reversion] Pre-screen: {result.summary}")
    _trace(state, "pre_screen", {
        "passed": result.passed,
        "summary": result.summary,
        "checks": result.checks,
        "reasons": result.reasons,
    })

    if not result.passed and not force:
        raise PreScreenFailed(result)

    return state


async def _node_fetch_breadth(state: MeanReversionState) -> MeanReversionState:
    """Fetch market breadth (US: Monty's CSV; TASE: neutral stub)."""
    try:
        state.breadth = get_market_breadth(state.market)
    except Exception as e:
        logger.warning(f"[mean_reversion] Breadth fetch failed: {e}")
        state.breadth = {"available": False, "note": f"Breadth unavailable: {e}", "zone": "Neutral"}
    _trace(state, "fetch_breadth", {
        "available": state.breadth.get("available"),
        "zone": state.breadth.get("zone"),
        "overall_ratio": state.breadth.get("overall_ratio"),
    })
    return state


async def _node_llm_research(state: MeanReversionState) -> MeanReversionState:
    """Call OpenRouter with the MR prompt. Returns structured JSON."""
    prompt = build_mr_research_prompt(
        symbol=state.symbol,
        market=state.market,
        indicators=state.indicators,
        mr_indicators=state.mr_indicators,
        pre_screen_result=state.screen_result,
        breadth=state.breadth,
        portfolio_size=state.portfolio_size,
        max_risk_pct=state.max_risk_pct,
        weekly_indicators=state.weekly_indicators or None,
        rs_indicators=state.rs_indicators or None,
    )

    _trace(state, "llm_research_prompt", {
        "model": settings.research_model,
        "temperature": 0.5,
        "max_tokens": 3500,
        "full_prompt": prompt,
        "system_prompt": MR_SYSTEM_PROMPT,
    })

    client = OpenRouterClient()
    logger.info(f"[mean_reversion] Calling LLM ({settings.research_model}) for {state.symbol}")

    try:
        result = await client.research(
            prompt=prompt,
            system_context=MR_SYSTEM_PROMPT,
            temperature=0.5,
            max_tokens=3500,
        )
    except Exception as e:
        raise WorkflowError(f"LLM research failed: {e}") from e

    required = ["entry_price", "stop_loss", "target", "bullish_probability", "key_triggers"]
    missing = [f for f in required if f not in result]
    if missing:
        raise WorkflowError(
            f"LLM response missing required fields: {missing}. Got: {list(result.keys())}"
        )

    state.llm_raw = result
    logger.info(
        f"[mean_reversion] LLM complete: entry={result.get('entry_price')}, "
        f"stop={result.get('stop_loss')}, target={result.get('target')}, "
        f"prob={result.get('bullish_probability')}"
    )
    _trace(state, "llm_research_response", {
        "entry_price": result.get("entry_price"),
        "stop_loss": result.get("stop_loss"),
        "target": result.get("target"),
        "bullish_probability": result.get("bullish_probability"),
        "risk_reward_ratio": result.get("risk_reward_ratio"),
        "setup_quality": result.get("setup_quality"),
        "chain_of_thought": result.get("chain_of_thought", ""),
        "key_triggers": result.get("key_triggers", []),
        "verdict": (result.get("final_recommendation") or {}).get("verdict"),
        "setup_score": (result.get("synthesized_score") or {}).get("total"),
        "pattern_stage": (result.get("technical_analysis") or {}).get("pattern_stage"),
    })
    return state


def _node_compute_sizing(state: MeanReversionState) -> MeanReversionState:
    """Compute position size from LLM entry/stop prices."""
    llm = state.llm_raw
    entry = float(llm.get("entry_price", 0) or 0)
    stop = float(llm.get("stop_loss", 0) or 0)

    if entry <= 0 or stop <= 0 or stop >= entry:
        logger.warning(f"[mean_reversion] Invalid entry/stop: entry={entry}, stop={stop}")
        state.sizing = {
            "shares": 0,
            "position_value": 0.0,
            "dollar_risk": 0.0,
            "risk_pct_actual": 0.0,
            "error": "Invalid entry/stop prices from LLM",
        }
        return state

    state.sizing = compute_position_size(
        entry_price=entry,
        stop_price=stop,
        account_size=state.portfolio_size,
        risk_pct=state.max_risk_pct,
        market=state.market,
    )
    total_shares = int(state.sizing.get("shares") or 0)
    dollar_risk = float(state.sizing.get("dollar_risk") or 0)
    position_value = float(state.sizing.get("position_value") or 0)

    # Hard cap: no margin
    if position_value > state.portfolio_size and entry > 0:
        total_shares = int(state.portfolio_size / entry)
        position_value = round(total_shares * entry, 2)
        dollar_risk = round(total_shares * (entry - stop), 2)
        state.sizing["shares"] = total_shares
        state.sizing["position_value"] = position_value
        state.sizing["dollar_risk"] = dollar_risk
        state.sizing["risk_pct_actual"] = (
            round(dollar_risk / state.portfolio_size * 100, 2) if state.portfolio_size else 0
        )
        state.sizing["capped_by_portfolio"] = True

    # Build scale-out plan from LLM scale_out_targets
    scale_out_raw = llm.get("scale_out_targets") or []
    scale_out_plan = []
    alloc_map = [(0.40, "T1"), (0.35, "T2"), (0.25, "T3")]
    for i, target_obj in enumerate(scale_out_raw[:3]):
        pct = alloc_map[i][0] if i < len(alloc_map) else 0.34
        shares_at_target = max(1, round(total_shares * pct)) if total_shares > 0 else 0
        t_price = float(target_obj.get("price") or 0)
        r_multiple = (
            round((t_price - entry) / (entry - stop), 2)
            if (entry != stop and t_price > 0) else None
        )
        scale_out_plan.append({
            "label": target_obj.get("label", f"T{i + 1}"),
            "price": t_price,
            "share_pct": int(target_obj.get("share_pct") or round(pct * 100)),
            "shares": shares_at_target,
            "r_multiple": r_multiple,
            "partial_value": round(shares_at_target * t_price, 2) if t_price else None,
        })

    if scale_out_plan:
        state.scale_out_plan = scale_out_plan
        total_expected = sum(p["shares"] * p["price"] for p in scale_out_plan if p.get("price"))
        total_cost = total_shares * entry if total_shares else 0
        state.sizing["expected_gain"] = round(total_expected - total_cost, 2) if total_expected else None
        state.sizing["expected_r"] = (
            round((total_expected - total_cost) / dollar_risk, 2)
            if (dollar_risk and total_expected) else None
        )

    logger.info(
        f"[mean_reversion] Sizing: {total_shares} shares, "
        f"risk={state.sizing.get('dollar_risk')} {state.sizing.get('currency')}, "
        f"scale_out_targets={len(scale_out_plan)}"
    )
    _trace(state, "compute_sizing", {
        "shares": state.sizing.get("shares"),
        "position_value": state.sizing.get("position_value"),
        "dollar_risk": state.sizing.get("dollar_risk"),
        "risk_pct_actual": state.sizing.get("risk_pct_actual"),
        "currency": state.sizing.get("currency"),
        "scale_out_plan": scale_out_plan,
        "expected_r": state.sizing.get("expected_r"),
    })
    return state


async def _node_persist_ticket(state: MeanReversionState, db) -> Dict[str, Any]:
    """Validate final output and write to research_tickets table."""
    llm = state.llm_raw
    sizing = state.sizing
    currency = sizing.get("currency", "USD" if state.market.upper() == "US" else "ILS")

    # ── Output validation ────────────────────────────────────────────────────
    try:
        TicketOutputValidator(
            entry_price=float(llm.get("entry_price") or 0),
            stop_loss=float(llm.get("stop_loss") or 0),
            target=float(llm.get("target") or 0),
            risk_reward_ratio=float(llm.get("risk_reward_ratio") or 0),
            bullish_probability=float(llm.get("bullish_probability") or 0),
            position_size=int(sizing.get("shares") or 0),
            key_triggers=llm.get("key_triggers") or [],
        )
    except ValidationError as e:
        errors = "; ".join(f"{err['loc'][0]}: {err['msg']}" for err in e.errors())
        raise WorkflowError(f"Ticket output validation failed: {errors}") from e

    synthesized_score = llm.get("synthesized_score") or {}
    final_rec = llm.get("final_recommendation") or {}
    tech_analysis = llm.get("technical_analysis") or {}

    setup_score_total = synthesized_score.get("total")
    verdict = final_rec.get("verdict")
    entry_type_raw = tech_analysis.get("entry_type") or llm.get("entry_type")
    # MR uses "current" or "buy_stop"; map "buy_stop" to "breakout" for DB column compatibility
    entry_type = entry_type_raw if entry_type_raw in ("current", "breakout", "buy_stop") else None
    rs_rank_pct = state.rs_indicators.get("rs_rank_pct")

    metadata = {
        # Legacy fields (kept for backward compat / ticket renderer)
        "entry_rationale": llm.get("entry_rationale", ""),
        "stop_rationale": llm.get("stop_rationale", ""),
        "target_rationale": llm.get("target_rationale", ""),
        "risk_reward_ratio": llm.get("risk_reward_ratio"),
        "setup_quality": llm.get("setup_quality", "C"),
        "chain_of_thought": llm.get("chain_of_thought", ""),
        "trend_context": llm.get("trend_context", ""),
        "volume_context": llm.get("volume_context", ""),
        "market_breadth_context": llm.get("market_breadth_context", ""),
        "caveats": llm.get("caveats", []),
        # Rich analytical fields (same structure as swing — frontend renders unchanged)
        "technical_analysis": tech_analysis,
        "scale_out_targets": llm.get("scale_out_targets", []),
        "scale_out_plan": state.scale_out_plan,
        "scenarios": llm.get("scenarios", []),
        "synthesized_score": synthesized_score,
        "execution_checklist": llm.get("execution_checklist", {}),
        "final_recommendation": final_rec,
        # MR-specific indicators (for future drill-down / audit)
        "mr_indicators": state.mr_indicators,
        # Context
        "rs_indicators": {
            k: v for k, v in state.rs_indicators.items() if k not in ("error",)
        },
        "pre_screen": {
            "passed": state.screen_result.passed if state.screen_result else None,
            "checks": state.screen_result.checks if state.screen_result else {},
            "vcp": state.screen_result.vcp if state.screen_result else {},
        },
        "breadth_zone": state.breadth.get("zone"),
        "breadth_score": state.breadth.get("composite_score"),
        "weekly_trend": state.weekly_indicators.get("weekly_trend"),
        "research_model": settings.research_model,
        "portfolio_size": state.portfolio_size,
        "max_risk_pct": state.max_risk_pct,
        "sizing_detail": sizing,
        "debug_logs": state.debug_logs,
    }

    # DB column constraint: entry_type accepts "current" | "breakout"; map buy_stop → breakout
    db_entry_type = "breakout" if entry_type == "buy_stop" else entry_type

    row = {
        "symbol": state.symbol.upper(),
        "market": state.market.upper(),
        "workflow_type": WORKFLOW_TYPE,
        "entry_price": float(llm.get("entry_price") or 0),
        "stop_loss": float(llm.get("stop_loss") or 0),
        "target": float(llm.get("target") or 0),
        "position_size": sizing.get("shares", 0),
        "max_risk": sizing.get("dollar_risk", 0),
        "currency": currency,
        "bullish_probability": float(llm.get("bullish_probability") or 0),
        "key_triggers": llm.get("key_triggers", []),
        "status": "pending",
        "rs_rank_pct": rs_rank_pct,
        "setup_score": int(setup_score_total) if setup_score_total is not None else None,
        "verdict": verdict if verdict in ("Strong Buy", "Buy", "Watch", "Avoid") else None,
        "entry_type": db_entry_type if db_entry_type in ("current", "breakout") else None,
        "metadata": metadata,
    }

    result = db.table("research_tickets").insert(row).execute()
    if not result.data:
        raise WorkflowError("DB insert returned no data")

    ticket = result.data[0]
    logger.info(f"[mean_reversion] Ticket persisted: {ticket.get('id')}")
    return ticket
