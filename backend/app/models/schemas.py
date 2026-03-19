"""Pydantic schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class MarketType(str, Enum):
    """Supported markets."""

    US = "US"
    TASE = "TASE"


class Currency(str, Enum):
    """Currency by market."""

    USD = "USD"
    ILS = "ILS"


class CandleSchema(BaseModel):
    """OHLC candle data."""

    ts: int = Field(..., description="Epoch milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class ExecutionLevelsSchema(BaseModel):
    """Trade execution levels."""

    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    checkpoint: Optional[float] = None


class ResearchTicketAnalysisSchema(BaseModel):
    """Analysis payload in research ticket."""

    entry_price: float
    entry_rationale: str
    stop_loss: float
    target: float
    position_size: int
    max_risk: float
    bullish_probability: float
    key_triggers: List[str]
    caveats: List[str] = []


class ResearchTicketSchema(BaseModel):
    """Research ticket output schema."""

    id: str
    symbol: str
    market: MarketType
    created_at: datetime
    workflow_type: str
    analysis: ResearchTicketAnalysisSchema
    source_skill: str
    research_model: str
    status: str = "approved"


class CandidateSchema(BaseModel):
    """Screened candidate symbol."""

    symbol: str
    market: MarketType
    price: Optional[float] = None
    volume: Optional[float] = None
    screening_score: Optional[float] = None
    timestamp: Optional[datetime] = None


class ScanResultSchema(BaseModel):
    """Scan result with candidates."""

    market: MarketType
    candidates: List[CandidateSchema]
    total_screened: int
    total_filtered: int
    timestamp: datetime
