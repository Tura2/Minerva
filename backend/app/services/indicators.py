"""Technical indicators computed from OHLC DataFrame."""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Compute technical indicators from OHLC DataFrame.

    Args:
        df: DataFrame with columns: open, high, low, close, volume
            Index must be datetime, sorted ascending.

    Returns:
        Dict with indicator values (latest snapshot + helper series).
    """
    if df.empty or len(df) < 20:
        return {}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Moving averages
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()
    ma200 = close.rolling(200).mean()

    # 52-week high/low (252 trading days)
    lookback = min(252, len(df))
    high_52w = high.rolling(lookback).max()
    low_52w = low.rolling(lookback).min()

    # Average volume (50-day)
    avg_vol_50 = volume.rolling(50).mean()

    # ATR-14 (Wilder's smoothing)
    atr14 = _compute_atr(df, period=14)

    # RSI-14
    rsi14 = _compute_rsi(close, period=14)

    # MA200 trending up for 22+ sessions
    ma200_trending_up = False
    ma200_clean = ma200.dropna()
    if len(ma200_clean) >= 22:
        ma200_trending_up = bool(ma200_clean.iloc[-1] > ma200_clean.iloc[-22])

    current_price = float(close.iloc[-1])

    return {
        "price": current_price,
        "ma20": _last_valid(ma20),
        "ma50": _last_valid(ma50),
        "ma150": _last_valid(ma150),
        "ma200": _last_valid(ma200),
        "atr14": _last_valid(atr14),
        "rsi14": _last_valid(rsi14),
        "high_52w": _last_valid(high_52w),
        "low_52w": _last_valid(low_52w),
        "avg_vol_50": _last_valid(avg_vol_50),
        "volume": int(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else None,
        "ma200_trending_up": ma200_trending_up,
        # Series kept for VCP detection (prefixed with _ to signal internal use)
        "_close": close,
        "_high": high,
        "_low": low,
        "_atr14": atr14,
    }


def detect_vcp_contractions(df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect VCP (Volatility Contraction Pattern) from last 60 sessions.

    A VCP requires >= 2 contractions where each successive depth is
    shallower than the prior (ideally <= 75% depth).

    Returns:
        Dict with contraction_count, depths, is_vcp, pivot_buy_point.
    """
    default = {"contraction_count": 0, "depths": [], "is_vcp": False, "pivot_buy_point": None}
    close = indicators.get("_close")
    high = indicators.get("_high")
    if close is None or len(close) < 30:
        return default

    segment_close = close.tail(60)
    segment_high = high.tail(60)

    depths = _find_swing_depths(segment_close, segment_high)

    is_vcp = len(depths) >= 2 and _is_tightening(depths)
    pivot = round(float(segment_high.max()), 4) if is_vcp else None

    return {
        "contraction_count": len(depths),
        "depths": [round(d, 2) for d in depths],
        "is_vcp": is_vcp,
        "pivot_buy_point": pivot,
    }


# ── private helpers ────────────────────────────────────────────────────────────


def _compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=period, min_periods=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(span=period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100.0 - (100.0 / (1.0 + rs))


def _last_valid(series: pd.Series) -> Optional[float]:
    clean = series.dropna()
    if clean.empty:
        return None
    return round(float(clean.iloc[-1]), 4)


def _find_swing_depths(close: pd.Series, high: pd.Series, window: int = 5) -> list:
    """Find % drawdowns from swing highs within a price series."""
    depths = []
    vals = close.values
    highs = high.values
    n = len(vals)

    for i in range(window, n - window):
        is_local_high = all(highs[i] >= highs[i - j] for j in range(1, window + 1)) and all(
            highs[i] >= highs[i + j] for j in range(1, window + 1)
        )
        if not is_local_high:
            continue
        swing_h = float(highs[i])
        trough = float(min(vals[i : min(i + 30, n)]))
        depth_pct = (swing_h - trough) / swing_h * 100
        if 3.0 <= depth_pct <= 50.0:
            depths.append(depth_pct)

    return depths


def _is_tightening(depths: list) -> bool:
    """Each contraction depth <= 75% of the prior."""
    for i in range(1, len(depths)):
        if depths[i] > depths[i - 1] * 0.75:
            return False
    return True
