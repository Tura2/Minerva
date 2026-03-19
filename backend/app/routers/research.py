"""Research router — execute workflows and manage research tickets."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import logging

from app.db import get_db
from app.services.workflows.swing_trade import (
    execute_swing_trade,
    PreScreenFailed,
    WorkflowError,
)

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_WORKFLOWS = {"technical-swing"}
VALID_MARKETS = {"US", "TASE"}


# ── Request / Response models ─────────────────────────────────────────────────


class ResearchRequest(BaseModel):
    symbol: str
    market: str
    workflow_type: str = "technical-swing"
    portfolio_size: float = Field(..., gt=0, description="Account size in local currency")
    max_risk_pct: float = Field(..., gt=0, le=10, description="Max risk per trade as % (e.g. 1.0)")
    force: bool = Field(False, description="Skip pre-screen gate and force LLM research")
    force_refresh: bool = Field(False, description="Bypass 24h dedup check and run fresh research")


class PreScreenFailedResponse(BaseModel):
    detail: str
    pre_screen_summary: str
    checks: Dict[str, bool]
    reasons: List[str]
    vcp: Dict[str, Any]
    force_hint: str = "Set force=true to run LLM research anyway"


class TicketOut(BaseModel):
    id: Optional[str] = None
    symbol: str
    market: str
    workflow_type: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target: Optional[float] = None
    position_size: Optional[int] = None
    max_risk: Optional[float] = None
    currency: Optional[str] = None
    bullish_probability: Optional[float] = None
    key_triggers: Optional[List[str]] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_research(request: ResearchRequest):
    """
    Execute a research workflow for a symbol.

    Workflow stages:
      1. Fetch OHLC + compute indicators (yfinance)
      2. Deterministic pre-screen (Stage 2 Trend Template + VCP)
      3. Fetch market breadth (US only)
      4. LLM analysis via OpenRouter
      5. Position sizing
      6. Persist ticket to DB

    Returns the persisted research ticket.
    If pre-screen fails, returns 422 with check details unless force=true.
    """
    market = request.market.upper()
    if market not in VALID_MARKETS:
        raise HTTPException(status_code=400, detail=f"market must be one of {VALID_MARKETS}")

    if request.workflow_type not in VALID_WORKFLOWS:
        raise HTTPException(
            status_code=400,
            detail=f"workflow_type must be one of {VALID_WORKFLOWS}",
        )

    db = get_db()

    try:
        ticket = await execute_swing_trade(
            symbol=request.symbol.upper(),
            market=market,
            portfolio_size=request.portfolio_size,
            max_risk_pct=request.max_risk_pct,
            db=db,
            force_research=request.force,
            force_refresh=request.force_refresh,
        )
        return ticket

    except PreScreenFailed as e:
        result = e.result
        raise HTTPException(
            status_code=422,
            detail={
                "error": "pre_screen_failed",
                "pre_screen_summary": result.summary,
                "checks": result.checks,
                "reasons": result.reasons,
                "vcp": result.vcp,
                "force_hint": "Set force=true to run LLM research anyway",
            },
        )

    except WorkflowError as e:
        logger.error(f"Workflow error for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        logger.exception(f"Unexpected error for {request.symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: str):
    """Retrieve a research ticket by ID."""
    db = get_db()
    result = db.table("research_tickets").select("*").eq("id", ticket_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return result.data[0]


@router.get("/tickets", response_model=List[TicketOut])
async def list_tickets(
    market: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """List research tickets with optional filters."""
    db = get_db()
    q = db.table("research_tickets").select("*").order("created_at", desc=True)
    if market:
        q = q.eq("market", market.upper())
    if status:
        q = q.eq("status", status)
    result = q.limit(limit).execute()
    return result.data


@router.patch("/tickets/{ticket_id}/status")
async def update_ticket_status(ticket_id: str, status: str):
    """Approve or reject a research ticket."""
    valid_statuses = {"approved", "rejected", "pending"}
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {valid_statuses}",
        )
    db = get_db()
    result = (
        db.table("research_tickets")
        .update({"status": status})
        .eq("id", ticket_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found")
    return result.data[0]
