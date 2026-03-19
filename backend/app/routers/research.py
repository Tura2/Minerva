from fastapi import APIRouter, HTTPException
from typing import Optional, Dict, Any
from pydantic import BaseModel

router = APIRouter()


class ResearchRequest(BaseModel):
    """Request schema for research workflow execution."""

    symbol: str
    market: str  # "US" or "TASE"
    workflow_type: str  # e.g., "technical-swing", "theme-detector"


class ResearchTicket(BaseModel):
    """Research ticket with entry/exit rules and risk metrics."""

    id: str
    symbol: str
    market: str
    created_at: str
    workflow_type: str
    analysis: Dict[str, Any]
    source_skill: str
    research_model: str
    status: str


@router.post("/execute", response_model=ResearchTicket)
async def execute_research(request: ResearchRequest):
    """
    Execute research workflow for a given symbol.

    Workflow orchestration:
    1. Input validation (symbol exists, market valid)
    2. Fetch market data (OHLC, volume)
    3. Deterministic analysis nodes
    4. LLM research nodes (OpenRouter integration)
    5. Output validation against schema
    6. Persist ticket to database
    """
    # TODO: Implement workflow engine logic using LangGraph
    raise HTTPException(status_code=501, detail="Research workflow not yet implemented")


@router.get("/tickets/{ticket_id}", response_model=ResearchTicket)
async def get_ticket(ticket_id: str):
    """Retrieve a research ticket by ID."""
    # TODO: Fetch from database
    raise HTTPException(status_code=404, detail="Ticket not found")


@router.get("/tickets")
async def list_tickets(market: Optional[str] = None, status: Optional[str] = None):
    """List all research tickets with optional filtering."""
    # TODO: Fetch from database with filters
    return []
