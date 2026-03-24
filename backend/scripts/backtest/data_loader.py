"""Load watchlist symbols from Supabase, fetch & cache OHLC from yfinance."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

OHLC_COLS = ["open", "high", "low", "close", "volume"]


def normalize_ohlc(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Lowercase columns; divide price columns by 100 for TASE (agorot → ILS)."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df[[c for c in OHLC_COLS if c in df.columns]]
    if market.upper() == "TASE":
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col] / 100.0
    return df.sort_index()


def fetch_ohlc(symbol: str, market: str, period: str = "2y") -> pd.DataFrame:
    """Download OHLC from yfinance. TASE symbols get .TA suffix."""
    ticker = f"{symbol}.TA" if market.upper() == "TASE" else symbol
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    # yfinance >= 0.2.x returns MultiIndex columns for single tickers — flatten to level 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return normalize_ohlc(df, market)


def load_all_ohlc(
    symbols: List[Dict[str, str]],
    cache_dir: Path,
    period: str = "2y",
    refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Fetch OHLC for all symbols, caching each to a JSON file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, pd.DataFrame] = {}
    for item in symbols:
        sym, market = item["symbol"], item["market"]
        cache_file = cache_dir / f"{sym}_{market}.json"
        if not refresh and cache_file.exists():
            try:
                df = pd.read_json(cache_file)
                df.index = pd.to_datetime(df.index)
                result[sym] = df
                logger.debug("Loaded %s from cache", sym)
                continue
            except Exception as exc:
                logger.warning("Cache load failed for %s: %s — re-fetching", sym, exc)
        try:
            df = fetch_ohlc(sym, market, period=period)
            df.to_json(cache_file)
            result[sym] = df
            logger.info("Fetched %s (%d bars)", sym, len(df))
        except Exception as exc:
            logger.error("Failed to fetch %s: %s — skipping", sym, exc)
    return result


def build_trading_calendar(ohlc_data: Dict[str, pd.DataFrame]) -> List[date]:
    """Union of all symbol date indexes → sorted list of unique trading dates."""
    all_dates: set[date] = set()
    for df in ohlc_data.values():
        for ts in df.index:
            all_dates.add(pd.Timestamp(ts).normalize().date())
    return sorted(all_dates)


def slice_df(df: pd.DataFrame, up_to_date: date) -> pd.DataFrame:
    """Point-in-time slice: include only bars on or before up_to_date.
    Handles tz-aware indexes (yfinance returns Asia/Jerusalem for TASE).
    Compares using .date() to avoid tz-naive vs tz-aware TypeError.
    """
    if df.empty:
        return df
    mask = df.index.normalize().map(lambda ts: ts.date()) <= up_to_date
    return df.loc[mask]


def load_symbols(supabase_url: str, supabase_key: str) -> List[Dict[str, str]]:
    """Load watchlist symbols from Supabase. Fails fast if < 5 symbols."""
    from supabase import create_client
    client = create_client(supabase_url, supabase_key)
    response = (
        client.table("watchlist_items")
        .select("symbol, market")
        .eq("market", "TASE")
        .execute()
    )
    symbols = [{"symbol": r["symbol"], "market": r["market"]} for r in response.data]
    if len(symbols) < 5:
        raise RuntimeError(
            f"Only {len(symbols)} symbols loaded from Supabase — need at least 5 to run backtest"
        )
    logger.info("Loaded %d symbols from Supabase", len(symbols))
    return symbols
