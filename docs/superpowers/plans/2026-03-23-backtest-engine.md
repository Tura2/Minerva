# Backtest Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone local backtesting engine that replays 1 year of daily scans over 40 TASE watchlist symbols using the existing Minerva engine, managing a virtual 20,000 ILS portfolio with T1/T2/T3 scale-out exits, and writing results to CSV/JSON.

**Architecture:** A pure-Python script package at `backend/scripts/backtest/` with five focused modules — data_loader, portfolio, llm_cache, simulator, reporter — that call existing production services (`compute_indicators`, `pre_screen`, `OpenRouterClient`, `compute_position_size`) directly without modifying them. The simulator slices historical DataFrames to `df[df.index.normalize() <= D]` for point-in-time isolation and loops over the union of all symbol trading dates.

**Tech Stack:** Python 3.10+, yfinance, pandas, supabase-py, pytest (existing), existing backend services

**Spec:** `docs/superpowers/specs/2026-03-23-backtest-design.md`

---

## File Map

| File | Responsibility |
|---|---|
| `backend/scripts/__init__.py` | Makes scripts a package |
| `backend/scripts/backtest/__init__.py` | Makes backtest a package |
| `backend/scripts/backtest/__main__.py` | CLI entry point (`python -m scripts.backtest`) |
| `backend/scripts/backtest/data_loader.py` | Load symbols from Supabase; fetch & cache 2yr OHLC; build union trading calendar |
| `backend/scripts/backtest/portfolio.py` | Position state, cash/settlement accounting, scale-out exit logic |
| `backend/scripts/backtest/llm_cache.py` | JSON-backed cache for raw LLM results (keyed by symbol+date+workflow) |
| `backend/scripts/backtest/simulator.py` | Day-by-day loop: signal detection, entry resolution, exit processing |
| `backend/scripts/backtest/reporter.py` | Write backtest_trades.csv, backtest_daily_portfolio.csv, backtest_summary.json |
| `backend/tests/backtest/__init__.py` | Test package |
| `backend/tests/backtest/test_data_loader.py` | Unit tests for data_loader |
| `backend/tests/backtest/test_portfolio.py` | Unit tests for portfolio (all exit scenarios, tranche formula, T+2 settlement) |
| `backend/tests/backtest/test_llm_cache.py` | Unit tests for llm_cache |
| `backend/tests/backtest/test_simulator.py` | Unit tests for signal detection and entry resolution |
| `backend/tests/backtest/test_reporter.py` | Unit tests for CSV/JSON output |

---

## Task 1: Scaffold — Directory Structure + Packages

**Files:**
- Create: `backend/scripts/__init__.py`
- Create: `backend/scripts/backtest/__init__.py`
- Create: `backend/tests/backtest/__init__.py`

- [ ] **Step 1: Create directories and empty `__init__.py` files**

```bash
cd backend
mkdir -p scripts/backtest
mkdir -p tests/backtest
touch scripts/__init__.py scripts/backtest/__init__.py tests/backtest/__init__.py
```

- [ ] **Step 2: Verify pytest discovers the test directory**

```bash
cd backend
python -m pytest tests/backtest/ --collect-only 2>&1 | head -10
```

Expected: `no tests ran` (empty directory is fine — no collection error)

- [ ] **Step 3: Commit scaffold**

```bash
git add backend/scripts/ backend/tests/backtest/
git commit -m "feat(backtest): scaffold directory structure and packages"
```

---

## Task 2: `portfolio.py` — Position State & Cash Accounting

**Files:**
- Create: `backend/scripts/backtest/portfolio.py`
- Create: `backend/tests/backtest/test_portfolio.py`

### Background

`portfolio.py` tracks:
- `cash`: immediately debited on entry
- `settlement_queue`: list of `(amount_ils, settle_on)` — each exit's proceeds credited T+2
- `open_positions`: list of `Position` dataclasses
- Position scale-out uses tranche formula: T1 = `n // 3`, T2 = `n // 3`, T3 = `n - (n // 3) * 2`
- Trailing stop only updates at end-of-day (never intraday)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/test_portfolio.py`:

```python
from datetime import date, timedelta
import pytest
from scripts.backtest.portfolio import Portfolio, Position

TODAY = date(2025, 6, 15)
D2 = TODAY + timedelta(days=2)


def make_position(shares=12, entry_price=100.0, stop=90.0,
                  t1=115.0, t2=130.0, t3=150.0,
                  workflow="technical-swing") -> Position:
    return Position(
        symbol="TEST",
        workflow_type=workflow,
        entry_date=TODAY,
        entry_price=entry_price,
        fill_price=entry_price,  # actual fill == ticket entry_price in this fixture
        shares_total=shares,
        shares_remaining=shares,
        cost_basis=entry_price * shares,
        stop_loss=stop,
        t1=t1, t2=t2, t3=t3,
        t1_hit=False, t2_hit=False,
        verdict="Buy", setup_score=40, entry_rationale="test",
    )


# ── Starting state ───────────────────────────────────────────────────────────

def test_initial_state():
    p = Portfolio(starting_cash=20000.0)
    assert p.cash == 20000.0
    assert p.open_positions == []
    assert p.settlement_queue == []


# ── T+2 settlement ───────────────────────────────────────────────────────────

def test_settle_pending_credits_on_correct_day():
    p = Portfolio(starting_cash=1000.0)
    p.settlement_queue.append((500.0, D2))
    p.settle_pending(TODAY)      # too early — nothing credited
    assert p.cash == 1000.0
    p.settle_pending(D2)         # exactly on settle day
    assert p.cash == 1500.0


def test_settle_pending_clears_queue():
    p = Portfolio(starting_cash=0.0)
    p.settlement_queue.append((100.0, D2))
    p.settle_pending(D2)
    assert p.settlement_queue == []


# ── Entry ────────────────────────────────────────────────────────────────────

def test_enter_position_debits_cash_immediately():
    p = Portfolio(starting_cash=5000.0)
    pos = make_position(shares=10, entry_price=100.0)  # cost = 1000
    p.enter_position(pos)
    assert p.cash == 4000.0
    assert len(p.open_positions) == 1


def test_can_enter_returns_false_when_cash_insufficient():
    p = Portfolio(starting_cash=500.0)
    assert not p.can_enter(1000.0)


def test_can_enter_returns_true_when_cash_sufficient():
    p = Portfolio(starting_cash=5000.0)
    assert p.can_enter(1000.0)


# ── Tranche formula ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("n,t1,t2,t3", [
    (12, 4, 4, 4),
    (10, 3, 3, 4),
    (7,  2, 2, 3),
    (3,  1, 1, 1),
])
def test_tranche_formula(n, t1, t2, t3):
    from scripts.backtest.portfolio import tranches
    result = tranches(n)
    assert result == (t1, t2, t3)
    assert sum(result) == n


# ── Scale-out: T1 ─────────────────────────────────────────────────────────────

def test_t1_hit_sells_first_tranche_and_trails_stop(tmp_path):
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, stop=90.0,
                        t1=115.0, t2=130.0, t3=150.0)
    p.enter_position(pos)
    events = p.process_position_day(pos, day_high=120.0, day_low=112.0, day=TODAY)
    assert any(e["type"] == "T1" for e in events)
    t1_evt = next(e for e in events if e["type"] == "T1")
    assert t1_evt["shares"] == 4   # 12 // 3
    assert t1_evt["price"] == 115.0
    assert pos.t1_hit is True
    assert pos.stop_loss == 100.0  # trailed to fill_price (breakeven)
    assert pos.shares_remaining == 8


def test_t2_hit_after_t1_trails_to_t1():
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, t1=115.0, t2=130.0, t3=150.0)
    pos.t1_hit = True
    pos.shares_remaining = 8
    pos.stop_loss = 100.0  # already trailed to fill_price
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=135.0, day_low=128.0, day=TODAY)
    assert any(e["type"] == "T2" for e in events)
    t2_evt = next(e for e in events if e["type"] == "T2")
    assert t2_evt["shares"] == 4
    assert t2_evt["price"] == 130.0
    assert pos.t2_hit is True
    assert pos.stop_loss == 115.0  # trailed to T1


def test_t3_hit_closes_position():
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, t1=115.0, t2=130.0, t3=150.0)
    pos.t1_hit = True
    pos.t2_hit = True
    pos.shares_remaining = 4
    pos.stop_loss = 115.0
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=155.0, day_low=148.0, day=TODAY)
    assert any(e["type"] == "T3" for e in events)
    assert pos.shares_remaining == 0


def test_t1_t2_t3_all_hit_same_day():
    """All three targets hit in one day — T1, T2, T3 all exit same bar."""
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, stop=90.0,
                        t1=115.0, t2=130.0, t3=150.0)
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=160.0, day_low=112.0, day=TODAY)
    types = [e["type"] for e in events]
    assert "T1" in types
    assert "T2" in types
    assert "T3" in types
    assert pos.shares_remaining == 0
    # Verify tranche sizes sum to total
    total_sold = sum(e["shares"] for e in events)
    assert total_sold == 12


# ── Scale-out: stop ───────────────────────────────────────────────────────────

def test_stop_hit_sells_all_remaining():
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, stop=90.0)
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=95.0, day_low=88.0, day=TODAY)
    stop_evt = next(e for e in events if e["type"] == "stop")
    assert stop_evt["shares"] == 12
    assert stop_evt["price"] == 90.0
    assert pos.shares_remaining == 0


def test_t1_and_stop_same_day_t1_wins_for_tranche():
    """T1 tranche exits at T1; remaining exits at pre-T1 stop (not trailing stop)."""
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, stop=90.0,
                        t1=115.0, t2=130.0, t3=150.0)
    p.open_positions.append(pos)
    # day_high reaches T1, day_low also pierces original stop
    events = p.process_position_day(pos, day_high=118.0, day_low=88.0, day=TODAY)
    types = [e["type"] for e in events]
    assert "T1" in types
    assert "stop" in types
    t1_evt = next(e for e in events if e["type"] == "T1")
    stop_evt = next(e for e in events if e["type"] == "stop")
    assert t1_evt["shares"] == 4
    assert stop_evt["price"] == 90.0  # pre-T1 stop, NOT 100.0 (trailing)
    assert stop_evt["shares"] == 8
    assert pos.shares_remaining == 0


def test_t2_and_stop_same_day_stop_wins():
    """T2+stop same day: stop fills first for all remaining shares."""
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, t1=115.0, t2=130.0, t3=150.0)
    pos.t1_hit = True
    pos.shares_remaining = 8
    pos.stop_loss = 100.0  # trailed to breakeven
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=132.0, day_low=98.0, day=TODAY)
    # stop wins for T2 conflicts
    types = [e["type"] for e in events]
    assert "stop" in types
    assert "T2" not in types
    stop_evt = next(e for e in events if e["type"] == "stop")
    assert stop_evt["shares"] == 8
    assert pos.shares_remaining == 0


def test_breakout_not_filled_no_stop_out():
    """If entry never triggered (breakout unmet), no stop-out possible."""
    # This is an entry-resolution concern — portfolio never sees position
    # This test documents the contract: position only exists post-fill
    p = Portfolio(starting_cash=5000.0)
    assert len(p.open_positions) == 0
    # No positions → process_position_day is never called → no events
    assert p.open_positions == []


# ── Settlement queue populated on exits ───────────────────────────────────────

def test_exit_adds_to_settlement_queue():
    p = Portfolio(starting_cash=0.0)
    pos = make_position(shares=12, entry_price=100.0, stop=90.0,
                        t1=115.0, t2=130.0, t3=150.0)
    p.open_positions.append(pos)
    events = p.process_position_day(pos, day_high=120.0, day_low=112.0, day=TODAY)
    # T1 hit → settlement_queue should have entry for D+2
    assert len(p.settlement_queue) == 1
    amount, settle_on = p.settlement_queue[0]
    assert settle_on == TODAY + timedelta(days=2)
    assert amount == pytest.approx(4 * 115.0)  # 4 shares × T1 price
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
cd backend
python -m pytest tests/backtest/test_portfolio.py -v --no-cov 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'scripts.backtest.portfolio'`

- [ ] **Step 3: Implement `portfolio.py`**

Create `backend/scripts/backtest/portfolio.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd backend
python -m pytest tests/backtest/test_portfolio.py -v --no-cov
```

Expected: all 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/portfolio.py backend/tests/backtest/test_portfolio.py
git commit -m "feat(backtest): portfolio state machine with T+2 settlement and scale-out exits"
```

---

## Task 3: `llm_cache.py` — JSON-Backed LLM Result Cache

**Files:**
- Create: `backend/scripts/backtest/llm_cache.py`
- Create: `backend/tests/backtest/test_llm_cache.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/test_llm_cache.py`:

```python
from datetime import date
from pathlib import Path
import pytest
from scripts.backtest.llm_cache import LLMCache


SIGNAL_DATE = date(2025, 6, 15)
WORKFLOW = "technical-swing"
SYMBOL = "OPCE"

SAMPLE_TICKET = {
    "entry_price": 412.0,
    "entry_type": "breakout",
    "stop_loss": 385.0,
    "t1": 445.0,
    "t2": 480.0,
    "t3": 520.0,
    "verdict": "Strong Buy",
    "setup_score": 42,
    "entry_rationale": "Tight VCP above MA200",
}


def test_cache_miss_returns_none(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    assert cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW) is None


def test_store_and_retrieve(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    result = cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW)
    assert result == SAMPLE_TICKET


def test_cache_persists_across_instances(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache1 = LLMCache(cache_file=cache_file)
    cache1.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    cache2 = LLMCache(cache_file=cache_file)
    assert cache2.get(SYMBOL, SIGNAL_DATE, WORKFLOW) == SAMPLE_TICKET


def test_cache_key_format(tmp_path):
    """Key must be {symbol}_{YYYY-MM-DD}_{workflow}."""
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    import json
    data = json.loads((tmp_path / "cache.json").read_text())
    expected_key = "OPCE_2025-06-15_technical-swing"
    assert expected_key in data


def test_different_workflows_different_keys(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json")
    cache.store(SYMBOL, SIGNAL_DATE, "technical-swing", {"entry_price": 412.0})
    cache.store(SYMBOL, SIGNAL_DATE, "mean-reversion-bounce", {"entry_price": 400.0})
    swing = cache.get(SYMBOL, SIGNAL_DATE, "technical-swing")
    mr = cache.get(SYMBOL, SIGNAL_DATE, "mean-reversion-bounce")
    assert swing["entry_price"] == 412.0
    assert mr["entry_price"] == 400.0


def test_no_cache_flag_always_returns_none(tmp_path):
    cache = LLMCache(cache_file=tmp_path / "cache.json", no_cache=True)
    cache.store(SYMBOL, SIGNAL_DATE, WORKFLOW, SAMPLE_TICKET)
    assert cache.get(SYMBOL, SIGNAL_DATE, WORKFLOW) is None
```

- [ ] **Step 2: Run tests — verify all fail**

```bash
cd backend
python -m pytest tests/backtest/test_llm_cache.py -v --no-cov 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `llm_cache.py`**

Create `backend/scripts/backtest/llm_cache.py`:

```python
"""JSON-backed cache for raw LLM results. Keyed by symbol + signal_date + workflow."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_CACHE_FILE = Path(__file__).parent / "cache" / "llm_cache.json"


class LLMCache:
    def __init__(
        self,
        cache_file: Path = DEFAULT_CACHE_FILE,
        no_cache: bool = False,
    ) -> None:
        self._file = Path(cache_file)
        self._no_cache = no_cache
        self._data: Dict[str, Any] = {}
        if not self._no_cache and self._file.exists():
            try:
                self._data = json.loads(self._file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("LLM cache load failed (%s) — starting fresh", exc)

    @staticmethod
    def _key(symbol: str, signal_date: date, workflow: str) -> str:
        return f"{symbol}_{signal_date.strftime('%Y-%m-%d')}_{workflow}"

    def get(self, symbol: str, signal_date: date, workflow: str) -> Optional[Dict[str, Any]]:
        if self._no_cache:
            return None
        return self._data.get(self._key(symbol, signal_date, workflow))

    def store(self, symbol: str, signal_date: date, workflow: str, data: Dict[str, Any]) -> None:
        key = self._key(symbol, signal_date, workflow)
        self._data[key] = data
        if not self._no_cache:
            self._file.parent.mkdir(parents=True, exist_ok=True)
            self._file.write_text(
                json.dumps(self._data, indent=2, default=str),
                encoding="utf-8",
            )
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd backend
python -m pytest tests/backtest/test_llm_cache.py -v --no-cov
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/llm_cache.py backend/tests/backtest/test_llm_cache.py
git commit -m "feat(backtest): JSON-backed LLM result cache with no-cache flag"
```

---

## Task 4: `data_loader.py` — OHLC Fetch, Cache, Trading Calendar

**Files:**
- Create: `backend/scripts/backtest/data_loader.py`
- Create: `backend/tests/backtest/test_data_loader.py`

### Background

`data_loader.py` responsibilities:
1. `load_symbols(supabase_url, supabase_key) → List[dict]` — query `watchlist_items` table, return `[{symbol, market}, ...]`; fail fast if < 5 symbols
2. `fetch_ohlc(symbol, period="2y") → pd.DataFrame` — yfinance download, normalize columns to lowercase, divide TASE close/open/high/low by 100 (agorot→ILS)
3. `load_all_ohlc(symbols, cache_dir) → Dict[str, pd.DataFrame]` — cached to JSON per symbol
4. `build_trading_calendar(ohlc_data) → List[date]` — union of all symbol date indexes, sorted
5. `slice_df(df, up_to_date) → pd.DataFrame` — tz-safe point-in-time slice

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/test_data_loader.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_data_loader.py -v --no-cov 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement `data_loader.py`**

Create `backend/scripts/backtest/data_loader.py`:

```python
"""Load watchlist symbols from Supabase, fetch & cache OHLC from yfinance."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

OHLC_COLS = ["open", "high", "low", "close", "volume"]


def normalize_ohlc(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Lowercase columns; divide price columns by 100 for TASE (agorot → ILS)."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df[[c for c in OHLC_COLS if c in df.columns]]
    if market.upper() == "TASE":
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df[col] = df[col] / 100.0
    return df.sort_index()


def fetch_ohlc(symbol: str, market: str, period: str = "2y") -> pd.DataFrame:
    """Download OHLC from yfinance. TASE symbols get .TA suffix."""
    ticker = f"{symbol}.TA" if market.upper() == "TASE" else symbol
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}")
    return normalize_ohlc(df, market)


def load_all_ohlc(
    symbols: List[Dict[str, str]],
    cache_dir: Path,
    period: str = "2y",
    refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """Fetch OHLC for all symbols, caching each to a JSON file."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, pd.DataFrame] = {}
    for item in symbols:
        sym, market = item["symbol"], item["market"]
        cache_file = cache_dir / f"{sym}_{market}.json"
        if not refresh and cache_file.exists():
            try:
                df = pd.read_json(cache_file)
                df.index = pd.to_datetime(df.index)
                result[sym] = df
                logger.debug("Loaded %s from cache", sym)
                continue
            except Exception as exc:
                logger.warning("Cache load failed for %s: %s — re-fetching", sym, exc)
        try:
            df = fetch_ohlc(sym, market, period=period)
            df.to_json(cache_file)
            result[sym] = df
            logger.info("Fetched %s (%d bars)", sym, len(df))
        except Exception as exc:
            logger.error("Failed to fetch %s: %s — skipping", sym, exc)
    return result


def build_trading_calendar(ohlc_data: Dict[str, pd.DataFrame]) -> List[date]:
    """Union of all symbol date indexes → sorted list of unique trading dates."""
    all_dates: set[date] = set()
    for df in ohlc_data.values():
        for ts in df.index:
            all_dates.add(pd.Timestamp(ts).normalize().date())
    return sorted(all_dates)


def slice_df(df: pd.DataFrame, up_to_date: date) -> pd.DataFrame:
    """Point-in-time slice: include only bars on or before up_to_date.
    Handles tz-aware indexes (yfinance returns Asia/Jerusalem for TASE).
    """
    if df.empty:
        return df
    normalized = df.index.normalize()
    mask = normalized <= pd.Timestamp(up_to_date)
    return df.loc[mask]


def load_symbols(supabase_url: str, supabase_key: str) -> List[Dict[str, str]]:
    """Load watchlist symbols from Supabase. Fails fast if < 5 symbols."""
    from supabase import create_client
    client = create_client(supabase_url, supabase_key)
    response = client.table("watchlist_items").select("symbol, market").execute()
    symbols = [{"symbol": r["symbol"], "market": r["market"]} for r in response.data]
    if len(symbols) < 5:
        raise RuntimeError(
            f"Only {len(symbols)} symbols loaded from Supabase — need at least 5 to run backtest"
        )
    logger.info("Loaded %d symbols from Supabase", len(symbols))
    return symbols
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd backend
python -m pytest tests/backtest/test_data_loader.py -v --no-cov
```

Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/data_loader.py backend/tests/backtest/test_data_loader.py
git commit -m "feat(backtest): data_loader — OHLC fetch, cache, trading calendar, tz-safe slice"
```

---

## Task 5: `simulator.py` — Signal Detection & Entry Resolution

**Files:**
- Create: `backend/scripts/backtest/simulator.py` (partial — signal detection only)
- Create: `backend/tests/backtest/test_simulator.py`

### Background

`detect_signals(symbol, market, df_slice, indicators, mr_indicators, open_symbols)` returns a list of `{workflow, indicators, mr_indicators, pre_screen_result}` dicts — one per workflow that passed pre-screen. If both pass, only `technical-swing` is returned.

`resolve_entry(entry_type, entry_price, d1_open, d1_high)` returns the actual fill price or `None` if entry not triggered.

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/test_simulator.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_simulator.py -v --no-cov 2>&1 | tail -5
```

Expected: `ModuleNotFoundError`

- [ ] **Step 3: Implement signal detection in `simulator.py`**

Create `backend/scripts/backtest/simulator.py`:

```python
"""Day-by-day simulation loop — signal detection, entry resolution, exit processing."""

from __future__ import annotations

import logging
from datetime import date
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
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd backend
python -m pytest tests/backtest/test_simulator.py -v --no-cov
```

Expected: 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/simulator.py backend/tests/backtest/test_simulator.py
git commit -m "feat(backtest): simulator signal detection and entry resolution"
```

---

## Task 6: `reporter.py` — CSV + JSON Output

**Files:**
- Create: `backend/scripts/backtest/reporter.py`
- Create: `backend/tests/backtest/test_reporter.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/backtest/test_reporter.py`:

```python
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
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_reporter.py -v --no-cov 2>&1 | tail -5
```

- [ ] **Step 3: Implement `reporter.py`**

Create `backend/scripts/backtest/reporter.py`:

```python
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
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
cd backend
python -m pytest tests/backtest/test_reporter.py -v --no-cov
```

Expected: 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/reporter.py backend/tests/backtest/test_reporter.py
git commit -m "feat(backtest): reporter — CSV and JSON output writers"
```

---

## Task 7: `simulator.py` — Full Day Loop + LLM Integration

**Files:**
- Modify: `backend/scripts/backtest/simulator.py` (add `run_backtest()` and `_call_llm()`)
- Modify: `backend/tests/backtest/test_simulator.py` (add loop integration tests)

### Background

`run_backtest()` wires everything together:
1. Call `settle_pending()` at start of each day
2. Get mark-to-market close prices for all open positions
3. Detect signals for each unopen symbol
4. For each signal: check LLM cache → call LLM if miss → validate ticket → resolve entry on D+1 → enter position if cash available
5. For each open position: call `process_position_day()` with D+1 OHLC → record exits
6. Record daily portfolio snapshot

`_call_llm()` calls `OpenRouterClient` with the appropriate prompt builder (swing vs MR), extracts the ticket fields, and stores in LLM cache. The market breadth stub is a fixed neutral dict for TASE.

- [ ] **Step 1: Write failing integration tests for `run_backtest()`**

Append to `backend/tests/backtest/test_simulator.py`:

```python
# ── run_backtest integration (mocked) ─────────────────────────────────────────

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
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
    # LLM should NOT have been called (cache hit)
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
                result = run_backtest(
                    ohlc_data=OHLC_DATA, symbol_meta=META,
                    trading_calendar=DAYS[:4], cache=cache,
                    output_dir=tmp_path, dry_run=False,
                )
    assert result["skipped_signals"] >= 1
    assert result["total_trades"] == 0
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
cd backend
python -m pytest tests/backtest/test_simulator.py::test_dry_run_produces_signal_csv -v --no-cov 2>&1 | tail -5
```

Expected: `ImportError` or attribute error (functions not yet implemented)

- [ ] **Step 3: Add `run_backtest()` to `simulator.py`**

Append to `backend/scripts/backtest/simulator.py`:

```python
# ── Full backtest loop ────────────────────────────────────────────────────────

from datetime import timedelta

import pandas as pd

from app.config import settings
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

_PORTFOLIO_SIZE_FOR_PROMPT = 20_000.0   # cosmetic: LLM rationale only
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
        raw = client.research(prompt)
        return raw
    except Exception as exc:
        logger.error("LLM call failed for %s/%s: %s", symbol, workflow, exc)
        return None


def _extract_ticket(raw: dict) -> dict | None:
    """Extract and validate required ticket fields from LLM response."""
    required = ["entry_price", "entry_type", "stop_loss"]
    for field in required:
        if raw.get(field) is None:
            logger.warning("LLM ticket missing required field: %s", field)
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
    ohlc_data: dict,            # {symbol → pd.DataFrame (full 2yr)}
    symbol_meta: dict,          # {symbol → {"market": str}}
    trading_calendar: list,     # sorted list of date
    cache: LLMCache,
    output_dir,
    starting_cash: float = 20_000.0,
    dry_run: bool = False,
) -> dict:
    """Main backtest loop. Returns summary dict."""
    from pathlib import Path
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client = OpenRouterClient() if not dry_run else None
    portfolio = Portfolio(starting_cash=starting_cash)

    closed_trades: list[dict] = []
    daily_snapshots: list[dict] = []
    skipped_signals = 0
    dry_run_signals: list[dict] = []

    for i, day in enumerate(trading_calendar):
        # Settle T+2 proceeds from prior exits
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
        pending_entries: list[dict] = []  # entries to attempt on D+1

        # ── Signal detection ──────────────────────────────────────────────────
        for sym, df_full in ohlc_data.items():
            df_slice = slice_df(df_full, day)
            if len(df_slice) < 20:
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
                    dry_run_signals.append({"date": day, "symbol": sym, "workflow": workflow, "pre_screen_passed": True})
                    continue

                # LLM cache check
                ticket = cache.get(sym, day, workflow)
                if ticket is None:
                    raw = _call_llm(sym, market, workflow, indicators, mr_indicators, sig["pre_screen_result"], client)
                    if raw is None:
                        skipped_signals += 1
                        continue
                    ticket = _extract_ticket(raw)
                    if ticket is None:
                        skipped_signals += 1
                        continue
                    cache.store(sym, day, workflow, ticket)

                pending_entries.append({
                    "symbol": sym, "market": market, "workflow": workflow,
                    "ticket": ticket, "signal_date": day,
                })

        # ── Entry resolution (attempt entries on D+1) ─────────────────────────
        if i + 1 < len(trading_calendar):
            d1 = trading_calendar[i + 1]
            for pending in pending_entries:
                sym = pending["symbol"]
                ticket = pending["ticket"]
                df_d1 = slice_df(ohlc_data[sym], d1)
                if df_d1.empty:
                    continue
                d1_row = df_d1.iloc[-1]
                fill = resolve_entry(
                    ticket["entry_type"], ticket["entry_price"],
                    d1_open=float(df_d1["open"].iloc[-1]) if "open" in df_d1 else float(d1_row["close"]),
                    d1_high=float(d1_row["high"]) if "high" in d1_row.index else float(d1_row["close"]),
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

        # ── Exit processing (check positions against D+1 OHLC per spec) ──────
        # Exits are monitored on the trading day AFTER the current loop day.
        # Skip on last calendar day (no D+1 available).
        if i + 1 < len(trading_calendar):
            d1_exit = trading_calendar[i + 1]
            for pos in list(portfolio.open_positions):
                df_d1 = ohlc_data.get(pos.symbol, pd.DataFrame())
                # Get only the D+1 bar
                d1_rows = df_d1[df_d1.index.normalize() == pd.Timestamp(d1_exit)]
                if d1_rows.empty:
                    continue
                d1_row = d1_rows.iloc[-1]
                events = portfolio.process_position_day(
                    pos,
                    day_high=float(d1_row.get("high", d1_row["close"])),
                    day_low=float(d1_row.get("low", d1_row["close"])),
                    day=d1_exit,
                )
                if events:
                    new_exits += len(events)
                    if pos.shares_remaining == 0:
                        # Use accumulated exit_events (covers T1 from day 10, stop from day 20)
                        closed_trades.append(_summarize_trade(pos, pos.exit_events, d1_exit))

        # ── Daily snapshot ────────────────────────────────────────────────────
        daily_snapshots.append({
            "date": day, "cash": round(portfolio.cash, 2),
            "open_positions_value": round(portfolio.open_positions_value(close_prices), 2),
            "total_equity": round(portfolio.total_equity(close_prices), 2),
            "num_open_positions": len(portfolio.open_positions),
            "num_new_signals": new_signals, "num_entries": new_entries, "num_exits": new_exits,
        })

    # ── Dry-run output ────────────────────────────────────────────────────────
    if dry_run:
        import csv
        out = output_dir / "dry_run_signals.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "symbol", "workflow", "pre_screen_passed"])
            writer.writeheader()
            writer.writerows(dry_run_signals)
        logger.info("Dry-run complete — %d signals found → %s", len(dry_run_signals), out)
        return {"dry_run": True, "signals_found": len(dry_run_signals)}

    # ── Write output files ────────────────────────────────────────────────────
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
    """Build a closed-trade row for the CSV."""
    t1_events = [e for e in events if e["type"] == "T1"]
    t2_events = [e for e in events if e["type"] == "T2"]
    t3_events = [e for e in events if e["type"] == "T3"]
    stop_events = [e for e in events if e["type"] == "stop"]

    total_proceeds = sum(
        e["shares"] * e["price"] for e in events
    )
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
        "rs_rank_pct": None,  # always null in backtest
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

    # max drawdown: peak-to-trough of equity curve
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
```

- [ ] **Step 4: Run all existing tests — verify nothing broken**

```bash
cd backend
python -m pytest tests/backtest/ -v --no-cov
```

Expected: all previously passing tests still PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/simulator.py
git commit -m "feat(backtest): full day-loop simulation — LLM integration, entry/exit orchestration, summary stats"
```

---

## Task 8: `__main__.py` — CLI Entry Point

**Files:**
- Create: `backend/scripts/backtest/__main__.py`

- [ ] **Step 1: Implement CLI**

Create `backend/scripts/backtest/__main__.py`:

```python
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
    symbols = load_symbols(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    logger.info("Loading OHLC data for %d symbols...", len(symbols))
    ohlc_data = load_all_ohlc(symbols, cache_dir=cache_dir)

    if not ohlc_data:
        logger.error("No OHLC data loaded — cannot run backtest")
        sys.exit(1)

    symbol_meta = {s["symbol"]: {"market": s["market"]} for s in symbols}
    trading_calendar = [d for d in build_trading_calendar(ohlc_data) if start <= d <= end]

    logger.info(
        "Running backtest: %s → %s (%d trading days, %d symbols, %.0f ILS capital)",
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
```

- [ ] **Step 2: Test CLI help works**

```bash
cd backend
python -m scripts.backtest --help
```

Expected: usage message printed with all flags listed

- [ ] **Step 3: Verify arg-parsing module imports cleanly**

```bash
cd backend
python -c "from scripts.backtest.__main__ import parse_args; args = parse_args([]); print(args.capital)"
```

Expected: `20000.0` (default capital printed without error)

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/backtest/__main__.py
git commit -m "feat(backtest): CLI entry point with --start-date, --end-date, --capital, --no-cache, --dry-run"
```

---

## Task 9: Integration — Dry-Run Smoke Test

**Goal:** Verify the full pipeline runs end-to-end against real Supabase + yfinance data in `--dry-run` mode (no LLM calls, no spend).

- [ ] **Step 1: Verify `.env.local` has Supabase credentials**

```bash
cd backend
grep "SUPABASE_URL\|SUPABASE_KEY" .env 2>/dev/null || grep "SUPABASE" .env.local 2>/dev/null
```

Expected: both keys present

- [ ] **Step 2: Run dry-run smoke test**

```bash
cd backend
python -m scripts.backtest --dry-run --start-date 2025-03-01 --end-date 2025-03-31
```

Expected output:
```
INFO backtest: Loading symbols from Supabase...
INFO backtest: Loading OHLC data for 40 symbols...
INFO backtest: Running backtest: 2025-03-01 → 2025-03-31 (N trading days, ...)
INFO backtest: Dry-run complete — N signals found → .../output/dry_run_signals.csv
```

- [ ] **Step 3: Inspect dry-run output**

```bash
head -5 backend/scripts/backtest/output/dry_run_signals.csv
```

Expected: CSV with columns `date,symbol,workflow,pre_screen_passed` and at least some rows

- [ ] **Step 4: Run full test suite**

```bash
cd backend
python -m pytest tests/backtest/ -v --no-cov
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/backtest/output/.gitkeep backend/scripts/backtest/cache/.gitkeep
git commit -m "feat(backtest): integration smoke test passes — dry-run end-to-end verified"
```

---

## Task 10: Full Backtest Run (1-Year, Real LLM Calls)

**Goal:** Execute the full 1-year backtest with real LLM calls. Results cached so re-runs are free.

- [ ] **Step 1: Ensure OpenRouter API key is set**

```bash
cd backend
grep "OPENROUTER_API_KEY" .env 2>/dev/null || echo "missing — add to .env"
```

- [ ] **Step 2: Start the full backtest (will take 30-60 min depending on signals found)**

```bash
cd backend
python -m scripts.backtest --capital 20000
```

Monitor logs for signal counts and any LLM errors.

- [ ] **Step 3: Inspect results**

```bash
# Summary
cat backend/scripts/backtest/output/backtest_summary.json

# Trade count
wc -l backend/scripts/backtest/output/backtest_trades.csv

# First 5 trades
head -6 backend/scripts/backtest/output/backtest_trades.csv
```

- [ ] **Step 4: Re-run with different capital to verify LLM cache works (no new API calls)**

```bash
cd backend
python -m scripts.backtest --capital 15000
```

Expected: runs much faster (all LLM results served from cache)

- [ ] **Step 5: Commit output directory structure (not data files)**

```bash
# Ignore LLM cache and OHLC cache files (ohlc/ is a subdirectory — use **)
echo "**/*.json" > backend/scripts/backtest/cache/.gitignore
echo "*.csv" >> backend/scripts/backtest/output/.gitignore
echo "*.json" >> backend/scripts/backtest/output/.gitignore
touch backend/scripts/backtest/cache/.gitkeep
touch backend/scripts/backtest/output/.gitkeep
git add backend/scripts/backtest/cache/ backend/scripts/backtest/output/
git commit -m "chore(backtest): add .gitignore for cache (including ohlc/) and output files"
```
