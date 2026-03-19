"""Market data router — OHLC history, quotes, and symbol lists."""

import asyncio
import yfinance as yf
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from app.db import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Warn if last candle is older than this many hours
STALE_THRESHOLD_HOURS = 24


class Candle(BaseModel):
    ts: int  # epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class ExecutionLevels(BaseModel):
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    checkpoint: Optional[float] = None


class MarketHistoryResponse(BaseModel):
    symbol: str
    market: str
    candles: list[Candle]
    execution_levels: ExecutionLevels
    last_updated: str
    is_stale: bool = False


def _yf_symbol(symbol: str, market: str) -> str:
    """Append .TA suffix for TASE symbols if not already present."""
    if market == "TASE" and not symbol.endswith(".TA"):
        return f"{symbol}.TA"
    return symbol


def _normalize_candles(df, market: str = "US") -> list[Candle]:
    """Convert yfinance DataFrame to list of Candle with epoch-ms timestamps.
    TASE prices are in agorot (1/100 ILS) — divide by 100 to get ILS.
    """
    divisor = 100.0 if market.upper() == "TASE" else 1.0
    candles = []
    for ts, row in df.iterrows():
        epoch_ms = int(ts.timestamp() * 1000)
        candles.append(Candle(
            ts=epoch_ms,
            open=round(float(row["Open"]) / divisor, 4),
            high=round(float(row["High"]) / divisor, 4),
            low=round(float(row["Low"]) / divisor, 4),
            close=round(float(row["Close"]) / divisor, 4),
            volume=float(row["Volume"]) if row["Volume"] else None,
        ))
    return candles


@router.get("/history", response_model=MarketHistoryResponse)
async def get_market_history(
    symbol: str = Query(...),
    market: str = Query(...),
    period: str = Query("3mo"),
    interval: str = Query("1d"),
    ticket_id: Optional[str] = Query(None, description="Attach execution levels from a research ticket"),
):
    """
    Fetch OHLC history for a symbol via yfinance.
    Returns candles normalized for lightweight-charts (epoch ms timestamps).
    Optionally overlays execution levels from a research ticket.
    """
    market = market.upper()
    yf_sym = _yf_symbol(symbol.upper(), market)

    try:
        ticker = yf.Ticker(yf_sym)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
    except Exception as e:
        logger.error(f"yfinance error for {yf_sym}: {e}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch market data: {e}")

    if df.empty:
        raise HTTPException(status_code=404, detail=f"No data found for {symbol} on {market}")

    candles = _normalize_candles(df, market)

    # Check staleness
    last_ts_ms = candles[-1].ts
    age_hours = (datetime.now(timezone.utc).timestamp() * 1000 - last_ts_ms) / 3_600_000
    is_stale = age_hours > STALE_THRESHOLD_HOURS
    if is_stale:
        logger.warning(f"{symbol} data is {age_hours:.1f}h old (threshold: {STALE_THRESHOLD_HOURS}h)")

    # Execution levels: pull from linked research ticket if provided
    execution_levels = ExecutionLevels()
    if ticket_id:
        try:
            db = get_db()
            result = db.table("research_tickets").select(
                "entry_price,stop_loss,target"
            ).eq("id", ticket_id).single().execute()
            if result.data:
                t = result.data
                execution_levels = ExecutionLevels(
                    entry=t.get("entry_price"),
                    stop=t.get("stop_loss"),
                    target=t.get("target"),
                )
        except Exception as e:
            logger.warning(f"Could not load execution levels for ticket {ticket_id}: {e}")

    return MarketHistoryResponse(
        symbol=symbol.upper(),
        market=market,
        candles=candles,
        execution_levels=execution_levels,
        last_updated=datetime.now(timezone.utc).isoformat(),
        is_stale=is_stale,
    )


class QuoteResponse(BaseModel):
    symbol: str
    market: str
    price: float
    change: float
    change_pct: float
    volume: Optional[float] = None
    error: Optional[str] = None


class BatchQuoteRequest(BaseModel):
    symbols: list[str]
    market: str


def _fetch_quote_sync(symbol: str, market: str) -> dict:
    """Fetch last price + day change for a symbol (synchronous, runs in thread).
    TASE prices from yfinance are in agorot — divide by 100 to get ILS.
    """
    yf_sym = _yf_symbol(symbol.upper(), market.upper())
    divisor = 100.0 if market.upper() == "TASE" else 1.0
    try:
        df = yf.Ticker(yf_sym).history(period="5d", interval="1d", auto_adjust=True)
        if df.empty:
            return {"symbol": symbol.upper(), "market": market.upper(), "error": "No data"}
        raw_price = float(df["Close"].iloc[-1])
        raw_prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else raw_price
        price = round(raw_price / divisor, 4)
        prev_close = raw_prev / divisor
        change = round(price - prev_close, 4)
        change_pct = round((change / prev_close * 100) if prev_close else 0.0, 2)
        volume = float(df["Volume"].iloc[-1]) if df["Volume"].iloc[-1] else None
        return {
            "symbol": symbol.upper(),
            "market": market.upper(),
            "price": price,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
        }
    except Exception as e:
        return {"symbol": symbol.upper(), "market": market.upper(), "error": str(e)}


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    symbol: str = Query(...),
    market: str = Query(...),
):
    """Return last price and day change for a single symbol."""
    result = await asyncio.to_thread(_fetch_quote_sync, symbol, market.upper())
    if result.get("error"):
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/quotes", response_model=list[QuoteResponse])
async def get_batch_quotes(req: BatchQuoteRequest):
    """Return last price and day change for a list of symbols (max 30)."""
    market = req.market.upper()
    symbols = [s.upper() for s in req.symbols[:30]]
    tasks = [asyncio.to_thread(_fetch_quote_sync, s, market) for s in symbols]
    results = await asyncio.gather(*tasks)
    return list(results)


@router.get("/symbols/{market}")
async def get_market_symbols(market: str):
    """
    Return watchlist symbols for a given market.
    These are the user's tracked symbols and serve as the scan universe.
    """
    market = market.upper()
    if market not in ("US", "TASE"):
        raise HTTPException(status_code=400, detail="market must be US or TASE")

    db = get_db()
    result = db.table("watchlist_items").select("symbol").eq("market", market).execute()
    symbols = [row["symbol"] for row in result.data]
    return {"market": market, "symbols": symbols, "count": len(symbols)}
