from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from scripts.backtest.data_loader import (
    build_trading_calendar,
    slice_df,
    normalize_ohlc,
)


# ── normalize_ohlc ────────────────────────────────────────────────────────────

def make_df(dates, closes, market="TASE"):
    df = pd.DataFrame({
        "Open": closes, "High": closes, "Low": closes,
        "Close": closes, "Volume": [1_000_000] * len(dates),
    }, index=pd.to_datetime(dates))
    return df


def test_normalize_ohlc_lowercases_columns():
    df = make_df(["2025-01-01"], [40000])
    result = normalize_ohlc(df, market="US")
    assert "close" in result.columns
    assert "open" in result.columns


def test_normalize_ohlc_tase_divides_by_100():
    """TASE prices from yfinance are in agorot (1/100 ILS)."""
    df = make_df(["2025-01-01"], [40000])
    result = normalize_ohlc(df, market="TASE")
    assert result["close"].iloc[0] == pytest.approx(400.0)


def test_normalize_ohlc_us_does_not_divide():
    df = make_df(["2025-01-01"], [150.0])
    result = normalize_ohlc(df, market="US")
    assert result["close"].iloc[0] == pytest.approx(150.0)


# ── build_trading_calendar ────────────────────────────────────────────────────

def test_trading_calendar_is_union_of_dates():
    dates_a = ["2025-01-02", "2025-01-05", "2025-01-06"]
    dates_b = ["2025-01-02", "2025-01-05", "2025-01-07"]  # different 3rd date
    df_a = pd.DataFrame({"close": [1, 1, 1]}, index=pd.to_datetime(dates_a))
    df_b = pd.DataFrame({"close": [1, 1, 1]}, index=pd.to_datetime(dates_b))
    cal = build_trading_calendar({"A": df_a, "B": df_b})
    # Union: 2, 5, 6, 7
    dates = [d.strftime("%Y-%m-%d") for d in cal]
    assert "2025-01-06" in dates  # only in A
    assert "2025-01-07" in dates  # only in B
    assert cal == sorted(cal)     # must be sorted


def test_trading_calendar_deduplicates():
    dates = ["2025-01-02", "2025-01-02", "2025-01-05"]
    df = pd.DataFrame({"close": [1, 1, 1]}, index=pd.to_datetime(dates))
    cal = build_trading_calendar({"A": df})
    assert len(cal) == len(set(cal))


# ── slice_df ──────────────────────────────────────────────────────────────────

def test_slice_df_excludes_future_bars():
    dates = ["2025-01-02", "2025-01-05", "2025-01-06", "2025-01-07"]
    df = pd.DataFrame({"close": [1, 2, 3, 4]}, index=pd.to_datetime(dates))
    sliced = slice_df(df, date(2025, 1, 6))
    assert len(sliced) == 3
    assert sliced["close"].tolist() == [1, 2, 3]


def test_slice_df_handles_tz_aware_index():
    """yfinance returns tz-aware timestamps for TASE (Asia/Jerusalem)."""
    dates = pd.to_datetime(["2025-01-02", "2025-01-05"]).tz_localize("Asia/Jerusalem")
    df = pd.DataFrame({"close": [1, 2]}, index=dates)
    sliced = slice_df(df, date(2025, 1, 2))
    assert len(sliced) == 1


def test_slice_df_returns_empty_for_no_data():
    df = pd.DataFrame({"close": [1, 2]}, index=pd.to_datetime(["2025-01-06", "2025-01-07"]))
    sliced = slice_df(df, date(2025, 1, 1))
    assert sliced.empty
