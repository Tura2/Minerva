# backend/app/services/workflows/support_bounce.py
"""
Support Bounce Workflow

Node pipeline:
  1. fetch_data      — yfinance OHLC + indicators (same as swing)
  2. fetch_rs        — relative strength + universe rank (same as swing)
  3. detect_sr       — S/R zone detection via sr_detector
  4. pre_screen_sb   — support-bounce specific gate
  5. fetch_breadth   — market breadth context (same as swing)
  6. llm_playbook    — playbook prompt + playbook output schema
  7. compute_sizing  — position calculator (same as swing)
  8. persist_ticket  — DB insert with workflow_type="support-bounce"

workflow_type = "support-bounce"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf
from pydantic import ValidationError

from app.config import settings
from app.models.ticket_validator import TicketOutputValidator
from app.services.indicators import compute_indicators, compute_weekly_indicators
from app.services.market_breadth import get_market_breadth
from app.services.openrouter_client import OpenRouterClient
from app.services.position_sizer_service import compute_position_size
from app.services.pre_screen import PreScreenResult, pre_screen_support_bounce
from app.services.rs_calculator import compute_rs_indicators, compute_rs_rank_in_universe
from app.services.sr_detector import detect_support_resistance_zones
from app.services.workflows.prompts_support_bounce import SYSTEM_PROMPT_SB, build_playbook_prompt
from app.services.workflows.swing_trade import PreScreenFailed, WorkflowError

logger = logging.getLogger(__name__)


@dataclass
class SupportBounceState:
    """Mutable state passed through workflow nodes."""
    symbol: str
    market: str
    portfolio_size: float
    max_risk_pct: float

    df: Optional[pd.DataFrame] = None
    indicators: Dict[str, Any] = field(default_factory=dict)
    weekly_indicators: Dict[str, Any] = field(default_factory=dict)
    rs_indicators: Dict[str, Any] = field(default_factory=dict)
    sr_data: Dict[str, Any] = field(default_factory=dict)
    screen_result: Optional[PreScreenResult] = None
    breadth: Dict[str, Any] = field(default_factory=dict)
    llm_raw: Dict[str, Any] = field(default_factory=dict)
    sizing: Dict[str, Any] = field(default_factory=dict)
    scale_out_plan: List[Dict[str, Any]] = field(default_factory=list)
    ticket_id: Optional[str] = None
    debug_logs: List[Dict[str, Any]] = field(default_factory=list)


def _trace(state: SupportBounceState, node: str, data: Dict[str, Any]) -> None:
    state.debug_logs.append({
        "node": node,
        "ts": datetime.now(timezone.utc).isoformat(),
        **data,
    })


async def execute_support_bounce(
    symbol: str,
    market: str,
    portfolio_size: float,
    max_risk_pct: float,
    db,
    force_research: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """Run the support-bounce workflow and persist the ticket."""
    if not force_refresh:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        dedup = (
            db.table("research_tickets")
            .select("*")
            .eq("symbol", symbol.upper())
            .eq("market", market.upper())
            .eq("workflow_type", "support-bounce")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if dedup.data:
            logger.info(f"[support_bounce] Dedup hit for {symbol}: returning cached ticket")
            return dedup.data[0]

    state = SupportBounceState(
        symbol=symbol, market=market,
        portfolio_size=portfolio_size, max_risk_pct=max_risk_pct,
    )

    state = await _node_fetch_data(state)
    state = await _node_fetch_rs(state, db)
    state = _node_detect_sr(state)
    state = await _node_pre_screen_sb(state, force_research)
    state = await _node_fetch_breadth(state)
    state = await _node_llm_playbook(state)
    state = _node_compute_sizing(state)
    ticket = await _node_persist_ticket(state, db)

    return ticket


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def _node_fetch_data(state: SupportBounceState) -> SupportBounceState:
    yf_symbol = f"{state.symbol}.TA" if state.market.upper() == "TASE" else state.symbol
    logger.info(f"[support_bounce] Fetching data for {yf_symbol}")
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

    if state.market.upper() == "TASE":
        for col in ("open", "high", "low", "close"):
            df[col] = df[col] / 100.0

    state.df = df
    state.indicators = compute_indicators(df)
    if not state.indicators:
        raise WorkflowError(f"Insufficient data for {yf_symbol}")
    state.weekly_indicators = compute_weekly_indicators(df)

    _trace(state, "fetch_data", {
        "sessions": len(df),
        "price": state.indicators.get("price"),
        "rsi14": state.indicators.get("rsi14"),
        "ma50": state.indicators.get("ma50"),
        "ma200": state.indicators.get("ma200"),
        "vol_dry_up_ratio": state.indicators.get("vol_dry_up_ratio"),
    })
    return state


async def _node_fetch_rs(state: SupportBounceState, db) -> SupportBounceState:
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
            except Exception as e:
                logger.warning(f"[support_bounce] RS rank failed: {e}")
    except Exception as e:
        logger.warning(f"[support_bounce] RS node failed (non-fatal): {e}")
        state.rs_indicators = {"error": str(e)}

    _trace(state, "fetch_rs", {
        "rs_composite": state.rs_indicators.get("rs_composite"),
        "rs_rank_pct": state.rs_indicators.get("rs_rank_pct"),
    })
    return state


def _node_detect_sr(state: SupportBounceState) -> SupportBounceState:
    """Detect support/resistance zones. Pure computation — no I/O."""
    state.sr_data = detect_support_resistance_zones(state.df, state.indicators)
    logger.info(
        f"[support_bounce] S/R: nearest_support={state.sr_data.get('nearest_support', {}).get('price')}, "
        f"nearest_resistance={state.sr_data.get('nearest_resistance', {}).get('price')}, "
        f"rr_ratio={state.sr_data.get('rr_ratio')}"
    )
    _trace(state, "detect_sr", {
        "support_zones": len(state.sr_data.get("support_zones", [])),
        "resistance_zones": len(state.sr_data.get("resistance_zones", [])),
        "nearest_support_price": (state.sr_data.get("nearest_support") or {}).get("price"),
        "nearest_resistance_price": (state.sr_data.get("nearest_resistance") or {}).get("price"),
        "rr_ratio": state.sr_data.get("rr_ratio"),
    })
    return state


async def _node_pre_screen_sb(state: SupportBounceState, force: bool) -> SupportBounceState:
    result = pre_screen_support_bounce(
        symbol=state.symbol,
        market=state.market,
        df=state.df,
        indicators=state.indicators,
        sr_data=state.sr_data,
    )
    state.screen_result = result
    logger.info(f"[support_bounce] Pre-screen: {result.summary}")
    _trace(state, "pre_screen_sb", {
        "passed": result.passed,
        "summary": result.summary,
        "checks": result.checks,
    })
    if not result.passed and not force:
        raise PreScreenFailed(result)
    return state


async def _node_fetch_breadth(state: SupportBounceState) -> SupportBounceState:
    try:
        state.breadth = get_market_breadth(state.market)
    except Exception as e:
        logger.warning(f"[support_bounce] Breadth failed: {e}")
        state.breadth = {"available": False, "zone": "Neutral", "note": str(e)}
    _trace(state, "fetch_breadth", {"zone": state.breadth.get("zone")})
    return state


async def _node_llm_playbook(state: SupportBounceState) -> SupportBounceState:
    prompt = build_playbook_prompt(
        symbol=state.symbol,
        market=state.market,
        indicators=state.indicators,
        sr_data=state.sr_data,
        breadth=state.breadth,
        portfolio_size=state.portfolio_size,
        max_risk_pct=state.max_risk_pct,
        rs_indicators=state.rs_indicators or None,
        weekly_indicators=state.weekly_indicators or None,
    )

    _trace(state, "llm_playbook_prompt", {
        "model": settings.research_model,
        "full_prompt": prompt,
        "system_prompt": SYSTEM_PROMPT_SB,
    })

    client = OpenRouterClient()
    logger.info(f"[support_bounce] Calling LLM for {state.symbol}")
    try:
        result = await client.research(
            prompt=prompt,
            system_context=SYSTEM_PROMPT_SB,
            temperature=0.3,
            max_tokens=3000,
        )
    except Exception as e:
        raise WorkflowError(f"LLM playbook call failed: {e}") from e

    required = ["setup_status", "entry_price", "stop_loss", "target_1", "bullish_probability"]
    missing = [f for f in required if f not in result]
    if missing:
        raise WorkflowError(f"LLM playbook missing required fields: {missing}")

    state.llm_raw = result
    _trace(state, "llm_playbook_response", {
        "setup_status": result.get("setup_status"),
        "entry_trigger": result.get("entry_trigger"),
        "entry_price": result.get("entry_price"),
        "stop_loss": result.get("stop_loss"),
        "target_1": result.get("target_1"),
        "rr_ratio": result.get("rr_ratio"),
        "verdict": (result.get("final_recommendation") or {}).get("verdict"),
    })
    return state


def _node_compute_sizing(state: SupportBounceState) -> SupportBounceState:
    llm = state.llm_raw
    entry = float(llm.get("entry_price") or 0)
    stop  = float(llm.get("stop_loss") or 0)

    if entry <= 0 or stop <= 0 or stop >= entry:
        state.sizing = {"shares": 0, "position_value": 0.0, "dollar_risk": 0.0, "error": "Invalid entry/stop"}
        return state

    state.sizing = compute_position_size(
        entry_price=entry, stop_price=stop,
        account_size=state.portfolio_size,
        risk_pct=state.max_risk_pct,
        market=state.market,
    )
    total_shares = int(state.sizing.get("shares") or 0)
    dollar_risk = float(state.sizing.get("dollar_risk") or 0)
    position_value = float(state.sizing.get("position_value") or 0)

    # Cap to portfolio
    if position_value > state.portfolio_size and entry > 0:
        total_shares = int(state.portfolio_size / entry)
        position_value = round(total_shares * entry, 2)
        dollar_risk = round(total_shares * (entry - stop), 2)
        state.sizing.update({
            "shares": total_shares,
            "position_value": position_value,
            "dollar_risk": dollar_risk,
            "risk_pct_actual": round(dollar_risk / state.portfolio_size * 100, 2),
            "capped_by_portfolio": True,
        })

    # Scale-out plan: T1 (60%) and T2 (40%)
    t1 = float(llm.get("target_1") or 0)
    t2 = float(llm.get("target_2") or 0)
    plan = []
    if t1 and total_shares:
        shares_t1 = max(1, round(total_shares * 0.60))
        plan.append({"label": "T1", "price": t1, "share_pct": 60, "shares": shares_t1,
                     "r_multiple": round((t1 - entry) / (entry - stop), 2) if entry != stop else None,
                     "partial_value": round(shares_t1 * t1, 2)})
    if t2 and total_shares:
        shares_t2 = total_shares - (plan[0]["shares"] if plan else 0)
        plan.append({"label": "T2", "price": t2, "share_pct": 40, "shares": shares_t2,
                     "r_multiple": round((t2 - entry) / (entry - stop), 2) if entry != stop else None,
                     "partial_value": round(shares_t2 * t2, 2)})
    state.scale_out_plan = plan

    _trace(state, "compute_sizing", {
        "shares": state.sizing.get("shares"),
        "dollar_risk": state.sizing.get("dollar_risk"),
        "scale_out_plan": plan,
    })
    return state


async def _node_persist_ticket(state: SupportBounceState, db) -> Dict[str, Any]:
    llm = state.llm_raw
    sizing = state.sizing
    currency = "ILS" if state.market.upper() == "TASE" else "USD"

    # Validate core fields using existing validator
    try:
        TicketOutputValidator(
            entry_price=float(llm.get("entry_price") or 0),
            stop_loss=float(llm.get("stop_loss") or 0),
            target=float(llm.get("target_1") or 0),
            risk_reward_ratio=float(llm.get("rr_ratio") or 0),
            bullish_probability=float(llm.get("bullish_probability") or 0),
            position_size=int(sizing.get("shares") or 0),
            key_triggers=llm.get("key_triggers") or [],
        )
    except ValidationError as e:
        errors = "; ".join(f"{err['loc'][0]}: {err['msg']}" for err in e.errors())
        raise WorkflowError(f"Playbook output validation failed: {errors}") from e

    synthesized_score = llm.get("synthesized_score") or {}
    final_rec = llm.get("final_recommendation") or {}

    metadata = {
        # Playbook-specific fields
        "setup_status": llm.get("setup_status"),
        "entry_trigger": llm.get("entry_trigger"),
        "abort_conditions": llm.get("abort_conditions", []),
        "expiry_range": llm.get("expiry_range"),
        "not_ready_reason": llm.get("not_ready_reason"),
        "check_back_condition": llm.get("check_back_condition"),
        "support_zone": llm.get("support_zone"),
        "resistance_zone": llm.get("resistance_zone"),
        "hidden_risks": llm.get("hidden_risks", []),
        "target_2": llm.get("target_2"),
        # Standard fields
        "synthesized_score": synthesized_score,
        "final_recommendation": final_rec,
        "scale_out_plan": state.scale_out_plan,
        "caveats": llm.get("caveats", []),
        # Context
        "sr_data": {
            "nearest_support": state.sr_data.get("nearest_support"),
            "nearest_resistance": state.sr_data.get("nearest_resistance"),
            "rr_ratio": state.sr_data.get("rr_ratio"),
            "support_zones_count": len(state.sr_data.get("support_zones", [])),
        },
        "pre_screen": {
            "passed": state.screen_result.passed if state.screen_result else None,
            "checks": state.screen_result.checks if state.screen_result else {},
        },
        "rs_indicators": {k: v for k, v in state.rs_indicators.items() if k != "error"},
        "breadth_zone": state.breadth.get("zone"),
        "weekly_trend": state.weekly_indicators.get("weekly_trend"),
        "research_model": settings.research_model,
        "portfolio_size": state.portfolio_size,
        "max_risk_pct": state.max_risk_pct,
        "sizing_detail": sizing,
        "debug_logs": state.debug_logs,
    }

    verdict = final_rec.get("verdict")
    row = {
        "symbol": state.symbol.upper(),
        "market": state.market.upper(),
        "workflow_type": "support-bounce",
        "entry_price": float(llm.get("entry_price") or 0),
        "stop_loss": float(llm.get("stop_loss") or 0),
        "target": float(llm.get("target_1") or 0),
        "position_size": sizing.get("shares", 0),
        "max_risk": sizing.get("dollar_risk", 0),
        "currency": currency,
        "bullish_probability": float(llm.get("bullish_probability") or 0),
        "key_triggers": llm.get("key_triggers", []),
        "status": "pending",
        "rs_rank_pct": state.rs_indicators.get("rs_rank_pct"),
        "setup_score": int(float(_total)) if (_total := synthesized_score.get("total")) is not None else None,
        "verdict": verdict if verdict in ("Strong Buy", "Buy", "Watch", "Avoid") else None,
        "entry_type": "breakout",   # support-bounce always uses breakout-style entry
        "metadata": metadata,
    }

    result = db.table("research_tickets").insert(row).execute()
    if not result.data:
        raise WorkflowError("DB insert returned no data")

    ticket = result.data[0]
    logger.info(f"[support_bounce] Ticket persisted: {ticket.get('id')}")
    return ticket
