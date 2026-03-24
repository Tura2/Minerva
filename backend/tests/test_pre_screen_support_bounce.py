import pandas as pd
import pytest
from app.services.pre_screen import pre_screen_support_bounce

def _base_indicators(**overrides):
    ind = {
        "price": 100.0,
        "ma200": 85.0,     # price > MA200 ✓
        "rsi14": 45.0,     # RSI in pullback zone ✓
        "vol_dry_up_ratio": 0.70,  # volume compressing ✓
    }
    ind.update(overrides)
    return ind

def _base_sr(support_price=97.0, resistance_price=108.0, rr=3.0):
    return {
        "nearest_support": {
            "price": support_price,
            "low": support_price - 0.5,
            "high": support_price + 0.5,
            "strength": "Strong",
            "touches": 3,
            "distance_pct": round((100.0 - support_price) / 100.0 * 100, 2),
        },
        "nearest_resistance": {"price": resistance_price, "distance_pct": round((resistance_price - 100.0) / 100.0 * 100, 2)},
        "rr_ratio": rr,
    }

def _make_df(n=50):
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    closes = [100.0] * n
    return pd.DataFrame({
        "open": closes, "high": [c+1 for c in closes],
        "low": [c-1 for c in closes], "close": closes,
        "volume": [500_000] * n,
    }, index=dates)


def test_passes_near_strong_support_with_good_rr():
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), _base_indicators(), _base_sr())
    assert result.passed


def test_fails_when_no_support_found():
    sr = _base_sr()
    sr["nearest_support"] = None
    sr["rr_ratio"] = None
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), _base_indicators(), sr)
    assert not result.passed
    assert any("support" in r.lower() for r in result.reasons)


def test_fails_when_support_too_far():
    # Support 6% below price — too far
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), _base_indicators(), _base_sr(support_price=94.0))
    assert not result.passed


def test_fails_when_price_below_ma200():
    ind = _base_indicators(price=80.0, ma200=85.0)
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), ind, _base_sr())
    assert not result.passed
    assert any("MA200" in r or "uptrend" in r.lower() for r in result.reasons)


def test_fails_when_rsi_overbought():
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), _base_indicators(rsi14=72.0), _base_sr())
    assert not result.passed


def test_fails_when_rr_below_minimum():
    result = pre_screen_support_bounce("TEST", "TASE", _make_df(), _base_indicators(), _base_sr(rr=1.2))
    assert not result.passed
    assert any("R:R" in r or "ratio" in r.lower() for r in result.reasons)
