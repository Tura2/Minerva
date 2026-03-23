"""Portfolio state machine — positions, cash, T+2 settlement, scale-out exits."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple


def tranches(n: int) -> Tuple[int, int, int]:
    """Return (T1_shares, T2_shares, T3_shares) for n total shares.
    T3 absorbs integer rounding: T3 = n - (n // 3) * 2.
    """
    t = n // 3
    return t, t, n - t * 2


@dataclass
class Position:
    symbol: str
    workflow_type: str
    entry_date: date
    entry_price: float       # LLM-specified entry price
    fill_price: float        # actual fill (D+1 open for "current", entry_price for "breakout")
    shares_total: int
    shares_remaining: int
    cost_basis: float        # fill_price × shares_total
    stop_loss: float
    t1: float
    t2: float
    t3: float
    t1_hit: bool = False
    t2_hit: bool = False
    # research metadata (from LLM cache)
    verdict: str = ""
    setup_score: int = 0
    entry_rationale: str = ""
    # accumulated exit events across all days (needed for multi-day P&L summarization)
    exit_events: list = field(default_factory=list)


@dataclass
class Portfolio:
    starting_cash: float = 20_000.0
    cash: float = field(init=False)
    open_positions: List[Position] = field(default_factory=list)
    settlement_queue: List[Tuple[float, date]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cash = self.starting_cash

    # ── Settlement ───────────────────────────────────────────────────────────

    def settle_pending(self, today: date) -> None:
        """Credit all settlements due on or before today."""
        due = [(amt, d) for amt, d in self.settlement_queue if d <= today]
        for item in due:
            self.cash += item[0]
            self.settlement_queue.remove(item)

    def _queue_settlement(self, amount: float, exit_date: date) -> None:
        """Queue an exit credit for T+2 settlement."""
        self.settlement_queue.append((amount, exit_date + timedelta(days=2)))

    # ── Entry ────────────────────────────────────────────────────────────────

    @property
    def available_cash(self) -> float:
        return self.cash

    def can_enter(self, cost: float) -> bool:
        return self.available_cash >= cost

    def enter_position(self, pos: Position) -> None:
        """Debit cash immediately (entry is T+0)."""
        self.cash -= pos.cost_basis
        self.open_positions.append(pos)

    # ── Exit processing ───────────────────────────────────────────────────────

    def process_position_day(
        self,
        pos: Position,
        day_high: float,
        day_low: float,
        day: date,
    ) -> List[Dict[str, Any]]:
        """
        Process one trading day for an open position.
        Returns list of exit events (type, shares, price, date).
        Trailing stop state updates at end-of-day (never intraday).
        """
        events: List[Dict[str, Any]] = []
        t1_sz, t2_sz, _ = tranches(pos.shares_total)

        # ── T1 not yet hit ────────────────────────────────────────────────────
        if not pos.t1_hit and day_high >= pos.t1:
            original_stop = pos.stop_loss  # capture before any trailing update
            events.append({"type": "T1", "shares": t1_sz, "price": pos.t1, "date": day})
            self._queue_settlement(t1_sz * pos.t1, day)
            pos.shares_remaining -= t1_sz
            pos.t1_hit = True

            # T1 + stop same day → T1 filled first; remaining exits at pre-T1 stop
            if day_low <= original_stop:
                events.append({
                    "type": "stop", "shares": pos.shares_remaining,
                    "price": original_stop, "date": day,
                })
                self._queue_settlement(pos.shares_remaining * original_stop, day)
                pos.shares_remaining = 0
                self._remove_closed(pos)
                return self._return_events(pos, events)

            # Trail stop to fill_price (breakeven) — end-of-day update
            pos.stop_loss = pos.fill_price

            # Check T2 same day (T2 hit after T1 on same day)
            if day_high >= pos.t2:
                # T2 + stop same day → stop wins
                if day_low <= pos.stop_loss:
                    events.append({
                        "type": "stop", "shares": pos.shares_remaining,
                        "price": pos.stop_loss, "date": day,
                    })
                    self._queue_settlement(pos.shares_remaining * pos.stop_loss, day)
                    pos.shares_remaining = 0
                    self._remove_closed(pos)
                    return self._return_events(pos, events)
                events.append({"type": "T2", "shares": t2_sz, "price": pos.t2, "date": day})
                self._queue_settlement(t2_sz * pos.t2, day)
                pos.shares_remaining -= t2_sz
                pos.t2_hit = True
                pos.stop_loss = pos.t1  # trail to T1
                # Check T3 same day
                if day_high >= pos.t3:
                    events.append({
                        "type": "T3", "shares": pos.shares_remaining,
                        "price": pos.t3, "date": day,
                    })
                    self._queue_settlement(pos.shares_remaining * pos.t3, day)
                    pos.shares_remaining = 0
                    self._remove_closed(pos)
                    return self._return_events(pos, events)

            return self._return_events(pos, events)  # T1 only (or T1+T2 without T3)

        # ── T1 hit, T2 not yet hit ─────────────────────────────────────────────
        if pos.t1_hit and not pos.t2_hit:
            if day_high >= pos.t2:
                # T2 + stop same day → stop wins for all remaining
                if day_low <= pos.stop_loss:
                    events.append({
                        "type": "stop", "shares": pos.shares_remaining,
                        "price": pos.stop_loss, "date": day,
                    })
                    self._queue_settlement(pos.shares_remaining * pos.stop_loss, day)
                    pos.shares_remaining = 0
                    self._remove_closed(pos)
                    return self._return_events(pos, events)
                events.append({"type": "T2", "shares": t2_sz, "price": pos.t2, "date": day})
                self._queue_settlement(t2_sz * pos.t2, day)
                pos.shares_remaining -= t2_sz
                pos.t2_hit = True
                pos.stop_loss = pos.t1
                # Check T3 same day
                if day_high >= pos.t3:
                    events.append({
                        "type": "T3", "shares": pos.shares_remaining,
                        "price": pos.t3, "date": day,
                    })
                    self._queue_settlement(pos.shares_remaining * pos.t3, day)
                    pos.shares_remaining = 0
                    self._remove_closed(pos)
                    return self._return_events(pos, events)
                return self._return_events(pos, events)

        # ── T1+T2 hit, T3 not yet hit ─────────────────────────────────────────
        if pos.t1_hit and pos.t2_hit and day_high >= pos.t3:
            events.append({
                "type": "T3", "shares": pos.shares_remaining,
                "price": pos.t3, "date": day,
            })
            self._queue_settlement(pos.shares_remaining * pos.t3, day)
            pos.shares_remaining = 0
            self._remove_closed(pos)
            return self._return_events(pos, events)

        # ── Stop check (no target hit) ─────────────────────────────────────────
        if pos.shares_remaining > 0 and day_low <= pos.stop_loss:
            events.append({
                "type": "stop", "shares": pos.shares_remaining,
                "price": pos.stop_loss, "date": day,
            })
            self._queue_settlement(pos.shares_remaining * pos.stop_loss, day)
            pos.shares_remaining = 0
            self._remove_closed(pos)

        return self._return_events(pos, events)

    def _return_events(self, pos: Position, events: list) -> list:
        """Accumulate events on pos and return them. Use instead of bare `return events`."""
        pos.exit_events.extend(events)
        return events

    def _remove_closed(self, pos: Position) -> None:
        if pos in self.open_positions:
            self.open_positions.remove(pos)

    def open_positions_value(self, close_prices: Dict[str, float]) -> float:
        """Mark-to-market value of all open positions at day close prices."""
        return sum(
            close_prices.get(pos.symbol, pos.fill_price) * pos.shares_remaining
            for pos in self.open_positions
        )

    def total_equity(self, close_prices: Dict[str, float]) -> float:
        return self.cash + self.open_positions_value(close_prices)
