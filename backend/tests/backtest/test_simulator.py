from unittest.mock import MagicMock, patch
import pytest
from scripts.backtest.simulator import detect_signals, resolve_entry


# ── resolve_entry ─────────────────────────────────────────────────────────────

def test_current_entry_always_fills_at_open():
    fill = resolve_entry("current", entry_price=100.0, d1_open=102.0, d1_high=108.0)
    assert fill == pytest.approx(102.0)


def test_breakout_entry_fills_when_high_reaches_price():
    fill = resolve_entry("breakout", entry_price=105.0, d1_open=102.0, d1_high=107.0)
    assert fill == pytest.approx(105.0)


def test_breakout_entry_returns_none_when_price_not_reached():
    fill = resolve_entry("breakout", entry_price=110.0, d1_open=102.0, d1_high=107.0)
    assert fill is None


def test_breakout_entry_returns_none_when_high_equals_price_minus_epsilon():
    fill = resolve_entry("breakout", entry_price=110.0, d1_open=102.0, d1_high=109.99)
    assert fill is None


def test_breakout_entry_fills_when_high_exactly_equals_price():
    fill = resolve_entry("breakout", entry_price=110.0, d1_open=102.0, d1_high=110.0)
    assert fill == pytest.approx(110.0)


# ── detect_signals ────────────────────────────────────────────────────────────

def _make_pass_result():
    r = MagicMock()
    r.passed = True
    return r


def _make_fail_result():
    r = MagicMock()
    r.passed = False
    return r


@patch("scripts.backtest.simulator.pre_screen")
@patch("scripts.backtest.simulator.pre_screen_mean_reversion")
def test_both_workflows_pass_returns_only_swing(mock_mr, mock_swing):
    mock_swing.return_value = _make_pass_result()
    mock_mr.return_value = _make_pass_result()
    signals = detect_signals("TEST", "TASE", MagicMock(), {}, {}, open_symbols=set())
    assert len(signals) == 1
    assert signals[0]["workflow"] == "technical-swing"


@patch("scripts.backtest.simulator.pre_screen")
@patch("scripts.backtest.simulator.pre_screen_mean_reversion")
def test_only_mr_passes_returns_mr(mock_mr, mock_swing):
    mock_swing.return_value = _make_fail_result()
    mock_mr.return_value = _make_pass_result()
    signals = detect_signals("TEST", "TASE", MagicMock(), {}, {}, open_symbols=set())
    assert len(signals) == 1
    assert signals[0]["workflow"] == "mean-reversion-bounce"


@patch("scripts.backtest.simulator.pre_screen")
@patch("scripts.backtest.simulator.pre_screen_mean_reversion")
def test_both_fail_returns_empty(mock_mr, mock_swing):
    mock_swing.return_value = _make_fail_result()
    mock_mr.return_value = _make_fail_result()
    signals = detect_signals("TEST", "TASE", MagicMock(), {}, {}, open_symbols=set())
    assert signals == []


@patch("scripts.backtest.simulator.pre_screen")
@patch("scripts.backtest.simulator.pre_screen_mean_reversion")
def test_symbol_already_open_returns_no_signals(mock_mr, mock_swing):
    mock_swing.return_value = _make_pass_result()
    mock_mr.return_value = _make_pass_result()
    signals = detect_signals("TEST", "TASE", MagicMock(), {}, {}, open_symbols={"TEST"})
    assert signals == []


# ── run_backtest integration (mocked) ─────────────────────────────────────────

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from scripts.backtest.simulator import run_backtest
from scripts.backtest.llm_cache import LLMCache


def _make_ohlc(dates, prices):
    """Helper: build a minimal OHLC DataFrame."""
    return pd.DataFrame({
        "open": prices, "high": [p * 1.02 for p in prices],
        "low": [p * 0.98 for p in prices], "close": prices,
        "volume": [1_000_000] * len(dates),
    }, index=pd.to_datetime(dates))


DAYS = [date(2025, 3, d) for d in range(3, 20)]  # Sun–Thu only for TASE
OHLC_DATA = {"SYM": _make_ohlc([str(d) for d in DAYS], [100.0 + i for i in range(len(DAYS))])}
META = {"SYM": {"market": "TASE"}}


def test_dry_run_produces_signal_csv(tmp_path):
    """Dry-run should write dry_run_signals.csv without calling LLM."""
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    with patch("scripts.backtest.simulator.detect_signals") as mock_detect:
        mock_detect.return_value = [{"workflow": "technical-swing", "pre_screen_result": MagicMock()}]
        with patch("scripts.backtest.simulator.compute_indicators", return_value={"price": 100}):
            with patch("scripts.backtest.simulator.compute_mean_reversion_indicators", return_value={}):
                result = run_backtest(
                    ohlc_data=OHLC_DATA, symbol_meta=META,
                    trading_calendar=DAYS[:5], cache=cache,
                    output_dir=tmp_path, dry_run=True,
                )
    assert result["dry_run"] is True
    assert (tmp_path / "dry_run_signals.csv").exists()


def test_signal_with_cached_ticket_enters_position(tmp_path):
    """A cached ticket should create a position without LLM call."""
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store("SYM", DAYS[0], "technical-swing", {
        "entry_price": 100.0, "entry_type": "current",
        "stop_loss": 90.0, "t1": 112.0, "t2": 124.0, "t3": 140.0,
        "verdict": "Buy", "setup_score": 40, "entry_rationale": "test",
    })
    with patch("scripts.backtest.simulator.detect_signals") as mock_detect:
        mock_detect.return_value = [{"workflow": "technical-swing", "pre_screen_result": MagicMock()}]
        with patch("scripts.backtest.simulator.compute_indicators", return_value={"price": 100}):
            with patch("scripts.backtest.simulator.compute_mean_reversion_indicators", return_value={}):
                with patch("scripts.backtest.simulator.OpenRouterClient") as mock_client_cls:
                    result = run_backtest(
                        ohlc_data=OHLC_DATA, symbol_meta=META,
                        trading_calendar=DAYS[:4], cache=cache,
                        output_dir=tmp_path, dry_run=False,
                    )
    # LLM should NOT have been called (cache hit + open_symbols guard on subsequent days)
    mock_client_cls.return_value.research.assert_not_called()
    assert (tmp_path / "backtest_summary.json").exists()


def test_invalid_ticket_skips_entry(tmp_path):
    """A ticket with null targets is logged as skipped — no position entered."""
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store("SYM", DAYS[0], "technical-swing", {
        "entry_price": 100.0, "entry_type": "current",
        "stop_loss": 90.0, "t1": None, "t2": None, "t3": None,
        "verdict": "Buy", "setup_score": 40, "entry_rationale": "test",
    })
    with patch("scripts.backtest.simulator.detect_signals") as mock_detect:
        mock_detect.return_value = [{"workflow": "technical-swing", "pre_screen_result": MagicMock()}]
        with patch("scripts.backtest.simulator.compute_indicators", return_value={"price": 100}):
            with patch("scripts.backtest.simulator.compute_mean_reversion_indicators", return_value={}):
                with patch("scripts.backtest.simulator.OpenRouterClient") as mock_client_cls:
                    mock_client_cls.return_value.research = AsyncMock(return_value=None)
                    result = run_backtest(
                        ohlc_data=OHLC_DATA, symbol_meta=META,
                        trading_calendar=DAYS[:4], cache=cache,
                        output_dir=tmp_path, dry_run=False,
                    )
    assert result["skipped_signals"] >= 1
    assert result["total_trades"] == 0
