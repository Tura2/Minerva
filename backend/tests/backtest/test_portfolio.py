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
