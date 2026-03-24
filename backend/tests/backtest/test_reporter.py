import csv
import json
from datetime import date
from pathlib import Path
import pytest
from scripts.backtest.reporter import write_trades_csv, write_daily_csv, write_summary_json

SAMPLE_TRADES = [
    {
        "symbol": "OPCE", "workflow": "technical-swing",
        "entry_date": date(2025, 6, 15), "exit_date": date(2025, 7, 3),
        "hold_days": 18, "entry_price": 412.0,
        "exit_t1": 445.0, "exit_t2": 480.0, "exit_t3": None, "exit_stop": 412.0,
        "shares_t1": 4, "shares_t2": 4, "shares_t3": 0, "shares_stopped": 4,
        "pnl_ils": 280.0, "pnl_pct": 5.7, "outcome": "partial",
        "verdict": "Buy", "setup_score": 42, "rs_rank_pct": None,
        "entry_rationale": "VCP breakout above 52w high",
    }
]

SAMPLE_DAILY = [
    {
        "date": date(2025, 6, 15), "cash": 18_000.0,
        "open_positions_value": 2_000.0, "total_equity": 20_000.0,
        "num_open_positions": 1, "num_new_signals": 2, "num_entries": 1, "num_exits": 0,
    }
]

SAMPLE_SUMMARY = {
    "simulation_period": {"start": "2025-03-23", "end": "2026-03-23"},
    "starting_capital_ils": 20000,
    "ending_equity_ils": 23680,
    "total_return_pct": 18.4,
    "max_drawdown_pct": -12.1,
    "total_trades": 1,
    "wins": 0, "partials": 1, "losses": 0,
    "win_rate_pct": 0.0,
    "avg_win_pct": None, "avg_loss_pct": None,
    "avg_hold_days": 18.0,
    "expectancy_ils": 280.0,
    "skipped_signals": 5,
    "by_workflow": {
        "technical-swing": {"trades": 1, "win_rate_pct": 0.0, "avg_pnl_pct": 5.7},
    },
}


def test_write_trades_csv_creates_file(tmp_path):
    write_trades_csv(SAMPLE_TRADES, tmp_path)
    assert (tmp_path / "backtest_trades.csv").exists()


def test_write_trades_csv_has_correct_headers(tmp_path):
    write_trades_csv(SAMPLE_TRADES, tmp_path)
    with open(tmp_path / "backtest_trades.csv") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
    assert "symbol" in headers
    assert "pnl_ils" in headers
    assert "outcome" in headers
    assert "rs_rank_pct" in headers


def test_write_trades_csv_has_correct_values(tmp_path):
    write_trades_csv(SAMPLE_TRADES, tmp_path)
    with open(tmp_path / "backtest_trades.csv") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["symbol"] == "OPCE"
    assert rows[0]["pnl_ils"] == "280.0"
    assert rows[0]["outcome"] == "partial"


def test_write_daily_csv_creates_file(tmp_path):
    write_daily_csv(SAMPLE_DAILY, tmp_path)
    assert (tmp_path / "backtest_daily_portfolio.csv").exists()


def test_write_daily_csv_has_date_and_equity(tmp_path):
    write_daily_csv(SAMPLE_DAILY, tmp_path)
    with open(tmp_path / "backtest_daily_portfolio.csv") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["total_equity"] == "20000.0"


def test_write_summary_json_creates_file(tmp_path):
    write_summary_json(SAMPLE_SUMMARY, tmp_path)
    assert (tmp_path / "backtest_summary.json").exists()


def test_write_summary_json_is_valid_json(tmp_path):
    write_summary_json(SAMPLE_SUMMARY, tmp_path)
    data = json.loads((tmp_path / "backtest_summary.json").read_text())
    assert data["total_trades"] == 1
    assert "by_workflow" in data
