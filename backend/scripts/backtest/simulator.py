"""Day-by-day simulation loop — signal detection, entry resolution, exit processing."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from app.services.pre_screen import pre_screen, pre_screen_mean_reversion

logger = logging.getLogger(__name__)


# ── Entry resolution ──────────────────────────────────────────────────────────

def resolve_entry(
    entry_type: str,
    entry_price: float,
    d1_open: float,
    d1_high: float,
) -> Optional[float]:
    """Return fill price or None if entry not triggered.

    current  → always fills at D+1 open
    breakout → fills only if D+1 high >= entry_price; fill = entry_price
    """
    if entry_type == "current":
        return d1_open
    if entry_type == "breakout":
        return entry_price if d1_high >= entry_price else None
    logger.warning("Unknown entry_type=%s, treating as current", entry_type)
    return d1_open


# ── Signal detection ──────────────────────────────────────────────────────────

def detect_signals(
    symbol: str,
    market: str,
    df_slice,       # pd.DataFrame — point-in-time slice
    indicators: Dict[str, Any],
    mr_indicators: Dict[str, Any],
    open_symbols: Set[str],
) -> List[Dict[str, Any]]:
    """Run both pre-screen gates. Return passing workflow(s).

    If both pass, only technical-swing is returned (preferred workflow).
    If symbol is already in an open position, returns [].
    """
    if symbol in open_symbols:
        return []

    swing_result = pre_screen(symbol, market, df_slice, indicators)
    mr_result = pre_screen_mean_reversion(symbol, market, df_slice, mr_indicators)

    if swing_result.passed:
        return [{"workflow": "technical-swing", "pre_screen_result": swing_result}]
    if mr_result.passed:
        return [{"workflow": "mean-reversion-bounce", "pre_screen_result": mr_result}]
    return []


# ── Full backtest loop ────────────────────────────────────────────────────────

import asyncio
from datetime import timedelta  # noqa: F401 — available for callers
from pathlib import Path

import pandas as pd

from app.services.indicators import compute_indicators, compute_mean_reversion_indicators
from app.services.openrouter_client import OpenRouterClient
from app.services.position_sizer_service import compute_position_size
from app.services.prompts import build_research_prompt
from app.services.prompts_mean_reversion import build_mr_research_prompt
from scripts.backtest.data_loader import slice_df
from scripts.backtest.llm_cache import LLMCache
from scripts.backtest.portfolio import Portfolio, Position
from scripts.backtest.reporter import write_trades_csv, write_daily_csv, write_summary_json

_NEUTRAL_BREADTH = {
    "zone": "neutral", "uptrend_pct": 50.0,
    "label": "Neutral (TASE stub)", "source": "backtest_stub",
}

_PORTFOLIO_SIZE_FOR_PROMPT = 20_000.0
_MAX_RISK_PCT = 1.0


def _call_llm(
    symbol: str,
    market: str,
    workflow: str,
    indicators: dict,
    mr_indicators: dict,
    pre_screen_result,
    client: OpenRouterClient,
) -> dict | None:
    """Call OpenRouter for a research ticket. Returns raw ticket dict or None on error."""
    try:
        if workflow == "technical-swing":
            prompt = build_research_prompt(
                symbol=symbol, market=market, indicators=indicators,
                pre_screen_result=pre_screen_result, breadth=_NEUTRAL_BREADTH,
                portfolio_size=_PORTFOLIO_SIZE_FOR_PROMPT, max_risk_pct=_MAX_RISK_PCT,
                rs_indicators=None,
            )
        else:
            prompt = build_mr_research_prompt(
                symbol=symbol, market=market, indicators=indicators,
                mr_indicators=mr_indicators, pre_screen_result=pre_screen_result,
                breadth=_NEUTRAL_BREADTH, portfolio_size=_PORTFOLIO_SIZE_FOR_PROMPT,
                max_risk_pct=_MAX_RISK_PCT, rs_indicators=None,
            )
        raw = asyncio.run(client.research(prompt))
        return raw
    except Exception as exc:
        logger.error("LLM call failed for %s/%s: %s", symbol, workflow, exc)
        return None


def _extract_ticket(raw: dict) -> dict | None:
    """Extract and validate required ticket fields from LLM response."""
    if raw is None:
        return None
    required = ["entry_price", "entry_type", "stop_loss"]
    for f in required:
        if raw.get(f) is None:
            logger.warning("LLM ticket missing required field: %s", f)
            return None

    targets = raw.get("scale_out_targets") or {}
    t1 = targets.get("t1") or raw.get("t1")
    t2 = targets.get("t2") or raw.get("t2")
    t3 = targets.get("t3") or raw.get("t3")
    if None in (t1, t2, t3):
        logger.warning("LLM ticket missing scale-out targets: %s", raw)
        return None

    entry_price = float(raw["entry_price"])
    if entry_price <= 0:
        logger.warning("LLM ticket invalid entry_price=%s", entry_price)
        return None

    return {
        "entry_price": entry_price,
        "entry_type": raw.get("entry_type", "current"),
        "stop_loss": float(raw["stop_loss"]),
        "t1": float(t1), "t2": float(t2), "t3": float(t3),
        "verdict": raw.get("verdict", ""),
        "setup_score": int(raw.get("setup_score", 0) or 0),
        "entry_rationale": str(raw.get("entry_rationale", ""))[:200],
    }


def run_backtest(
    ohlc_data: dict,
    symbol_meta: dict,
    trading_calendar: list,
    cache: LLMCache,
    output_dir,
    starting_cash: float = 20_000.0,
    dry_run: bool = False,
) -> dict:
    """Main backtest loop. Returns summary dict."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenRouterClient() if not dry_run else None
    portfolio = Portfolio(starting_cash=starting_cash)

    closed_trades: list[dict] = []
    daily_snapshots: list[dict] = []
    skipped_signals = 0
    dry_run_signals: list[dict] = []

    for i, day in enumerate(trading_calendar):
        portfolio.settle_pending(day)

        close_prices = {
            sym: slice_df(df, day)["close"].iloc[-1]
            for sym, df in ohlc_data.items()
            if not slice_df(df, day).empty
        }

        open_symbols: Set[str] = {pos.symbol for pos in portfolio.open_positions}
        new_signals = 0
        new_entries = 0
        new_exits = 0
        pending_entries: list[dict] = []

        # Signal detection
        for sym, df_full in ohlc_data.items():
            # Skip symbols already in an open position
            if sym in open_symbols:
                continue

            df_slice = slice_df(df_full, day)
            if df_slice.empty:
                continue
            market = symbol_meta[sym]["market"]
            indicators = compute_indicators(df_slice)
            if not indicators:
                continue
            mr_indicators = compute_mean_reversion_indicators(df_slice)
            signals = detect_signals(sym, market, df_slice, indicators, mr_indicators, open_symbols)

            for sig in signals:
                new_signals += 1
                workflow = sig["workflow"]

                if dry_run:
                    dry_run_signals.append({
                        "date": day, "symbol": sym, "workflow": workflow,
                        "pre_screen_passed": True,
                    })
                    continue

                ticket = cache.get(sym, day, workflow)
                if ticket is None:
                    raw = _call_llm(
                        sym, market, workflow, indicators, mr_indicators,
                        sig["pre_screen_result"], client,
                    )
                    if raw is None:
                        skipped_signals += 1
                        continue
                    ticket = _extract_ticket(raw)
                    if ticket is None:
                        skipped_signals += 1
                        continue
                    cache.store(sym, day, workflow, ticket)
                else:
                    ticket = _extract_ticket(ticket)
                    if ticket is None:
                        skipped_signals += 1
                        continue

                pending_entries.append({
                    "symbol": sym, "market": market, "workflow": workflow,
                    "ticket": ticket, "signal_date": day,
                })

        # Entry resolution on D+1
        if i + 1 < len(trading_calendar):
            d1 = trading_calendar[i + 1]
            for pending in pending_entries:
                sym = pending["symbol"]
                ticket = pending["ticket"]
                df_d1 = slice_df(ohlc_data[sym], d1)
                if df_d1.empty:
                    continue
                d1_row = df_d1.iloc[-1]
                d1_open = float(df_d1["open"].iloc[-1]) if "open" in df_d1.columns else float(d1_row["close"])
                d1_high = float(d1_row["high"]) if "high" in d1_row.index else float(d1_row["close"])
                fill = resolve_entry(
                    ticket["entry_type"], ticket["entry_price"],
                    d1_open=d1_open,
                    d1_high=d1_high,
                )
                if fill is None:
                    skipped_signals += 1
                    continue

                sizing = compute_position_size(
                    entry_price=fill,
                    stop_price=ticket["stop_loss"],
                    account_size=portfolio.total_equity(close_prices),
                    risk_pct=_MAX_RISK_PCT,
                    market=pending["market"],
                )
                shares = sizing.get("shares", 0)
                if shares <= 0:
                    skipped_signals += 1
                    continue

                cost = fill * shares
                if not portfolio.can_enter(cost):
                    skipped_signals += 1
                    continue

                pos = Position(
                    symbol=sym, workflow_type=pending["workflow"],
                    entry_date=d1, entry_price=ticket["entry_price"],
                    fill_price=fill, shares_total=shares, shares_remaining=shares,
                    cost_basis=cost, stop_loss=ticket["stop_loss"],
                    t1=ticket["t1"], t2=ticket["t2"], t3=ticket["t3"],
                    verdict=ticket.get("verdict", ""),
                    setup_score=ticket.get("setup_score", 0),
                    entry_rationale=ticket.get("entry_rationale", ""),
                )
                portfolio.enter_position(pos)
                new_entries += 1
                open_symbols.add(sym)

        # Exit processing on D+1
        if i + 1 < len(trading_calendar):
            d1_exit = trading_calendar[i + 1]
            for pos in list(portfolio.open_positions):
                df_full = ohlc_data.get(pos.symbol, pd.DataFrame())
                d1_rows = df_full[df_full.index.normalize() == pd.Timestamp(d1_exit)]
                if d1_rows.empty:
                    continue
                d1_row = d1_rows.iloc[-1]
                day_high = float(d1_row["high"]) if "high" in d1_row.index else float(d1_row["close"])
                day_low = float(d1_row["low"]) if "low" in d1_row.index else float(d1_row["close"])
                events = portfolio.process_position_day(
                    pos,
                    day_high=day_high,
                    day_low=day_low,
                    day=d1_exit,
                )
                if events:
                    new_exits += len(events)
                    if pos.shares_remaining == 0:
                        closed_trades.append(_summarize_trade(pos, pos.exit_events, d1_exit))

        # Daily snapshot
        daily_snapshots.append({
            "date": day, "cash": round(portfolio.cash, 2),
            "open_positions_value": round(portfolio.open_positions_value(close_prices), 2),
            "total_equity": round(portfolio.total_equity(close_prices), 2),
            "num_open_positions": len(portfolio.open_positions),
            "num_new_signals": new_signals, "num_entries": new_entries, "num_exits": new_exits,
        })

    # Dry-run output
    if dry_run:
        import csv
        out = output_dir / "dry_run_signals.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "symbol", "workflow", "pre_screen_passed"])
            writer.writeheader()
            writer.writerows(dry_run_signals)
        logger.info("Dry-run complete — %d signals found → %s", len(dry_run_signals), out)
        return {"dry_run": True, "signals_found": len(dry_run_signals)}

    summary = _compute_summary(
        closed_trades=closed_trades,
        daily_snapshots=daily_snapshots,
        starting_cash=starting_cash,
        skipped_signals=skipped_signals,
        trading_calendar=trading_calendar,
    )
    write_trades_csv(closed_trades, output_dir)
    write_daily_csv(daily_snapshots, output_dir)
    write_summary_json(summary, output_dir)
    return summary


def _summarize_trade(pos: "Position", events: list, exit_date) -> dict:
    t1_events = [e for e in events if e["type"] == "T1"]
    t2_events = [e for e in events if e["type"] == "T2"]
    t3_events = [e for e in events if e["type"] == "T3"]
    stop_events = [e for e in events if e["type"] == "stop"]

    total_proceeds = sum(e["shares"] * e["price"] for e in events)
    pnl_ils = total_proceeds - pos.cost_basis
    pnl_pct = (pnl_ils / pos.cost_basis) * 100 if pos.cost_basis else 0

    if t3_events:
        outcome = "win"
    elif t1_events or t2_events:
        outcome = "partial"
    else:
        outcome = "loss"

    return {
        "symbol": pos.symbol, "workflow": pos.workflow_type,
        "entry_date": pos.entry_date, "exit_date": exit_date,
        "hold_days": (exit_date - pos.entry_date).days,
        "entry_price": pos.fill_price,
        "exit_t1": t1_events[0]["price"] if t1_events else None,
        "exit_t2": t2_events[0]["price"] if t2_events else None,
        "exit_t3": t3_events[0]["price"] if t3_events else None,
        "exit_stop": stop_events[0]["price"] if stop_events else None,
        "shares_t1": t1_events[0]["shares"] if t1_events else 0,
        "shares_t2": t2_events[0]["shares"] if t2_events else 0,
        "shares_t3": t3_events[0]["shares"] if t3_events else 0,
        "shares_stopped": stop_events[0]["shares"] if stop_events else 0,
        "pnl_ils": round(pnl_ils, 2), "pnl_pct": round(pnl_pct, 2),
        "outcome": outcome,
        "verdict": pos.verdict, "setup_score": pos.setup_score,
        "rs_rank_pct": None,
        "entry_rationale": pos.entry_rationale,
    }


def _compute_summary(
    closed_trades, daily_snapshots, starting_cash, skipped_signals, trading_calendar
) -> dict:
    wins = [t for t in closed_trades if t["outcome"] == "win"]
    partials = [t for t in closed_trades if t["outcome"] == "partial"]
    losses = [t for t in closed_trades if t["outcome"] == "loss"]
    total = len(closed_trades)

    avg_win = (sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else None
    avg_loss = (sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else None
    avg_hold = (sum(t["hold_days"] for t in closed_trades) / total) if total else 0
    expectancy = (sum(t["pnl_ils"] for t in closed_trades) / total) if total else 0

    equities = [d["total_equity"] for d in daily_snapshots]
    ending = equities[-1] if equities else starting_cash
    total_return = ((ending - starting_cash) / starting_cash * 100) if starting_cash else 0

    max_dd = 0.0
    peak = equities[0] if equities else starting_cash
    for eq in equities:
        if eq > peak:
            peak = eq
        dd = (eq - peak) / peak * 100
        if dd < max_dd:
            max_dd = dd

    by_workflow: dict = {}
    for wf in ("technical-swing", "mean-reversion-bounce"):
        wf_trades = [t for t in closed_trades if t["workflow"] == wf]
        if not wf_trades:
            continue
        wf_wins = [t for t in wf_trades if t["outcome"] == "win"]
        by_workflow[wf] = {
            "trades": len(wf_trades),
            "win_rate_pct": round(len(wf_wins) / len(wf_trades) * 100, 1),
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in wf_trades) / len(wf_trades), 2),
        }

    return {
        "simulation_period": {
            "start": str(trading_calendar[0]) if trading_calendar else None,
            "end": str(trading_calendar[-1]) if trading_calendar else None,
        },
        "starting_capital_ils": starting_cash,
        "ending_equity_ils": round(ending, 2),
        "total_return_pct": round(total_return, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "total_trades": total,
        "wins": len(wins), "partials": len(partials), "losses": len(losses),
        "win_rate_pct": round(len(wins) / total * 100, 1) if total else 0,
        "avg_win_pct": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss_pct": round(avg_loss, 2) if avg_loss is not None else None,
        "avg_hold_days": round(avg_hold, 1),
        "expectancy_ils": round(expectancy, 2),
        "skipped_signals": skipped_signals,
        "by_workflow": by_workflow,
    }
