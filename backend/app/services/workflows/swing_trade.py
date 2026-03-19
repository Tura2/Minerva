"""
Technical Swing Trade Workflow

Sequential node pipeline (LangGraph-style):
  1. validate_symbol     — deterministic, no LLM
  2. fetch_data          — yfinance OHLC + indicators
  3. pre_screen          — Stage 2 + VCP gate, no LLM
  4. fetch_breadth       — Monty's uptrend CSV (US only)
  5. llm_research        — OpenRouter single call (JSON mode)
  6. validate_output     — Pydantic schema check
  7. compute_sizing      — deterministic position calculator
  8. persist_ticket      — write to research_tickets DB table

If pre_screen fails → WorkflowError is raised with the failure reasons.
The caller (research router) catches this and returns a 422 with the pre-screen details
so the user can decide whether to proceed anyway.
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
from app.services.indicators import compute_indicators
from app.services.market_breadth import get_market_breadth
from app.services.openrouter_client import OpenRouterClient
from app.services.position_sizer_service import compute_position_size
from app.services.pre_screen import PreScreenResult, pre_screen
from app.services.prompts import SYSTEM_PROMPT, build_research_prompt

logger = logging.getLogger(__name__)


class PreScreenFailed(Exception):
    """Raised when the deterministic pre-screen gate fails."""

    def __init__(self, result: PreScreenResult):
        self.result = result
        super().__init__(result.summary)


class WorkflowError(Exception):
    """General workflow execution error."""


@dataclass
class SwingTradeState:
    """Mutable state passed through workflow nodes."""

    symbol: str
    market: str
    portfolio_size: float
    max_risk_pct: float

    df: Optional[pd.DataFrame] = None
    indicators: Dict[str, Any] = field(default_factory=dict)
    screen_result: Optional[PreScreenResult] = None
    breadth: Dict[str, Any] = field(default_factory=dict)
    llm_raw: Dict[str, Any] = field(default_factory=dict)
    sizing: Dict[str, Any] = field(default_factory=dict)
    ticket_id: Optional[str] = None


async def execute_swing_trade(
    symbol: str,
    market: str,
    portfolio_size: float,
    max_risk_pct: float,
    db,  # Supabase client
    force_research: bool = False,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Run the full swing trade workflow and persist the ticket.

    Args:
        symbol:        Ticker (without .TA suffix)
        market:        "US" or "TASE"
        portfolio_size: Account size in local currency
        max_risk_pct:  Max risk per trade as % (e.g. 1.0)
        db:            Supabase client instance
        force_research: If True, skip pre-screen gate and run LLM anyway
        force_refresh:  If True, skip 24h deduplication check and run fresh

    Returns:
        research_ticket row as dict

    Raises:
        PreScreenFailed: if pre-screen fails and force_research=False
        WorkflowError:   on data fetch or LLM errors
    """
    # ── Deduplication check: return cached ticket if run within last 24h ─────
    if not force_refresh:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        dedup_result = (
            db.table("research_tickets")
            .select("*")
            .eq("symbol", symbol.upper())
            .eq("market", market.upper())
            .eq("workflow_type", "technical-swing")
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if dedup_result.data:
            cached = dedup_result.data[0]
            logger.info(
                f"[swing_trade] Dedup hit for {symbol}/{market}: returning ticket {cached.get('id')}"
            )
            return cached

    state = SwingTradeState(
        symbol=symbol,
        market=market,
        portfolio_size=portfolio_size,
        max_risk_pct=max_risk_pct,
    )

    state = await _node_fetch_data(state)
    state = await _node_pre_screen(state, force_research)
    state = await _node_fetch_breadth(state)
    state = await _node_llm_research(state)
    state = _node_compute_sizing(state)
    ticket = await _node_persist_ticket(state, db)

    return ticket


# ── Nodes ─────────────────────────────────────────────────────────────────────


async def _node_fetch_data(state: SwingTradeState) -> SwingTradeState:
    """Fetch 1-year OHLC data from yfinance and compute indicators."""
    yf_symbol = f"{state.symbol}.TA" if state.market.upper() == "TASE" else state.symbol

    logger.info(f"[swing_trade] Fetching data for {yf_symbol}")
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="1y", interval="1d")
    except Exception as e:
        raise WorkflowError(f"yfinance fetch failed for {yf_symbol}: {e}") from e

    if df.empty:
        raise WorkflowError(f"No data returned for {yf_symbol}")

    # Normalize column names
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()

    state.df = df
    state.indicators = compute_indicators(df)

    if not state.indicators:
        raise WorkflowError(f"Insufficient data to compute indicators for {yf_symbol}")

    logger.info(
        f"[swing_trade] Data fetched: {len(df)} sessions, "
        f"price={state.indicators.get('price')}"
    )
    return state


async def _node_pre_screen(state: SwingTradeState, force: bool) -> SwingTradeState:
    """Run deterministic Stage 2 + VCP gate."""
    result = pre_screen(
        symbol=state.symbol,
        market=state.market,
        df=state.df,
        indicators=state.indicators,
    )
    state.screen_result = result
    logger.info(f"[swing_trade] Pre-screen: {result.summary}")

    if not result.passed and not force:
        raise PreScreenFailed(result)

    return state


async def _node_fetch_breadth(state: SwingTradeState) -> SwingTradeState:
    """Fetch market breadth (US only; TASE returns neutral stub)."""
    try:
        state.breadth = get_market_breadth(state.market)
    except Exception as e:
        logger.warning(f"[swing_trade] Breadth fetch failed: {e}")
        state.breadth = {
            "available": False,
            "note": f"Breadth unavailable: {e}",
            "zone": "Neutral",
        }
    return state


async def _node_llm_research(state: SwingTradeState) -> SwingTradeState:
    """Call OpenRouter for LLM analysis. Returns structured JSON."""
    prompt = build_research_prompt(
        symbol=state.symbol,
        market=state.market,
        indicators=state.indicators,
        pre_screen_result=state.screen_result,
        breadth=state.breadth,
        portfolio_size=state.portfolio_size,
        max_risk_pct=state.max_risk_pct,
    )

    client = OpenRouterClient()
    logger.info(f"[swing_trade] Calling LLM ({settings.research_model}) for {state.symbol}")

    try:
        result = await client.research(
            prompt=prompt,
            system_context=SYSTEM_PROMPT,
            temperature=0.4,
            max_tokens=2500,
        )
    except Exception as e:
        raise WorkflowError(f"LLM research failed: {e}") from e

    # Validate required fields
    required = ["entry_price", "stop_loss", "target", "bullish_probability", "key_triggers"]
    missing = [f for f in required if f not in result]
    if missing:
        raise WorkflowError(f"LLM response missing required fields: {missing}. Got: {list(result.keys())}")

    state.llm_raw = result
    logger.info(
        f"[swing_trade] LLM analysis complete: entry={result.get('entry_price')}, "
        f"stop={result.get('stop_loss')}, target={result.get('target')}, "
        f"prob={result.get('bullish_probability')}"
    )
    return state


def _node_compute_sizing(state: SwingTradeState) -> SwingTradeState:
    """Compute position size from LLM entry/stop prices."""
    llm = state.llm_raw
    entry = float(llm.get("entry_price", 0) or 0)
    stop = float(llm.get("stop_loss", 0) or 0)

    if entry <= 0 or stop <= 0 or stop >= entry:
        logger.warning(f"[swing_trade] Invalid entry/stop for sizing: entry={entry}, stop={stop}")
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
    logger.info(
        f"[swing_trade] Sizing: {state.sizing.get('shares')} shares, "
        f"risk={state.sizing.get('dollar_risk')} {state.sizing.get('currency')}"
    )
    return state


async def _node_persist_ticket(state: SwingTradeState, db) -> Dict[str, Any]:
    """Validate final output and write to research_tickets table."""
    llm = state.llm_raw
    sizing = state.sizing
    currency = sizing.get("currency", "USD" if state.market.upper() == "US" else "ILS")

    # ── Output validation (fail loudly before DB write) ──────────────────────
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

    metadata = {
        "entry_rationale": llm.get("entry_rationale", ""),
        "stop_rationale": llm.get("stop_rationale", ""),
        "target_rationale": llm.get("target_rationale", ""),
        "risk_reward_ratio": llm.get("risk_reward_ratio"),
        "setup_quality": llm.get("setup_quality", "C"),
        "trend_context": llm.get("trend_context", ""),
        "volume_context": llm.get("volume_context", ""),
        "market_breadth_context": llm.get("market_breadth_context", ""),
        "caveats": llm.get("caveats", []),
        "pre_screen": {
            "passed": state.screen_result.passed if state.screen_result else None,
            "checks": state.screen_result.checks if state.screen_result else {},
            "vcp": state.screen_result.vcp if state.screen_result else {},
        },
        "breadth_zone": state.breadth.get("zone"),
        "breadth_score": state.breadth.get("composite_score"),
        "research_model": settings.research_model,
        "portfolio_size": state.portfolio_size,
        "max_risk_pct": state.max_risk_pct,
        "sizing_detail": sizing,
    }

    row = {
        "symbol": state.symbol.upper(),
        "market": state.market.upper(),
        "workflow_type": "technical-swing",
        "entry_price": float(llm.get("entry_price") or 0),
        "stop_loss": float(llm.get("stop_loss") or 0),
        "target": float(llm.get("target") or 0),
        "position_size": sizing.get("shares", 0),
        "max_risk": sizing.get("dollar_risk", 0),
        "currency": currency,
        "bullish_probability": float(llm.get("bullish_probability") or 0),
        "key_triggers": llm.get("key_triggers", []),
        "status": "pending",
        "metadata": metadata,
    }

    result = db.table("research_tickets").insert(row).execute()
    if not result.data:
        raise WorkflowError("DB insert returned no data")

    ticket = result.data[0]
    logger.info(f"[swing_trade] Ticket persisted: {ticket.get('id')}")
    return ticket
