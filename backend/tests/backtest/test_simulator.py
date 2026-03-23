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
