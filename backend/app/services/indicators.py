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
    current_vol = int(volume.iloc[-1]) if not pd.isna(volume.iloc[-1]) else None

    # ATR as % of current price — normalises volatility across price levels
    atr14_val = _last_valid(atr14)
    atr_pct = round(atr14_val / current_price * 100, 4) if (atr14_val and current_price) else None

    # Relative Volume — current session vs 50-day average (normalises across markets)
    avg_vol_50_val = _last_valid(avg_vol_50)
    rvol = (
        round(current_vol / avg_vol_50_val, 4)
        if (current_vol and avg_vol_50_val and avg_vol_50_val > 0)
        else None
    )

    # ── Volume profile: accumulation vs distribution (last 20 sessions) ────────
    accum_days: Optional[int] = None
    distrib_days: Optional[int] = None
    vol_dry_up: Optional[bool] = None

    vol_dry_up_ratio: Optional[float] = None  # 10d avg vol / 50d avg vol

    if len(df) >= 20 and avg_vol_50_val:
        seg = df.tail(20).copy()
        seg_prev_close = seg["close"].shift(1)
        seg_up = seg["close"] > seg_prev_close
        seg_above_avg = seg["volume"] > avg_vol_50_val
        accum_days = int((seg_up & seg_above_avg).sum())
        distrib_days = int((~seg_up & seg_above_avg).sum())
        last3_vol = float(volume.tail(3).mean())
        vol_dry_up = last3_vol < avg_vol_50_val * 0.60

    if len(df) >= 10 and avg_vol_50_val and avg_vol_50_val > 0:
        avg_vol_10 = float(volume.tail(10).mean())
        vol_dry_up_ratio = round(avg_vol_10 / avg_vol_50_val, 4)

    return {
        "price": current_price,
        "ma20": _last_valid(ma20),
        "ma50": _last_valid(ma50),
        "ma150": _last_valid(ma150),
        "ma200": _last_valid(ma200),
        "atr14": atr14_val,
        "atr_pct": atr_pct,
        "rsi14": _last_valid(rsi14),
        "high_52w": _last_valid(high_52w),
        "low_52w": _last_valid(low_52w),
        "avg_vol_50": avg_vol_50_val,
        "rvol": rvol,
        "volume": current_vol,
        "ma200_trending_up": ma200_trending_up,
        # Volume profile
        "accum_days_20": accum_days,
        "distrib_days_20": distrib_days,
        "vol_dry_up": vol_dry_up,
        "vol_dry_up_ratio": vol_dry_up_ratio,  # 10d/50d avg vol ratio (< 0.6 = compression)
        # Series kept for VCP detection (prefixed with _ to signal internal use)
        "_close": close,
        "_high": high,
        "_low": low,
        "_atr14": atr14,
    }


def compute_weekly_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Derive weekly-timeframe indicators from a daily OHLC DataFrame.

    Resamples to weekly (Friday close), then computes:
      - WMA10 (10-week ≈ 50-day proxy)
      - WMA20 (20-week ≈ 100-day proxy)
      - Weekly RSI-14
      - Weekly ATR-14
      - Weekly trend classification: uptrend / downtrend / sideways

    Requires at least 20 weeks of data in the daily frame (~100 days).
    """
    if df.empty or len(df) < 100:
        return {}

    weekly = (
        df.resample("W")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )

    if len(weekly) < 20:
        return {}

    close = weekly["close"]
    wma10 = close.rolling(10).mean()
    wma20 = close.rolling(20).mean()
    wrsi = _compute_rsi(close, 14)
    watr = _compute_atr(weekly, 14)

    latest_close = float(close.iloc[-1])
    wma10_val = _last_valid(wma10)
    wma20_val = _last_valid(wma20)
    wrsi_val = _last_valid(wrsi)
    watr_val = _last_valid(watr)

    if wma10_val and wma20_val:
        if latest_close > wma10_val and wma10_val > wma20_val:
            weekly_trend = "uptrend"
        elif latest_close < wma10_val and wma10_val < wma20_val:
            weekly_trend = "downtrend"
        else:
            weekly_trend = "sideways"
    else:
        weekly_trend = "unknown"

    return {
        "weekly_close": round(latest_close, 4),
        "weekly_ma10": wma10_val,
        "weekly_ma20": wma20_val,
        "weekly_rsi14": wrsi_val,
        "weekly_atr14": watr_val,
        "weekly_trend": weekly_trend,
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


# ── Mean Reversion Indicators ──────────────────────────────────────────────────


def compute_mean_reversion_indicators(
    df: pd.DataFrame,
    indicators: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute mean-reversion-specific indicators on top of base compute_indicators() output.

    New signals:
      - Bollinger Bands (20, 2): upper / middle / lower + %B position
      - Capitulation Volume: down-day with volume >= 2× 50d average (seller exhaustion)
      - Bullish RSI Divergence: lower price low but higher RSI low (momentum reversal)

    Args:
        df:         OHLC DataFrame (sorted ascending, lowercase columns)
        indicators: Output from compute_indicators() — must include _close series

    Returns:
        Dict with MR indicator values.
    """
    close = indicators.get("_close")
    avg_vol_50 = indicators.get("avg_vol_50")

    if close is None or len(close) < 20:
        return {}

    # ── Bollinger Bands (20, 2) ───────────────────────────────────────────────
    ma20 = close.rolling(20).mean()
    bb_std = close.rolling(20).std(ddof=0)
    bb_upper = ma20 + 2 * bb_std
    bb_lower = ma20 - 2 * bb_std

    latest_close = float(close.iloc[-1])
    bb_upper_val = _last_valid(bb_upper)
    bb_lower_val = _last_valid(bb_lower)

    bb_pct_b: Optional[float] = None
    distance_from_lower_bb_pct: Optional[float] = None
    if bb_upper_val and bb_lower_val and (bb_upper_val - bb_lower_val) > 0:
        bb_pct_b = round((latest_close - bb_lower_val) / (bb_upper_val - bb_lower_val), 4)
        # Positive = above lower band; negative = pierced below
        distance_from_lower_bb_pct = round(
            (latest_close - bb_lower_val) / latest_close * 100, 2
        )

    # ── Capitulation Volume (last 10 sessions) ────────────────────────────────
    # A heavy-volume down-day signals weak-hand selling exhaustion.
    capitulation_detected = False
    capitulation_vol_ratio = 0.0
    capitulation_days_ago: Optional[int] = None

    if avg_vol_50 and avg_vol_50 > 0 and len(df) >= 11:
        seg = df.tail(11).copy()
        seg = seg.assign(close_diff=seg["close"].diff()).iloc[1:]  # drop NaN first row
        down_day = seg["close_diff"] < 0
        heavy_vol = seg["volume"] > avg_vol_50 * 2.0
        cap_mask = down_day & heavy_vol

        if cap_mask.any():
            capitulation_detected = True
            cap_rows = seg[cap_mask]
            capitulation_vol_ratio = round(
                float((cap_rows["volume"] / avg_vol_50).max()), 2
            )
            # Sessions ago: 1 = last session, 10 = ten sessions back
            last_cap_pos = cap_rows.index[-1]
            all_positions = seg.index.tolist()
            capitulation_days_ago = len(all_positions) - all_positions.index(last_cap_pos)

    # ── Bullish RSI Divergence (last 30 sessions) ─────────────────────────────
    # Lower price low paired with higher RSI low = hidden buying pressure.
    rsi_divergence = False
    rsi_trough_1: Optional[float] = None
    rsi_trough_2: Optional[float] = None
    price_low_1: Optional[float] = None
    price_low_2: Optional[float] = None

    rsi14 = _compute_rsi(close, period=14)
    rsi_clean = rsi14.dropna()
    if len(rsi_clean) >= 30:
        seg_rsi = rsi14.tail(30).values
        seg_price = close.tail(30).values
        n = len(seg_rsi)
        window = 3

        troughs: list = []
        for i in range(window, n - window):
            if all(seg_rsi[i] <= seg_rsi[i - j] for j in range(1, window + 1)) and all(
                seg_rsi[i] <= seg_rsi[i + j] for j in range(1, window + 1)
            ):
                troughs.append((i, float(seg_rsi[i]), float(seg_price[i])))

        if len(troughs) >= 2:
            t1, t2 = troughs[-2], troughs[-1]
            rsi_trough_1 = round(t1[1], 2)
            rsi_trough_2 = round(t2[1], 2)
            price_low_1 = round(t1[2], 4)
            price_low_2 = round(t2[2], 4)
            # Bullish divergence: price made a lower low but RSI held higher
            if price_low_2 < price_low_1 and rsi_trough_2 > rsi_trough_1:
                rsi_divergence = True

    return {
        "bb_upper": bb_upper_val,
        "bb_middle": _last_valid(ma20),
        "bb_lower": bb_lower_val,
        "bb_pct_b": bb_pct_b,
        "distance_from_lower_bb_pct": distance_from_lower_bb_pct,
        "capitulation_detected": capitulation_detected,
        "capitulation_vol_ratio": capitulation_vol_ratio,
        "capitulation_days_ago": capitulation_days_ago,
        "rsi_divergence": rsi_divergence,
        "rsi_trough_1": rsi_trough_1,
        "rsi_trough_2": rsi_trough_2,
        "price_low_1": price_low_1,
        "price_low_2": price_low_2,
    }
