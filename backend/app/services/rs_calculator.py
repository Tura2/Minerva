"""
Relative Strength calculator.

Computes a stock's RS composite score versus a market benchmark,
and its percentile rank within a watchlist universe.

Methodology adapted from the VCP Screener skill:
  RS Composite = 0.40 × rs_63d + 0.35 × rs_126d + 0.25 × rs_189d
  (weights recency — matches Minervini's RS scoring approach)

Benchmarks:
  US   → SPY (S&P 500 ETF)
  TASE → ^TA125.TA (TA-125 index)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_BENCHMARK = {"US": "SPY", "TASE": "^TA125.TA"}

# Weighted recency: more weight on recent performance
_RS_WEIGHTS = {"rs_63": 0.40, "rs_126": 0.35, "rs_189": 0.25}

# Per-period lookback in trading days (approx 1 calendar year needed for 189d)
_FETCH_PERIOD = "1y"
_FETCH_INTERVAL = "1d"

# Max time to wait for universe RS fetch before giving up on rank
_UNIVERSE_TIMEOUT_SECONDS = 10


def _return_over_n_days(series: pd.Series, n: int) -> Optional[float]:
    """Return percentage change from n days ago to latest, or None if insufficient data."""
    clean = series.dropna()
    if len(clean) < n + 1:
        return None
    end = float(clean.iloc[-1])
    start = float(clean.iloc[-(n + 1)])
    if start == 0:
        return None
    return round((end - start) / start * 100, 4)


def _compute_rs_composite(
    stock_series: pd.Series,
    bench_series: pd.Series,
) -> Dict[str, Any]:
    """
    Compute excess return over benchmark for 63d / 126d / 189d,
    then blend into a single composite score.
    """
    results: Dict[str, Any] = {}
    composite_parts = []

    for key, n in [("rs_63", 63), ("rs_126", 126), ("rs_189", 189)]:
        s_ret = _return_over_n_days(stock_series, n)
        b_ret = _return_over_n_days(bench_series, n)
        if s_ret is not None and b_ret is not None:
            excess = round(s_ret - b_ret, 4)
            results[key] = excess
            composite_parts.append((_RS_WEIGHTS[key], excess))
        else:
            results[key] = None

    if composite_parts:
        total_weight = sum(w for w, _ in composite_parts)
        composite = sum(w * v for w, v in composite_parts) / total_weight
        results["rs_composite"] = round(composite, 4)
    else:
        results["rs_composite"] = None

    return results


def _fetch_pair_sync(yf_symbol: str, benchmark: str) -> Dict[str, Any]:
    """
    Download stock + benchmark in a single yfinance batch call.
    Returns {stock_close, bench_close} as pd.Series, or error dict.
    """
    try:
        df = yf.download(
            [yf_symbol, benchmark],
            period=_FETCH_PERIOD,
            interval=_FETCH_INTERVAL,
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return {"error": f"No data for {yf_symbol} / {benchmark}"}

        # yfinance returns MultiIndex columns when >1 ticker: (field, ticker)
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"]
            stock_close = close.get(yf_symbol)
            if stock_close is None:
                stock_close = close.get(yf_symbol.upper())
            bench_close = close.get(benchmark)
            if bench_close is None:
                bench_close = close.get(benchmark.upper())
        else:
            # Single ticker fallback (shouldn't happen for 2-ticker download)
            stock_close = df.get("Close")
            bench_close = None

        if stock_close is None or bench_close is None:
            return {"error": f"Missing columns for {yf_symbol}/{benchmark}"}

        return {"stock": stock_close.dropna(), "bench": bench_close.dropna()}
    except Exception as e:
        return {"error": str(e)}


async def compute_rs_indicators(
    symbol: str,
    market: str,
) -> Dict[str, Any]:
    """
    Fetch OHLC for symbol + benchmark, compute RS metrics.

    Returns dict with keys:
      rs_63, rs_126, rs_189, rs_composite, benchmark_used
      (all numeric values are excess return in %, or None if unavailable)
    """
    market_upper = market.upper()
    benchmark = _BENCHMARK.get(market_upper, "SPY")
    yf_symbol = f"{symbol}.TA" if market_upper == "TASE" else symbol

    pair = await asyncio.to_thread(_fetch_pair_sync, yf_symbol, benchmark)

    if "error" in pair:
        logger.warning(f"[rs_calculator] RS fetch failed for {yf_symbol}: {pair['error']}")
        return {"benchmark_used": benchmark, "error": pair["error"]}

    rs = _compute_rs_composite(pair["stock"], pair["bench"])
    rs["benchmark_used"] = benchmark
    rs["rs_rank_pct"] = None  # populated later by compute_rs_rank_in_universe
    logger.info(
        f"[rs_calculator] {symbol} RS composite={rs.get('rs_composite')}, "
        f"63d={rs.get('rs_63')}, 126d={rs.get('rs_126')}, 189d={rs.get('rs_189')}"
    )
    return rs


def _fetch_single_composite_sync(yf_symbol: str, benchmark: str) -> Optional[float]:
    """Fetch just the RS composite for one symbol (used for universe ranking)."""
    try:
        df = yf.download(
            [yf_symbol, benchmark],
            period=_FETCH_PERIOD,
            interval=_FETCH_INTERVAL,
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            close = df["Close"]
            stock_close = close.get(yf_symbol)
            bench_close = close.get(benchmark)
        else:
            return None

        if stock_close is None or bench_close is None:
            return None

        rs = _compute_rs_composite(stock_close.dropna(), bench_close.dropna())
        return rs.get("rs_composite")
    except Exception:
        return None


async def compute_rs_rank_in_universe(
    candidate_composite: float,
    universe_symbols: List[str],
    market: str,
) -> Optional[float]:
    """
    Compute the candidate's RS composite percentile rank within a symbol universe.

    Fetches all universe symbols' RS composites in parallel (capped at 30).
    Returns a float 0–100 (e.g. 87.0 = better than 87% of universe), or None on failure.
    """
    if not universe_symbols or candidate_composite is None:
        return None

    market_upper = market.upper()
    benchmark = _BENCHMARK.get(market_upper, "SPY")
    symbols_to_fetch = universe_symbols[:30]

    def yf_sym(s: str) -> str:
        return f"{s}.TA" if market_upper == "TASE" else s

    logger.info(
        f"[rs_calculator] Computing RS rank vs {len(symbols_to_fetch)} universe symbols"
    )
    try:
        tasks = [
            asyncio.to_thread(_fetch_single_composite_sync, yf_sym(s), benchmark)
            for s in symbols_to_fetch
        ]
        composites = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=_UNIVERSE_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("[rs_calculator] Universe RS fetch timed out — skipping rank")
        return None

    valid = [c for c in composites if isinstance(c, float)]
    if not valid:
        return None

    # Percentile: how many universe symbols scored BELOW the candidate
    below = sum(1 for c in valid if c < candidate_composite)
    rank_pct = round(below / len(valid) * 100, 1)
    logger.info(
        f"[rs_calculator] RS rank: {rank_pct:.1f}/100 "
        f"(composite={candidate_composite}, universe_size={len(valid)})"
    )
    return rank_pct
