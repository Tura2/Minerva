"""Write backtest results to CSV and JSON files."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

TRADE_FIELDS = [
    "symbol", "workflow", "entry_date", "exit_date", "hold_days",
    "entry_price", "exit_t1", "exit_t2", "exit_t3", "exit_stop",
    "shares_t1", "shares_t2", "shares_t3", "shares_stopped",
    "pnl_ils", "pnl_pct", "outcome",
    "verdict", "setup_score", "rs_rank_pct", "entry_rationale",
]

DAILY_FIELDS = [
    "date", "cash", "open_positions_value", "total_equity",
    "num_open_positions", "num_new_signals", "num_entries", "num_exits",
]


def write_trades_csv(trades: List[Dict[str, Any]], output_dir: Path) -> None:
    out = Path(output_dir) / "backtest_trades.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRADE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(trades)
    logger.info("Wrote %d trades → %s", len(trades), out)


def write_daily_csv(daily: List[Dict[str, Any]], output_dir: Path) -> None:
    out = Path(output_dir) / "backtest_daily_portfolio.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DAILY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(daily)
    logger.info("Wrote %d daily rows → %s", len(daily), out)


def write_summary_json(summary: Dict[str, Any], output_dir: Path) -> None:
    out = Path(output_dir) / "backtest_summary.json"
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote summary → %s", out)
