"""Entry point: python -m scripts.backtest"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("backtest")


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Minerva local backtest — replay 1yr of TASE scans"
    )
    parser.add_argument(
        "--start-date",
        default=str(date.today() - timedelta(days=365)),
        help="Simulation start date YYYY-MM-DD (default: today-1yr)",
    )
    parser.add_argument(
        "--end-date",
        default=str(date.today()),
        help="Simulation end date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--capital", type=float, default=20_000.0,
        help="Starting capital in ILS (default: 20000)",
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Ignore LLM cache — re-call OpenRouter for every signal",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run pre-screen only — no LLM calls, no portfolio changes",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent / "output"),
        help="Directory for output CSV/JSON files",
    )
    return parser.parse_args(args)


def main() -> None:
    args = parse_args()
    start = date.fromisoformat(args.start_date)
    end = date.fromisoformat(args.end_date)
    output_dir = Path(args.output_dir)

    # Lazy imports (avoid loading heavy libs before arg parsing)
    from app.config import settings
    from scripts.backtest.data_loader import load_symbols, load_all_ohlc, build_trading_calendar
    from scripts.backtest.llm_cache import LLMCache
    from scripts.backtest.simulator import run_backtest

    cache_dir = Path(__file__).parent / "cache" / "ohlc"
    llm_cache = LLMCache(
        cache_file=Path(__file__).parent / "cache" / "llm_cache.json",
        no_cache=args.no_cache,
    )

    logger.info("Loading symbols from Supabase...")
    symbols = load_symbols(settings.supabase_url, settings.supabase_key)

    logger.info("Loading OHLC data for %d symbols...", len(symbols))
    ohlc_data = load_all_ohlc(symbols, cache_dir=cache_dir)

    if not ohlc_data:
        logger.error("No OHLC data loaded — cannot run backtest")
        sys.exit(1)

    symbol_meta = {s["symbol"]: {"market": s["market"]} for s in symbols}
    trading_calendar = [d for d in build_trading_calendar(ohlc_data) if start <= d <= end]

    logger.info(
        "Running backtest: %s -> %s (%d trading days, %d symbols, %.0f ILS capital)",
        start, end, len(trading_calendar), len(ohlc_data), args.capital,
    )

    summary = run_backtest(
        ohlc_data=ohlc_data,
        symbol_meta=symbol_meta,
        trading_calendar=trading_calendar,
        cache=llm_cache,
        output_dir=output_dir,
        starting_cash=args.capital,
        dry_run=args.dry_run,
    )

    if not args.dry_run:
        logger.info(
            "Backtest complete — %d trades, %.1f%% win rate, %.1f%% total return",
            summary.get("total_trades", 0),
            summary.get("win_rate_pct", 0),
            summary.get("total_return_pct", 0),
        )
        logger.info("Results written to %s", output_dir)


if __name__ == "__main__":
    main()
