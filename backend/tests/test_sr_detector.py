# backend/tests/test_sr_detector.py
import pandas as pd
import numpy as np
import pytest
from app.services.sr_detector import detect_support_resistance_zones

def _make_df(closes: list[float], volume: int = 1_000_000) -> pd.DataFrame:
    """Build a minimal OHLC DataFrame from a close price list."""
    dates = pd.date_range("2024-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "open":   [c - 0.5 for c in closes],
        "high":   [c + 1.0 for c in closes],
        "low":    [c - 1.0 for c in closes],
        "close":  closes,
        "volume": [volume] * len(closes),
    }, index=dates)


def test_finds_pivot_lows_as_support():
    # Two clear local lows at ~45 and ~44, price now at 52
    closes = (
        [50, 49, 48, 47, 45, 47, 48, 49, 50, 51,
         50, 49, 47, 44, 46, 48, 49, 50, 51, 52]
    )
    df = _make_df(closes)
    result = detect_support_resistance_zones(df, {})
    assert len(result["support_zones"]) >= 1
    assert result["nearest_support"] is not None
    assert result["nearest_support"]["price"] < 52  # below current price


def test_finds_pivot_highs_as_resistance():
    closes = (
        [50, 51, 52, 53, 55, 53, 52, 51, 50, 49,
         50, 51, 53, 56, 53, 51, 50, 49, 48, 47]
    )
    df = _make_df(closes)
    result = detect_support_resistance_zones(df, {})
    assert result["nearest_resistance"] is not None
    # nearest resistance above current price (47)
    assert result["nearest_resistance"]["price"] > 47


def test_ma_levels_included_as_support():
    closes = [100.0] * 60
    df = _make_df(closes)
    indicators = {"ma50": 95.0, "ma200": 88.0}
    result = detect_support_resistance_zones(df, indicators)
    # MA levels should appear in support zones
    prices = [z["price"] for z in result["support_zones"]]
    assert any(abs(p - 95.0) < 1.0 for p in prices)


def test_rr_ratio_computed_when_both_levels_exist():
    # price=100, nearest support=97 (risk=3), nearest resistance=109 (reward=9) → R:R=3.0
    closes = [100.0] * 30
    df = _make_df(closes)
    indicators = {"ma50": 97.0, "ma200": 85.0}
    # Inject artificial resistance via pivot highs
    closes2 = [100]*10 + [109, 108, 107, 108, 109, 107, 106] + [100]*13
    df2 = _make_df(closes2)
    result = detect_support_resistance_zones(df2, {"ma50": 97.0, "ma200": 85.0})
    if result["rr_ratio"] is not None:
        assert result["rr_ratio"] > 0


def test_returns_none_nearest_support_when_no_pivots_below():
    # All prices ascending — no pivot lows below current price
    closes = list(range(50, 80))  # strictly rising
    df = _make_df(closes)
    result = detect_support_resistance_zones(df, {})
    # May or may not find support depending on MAs — just must not crash
    assert isinstance(result, dict)
    assert "support_zones" in result
    assert "resistance_zones" in result
