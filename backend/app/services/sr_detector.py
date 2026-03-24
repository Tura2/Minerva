# backend/app/services/sr_detector.py
"""
Support/Resistance Zone Detector.

Algorithm:
  1. Find pivot lows (local minima) → candidate support levels
  2. Find pivot highs (local maxima) → candidate resistance levels
  3. Add MA levels (20, 50, 200) as dynamic support/resistance
  4. Cluster nearby levels into zones (within 1.5% price band)
  5. Score zones by touch count
  6. Return nearest support below price and nearest resistance above price
  7. Compute R:R ratio: (nearest_resistance - price) / (price - nearest_support)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# How many bars on each side to qualify as a local extremum
PIVOT_WINDOW = 5
# Two levels within this % band are merged into one zone
CLUSTER_TOLERANCE_PCT = 1.5
# Only include pivots from the last N trading sessions (avoids ancient levels)
MAX_PIVOT_LOOKBACK = 252


def detect_support_resistance_zones(
    df: pd.DataFrame,
    indicators: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Detect support and resistance zones from OHLC data + indicator MA levels.

    Args:
        df:          Daily OHLC DataFrame (sorted ascending, at least 20 rows).
        indicators:  Output of compute_indicators() — used to include MA levels.

    Returns dict with:
        support_zones:      list of zone dicts (price, low, high, touches, strength, source)
        resistance_zones:   list of zone dicts
        nearest_support:    closest zone below current price (+ distance_pct), or None
        nearest_resistance: closest zone above current price (+ distance_pct), or None
        rr_ratio:           float or None
    """
    if df.empty or len(df) < 20:
        return _empty_result()

    close = df["close"]
    high = df["high"]
    low = df["low"]
    current_price = float(close.iloc[-1])

    # Limit lookback to avoid ancient irrelevant levels
    lookback_df = df.tail(MAX_PIVOT_LOOKBACK)
    lookback_close = lookback_df["close"]
    lookback_high = lookback_df["high"]
    lookback_low = lookback_df["low"]

    # 1. Pivot levels
    pivot_lows = _find_pivot_lows(lookback_low, PIVOT_WINDOW)
    pivot_highs = _find_pivot_highs(lookback_high, PIVOT_WINDOW)

    support_levels: List[float] = pivot_lows.dropna().tolist()
    resistance_levels: List[float] = pivot_highs.dropna().tolist()

    # 2. MA levels as dynamic S/R
    for key in ("ma20", "ma50", "ma200", "ma150"):
        val = indicators.get(key)
        if val and isinstance(val, (int, float)) and val > 0:
            if val < current_price:
                support_levels.append(float(val))
            else:
                resistance_levels.append(float(val))

    # 3. Cluster into zones
    raw_support_zones = _cluster_levels(
        [l for l in support_levels if l < current_price * 1.01],  # must be below or near price
        CLUSTER_TOLERANCE_PCT,
    )
    raw_resistance_zones = _cluster_levels(
        [l for l in resistance_levels if l > current_price * 0.99],  # must be above or near price
        CLUSTER_TOLERANCE_PCT,
    )

    # 4. Nearest support and resistance
    supports_below = [z for z in raw_support_zones if z["price"] < current_price]
    resistances_above = [z for z in raw_resistance_zones if z["price"] > current_price]

    nearest_support: Optional[Dict] = None
    if supports_below:
        nearest_support = min(supports_below, key=lambda z: current_price - z["price"])
        nearest_support["distance_pct"] = round(
            (current_price - nearest_support["price"]) / current_price * 100, 2
        )

    nearest_resistance: Optional[Dict] = None
    if resistances_above:
        nearest_resistance = min(resistances_above, key=lambda z: z["price"] - current_price)
        nearest_resistance["distance_pct"] = round(
            (nearest_resistance["price"] - current_price) / current_price * 100, 2
        )

    # 5. R:R ratio
    rr_ratio: Optional[float] = None
    if nearest_support and nearest_resistance:
        risk = current_price - nearest_support["price"]
        reward = nearest_resistance["price"] - current_price
        if risk > 0:
            rr_ratio = round(reward / risk, 2)

    return {
        "support_zones": raw_support_zones,
        "resistance_zones": raw_resistance_zones,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "rr_ratio": rr_ratio,
        "current_price": current_price,
    }


# ── Private helpers ────────────────────────────────────────────────────────────


def _empty_result() -> Dict[str, Any]:
    return {
        "support_zones": [],
        "resistance_zones": [],
        "nearest_support": None,
        "nearest_resistance": None,
        "rr_ratio": None,
        "current_price": None,
    }


def _find_pivot_lows(low: pd.Series, window: int) -> pd.Series:
    """Return pivot low prices (NaN elsewhere). A pivot low is a local minimum."""
    pivots = pd.Series(index=low.index, dtype=float)
    arr = low.values
    for i in range(window, len(arr) - window):
        segment = arr[i - window: i + window + 1]
        if arr[i] == segment.min():
            pivots.iloc[i] = arr[i]
    return pivots


def _find_pivot_highs(high: pd.Series, window: int) -> pd.Series:
    """Return pivot high prices (NaN elsewhere). A pivot high is a local maximum."""
    pivots = pd.Series(index=high.index, dtype=float)
    arr = high.values
    for i in range(window, len(arr) - window):
        segment = arr[i - window: i + window + 1]
        if arr[i] == segment.max():
            pivots.iloc[i] = arr[i]
    return pivots


def _cluster_levels(levels: List[float], tolerance_pct: float) -> List[Dict[str, Any]]:
    """
    Group nearby price levels into zones.
    Two levels are in the same zone if they are within `tolerance_pct`% of the lowest level.
    """
    if not levels:
        return []
    sorted_levels = sorted(levels)
    zones: List[Dict[str, Any]] = []
    current_cluster = [sorted_levels[0]]

    for level in sorted_levels[1:]:
        band_base = current_cluster[0]
        if band_base > 0 and (level - band_base) / band_base * 100 <= tolerance_pct:
            current_cluster.append(level)
        else:
            zones.append(_make_zone(current_cluster))
            current_cluster = [level]

    zones.append(_make_zone(current_cluster))
    return zones


def _make_zone(cluster: List[float]) -> Dict[str, Any]:
    touches = len(cluster)
    return {
        "price": round(sum(cluster) / touches, 4),
        "low":   round(min(cluster), 4),
        "high":  round(max(cluster), 4),
        "touches": touches,
        "strength": "Strong" if touches >= 3 else "Moderate" if touches >= 2 else "Weak",
    }
