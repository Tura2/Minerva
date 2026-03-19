from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()


class Candle(BaseModel):
    """OHLC candle with timestamp."""

    ts: int  # epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class ExecutionLevels(BaseModel):
    """Entry, exit, and checkpoint levels for a trade."""

    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    checkpoint: Optional[float] = None


class MarketHistoryResponse(BaseModel):
    """Market history response with normalized OHLC data."""

    symbol: str
    market: str
    candles: List[Candle]
    execution_levels: ExecutionLevels
    last_updated: str


@router.get("/history", response_model=MarketHistoryResponse)
async def get_market_history(
    symbol: str = Query(...),
    market: str = Query(...),
    period: str = Query("3mo"),  # e.g., "1mo", "3mo", "1y"
    interval: str = Query("1d"),  # e.g., "1d", "1h"
):
    """
    Fetch market history for a symbol.

    Returns:
    - Candle data normalized for frontend chart rendering
    - Execution levels (entry, stop, target, checkpoint) from linked ticket
    - Last updated timestamp
    """
    # TODO: Implement yfinance fetching and normalization
    return {
        "symbol": symbol,
        "market": market,
        "candles": [],
        "execution_levels": {},
        "last_updated": datetime.utcnow().isoformat(),
    }


@router.get("/symbols/{market}")
async def get_market_symbols(market: str):
    """
    Get list of valid symbols for a market.

    - US: S&P 500 tickers
    - TASE: Tel Aviv Stock Exchange tickers
    """
    # TODO: Load from CSV or cache
    return {"market": market, "symbols": [], "count": 0}
