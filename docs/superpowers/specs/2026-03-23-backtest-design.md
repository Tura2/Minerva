# Minerva Local Backtest Engine — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Standalone Python backtest script that replays 1 year of daily scans over the TASE watchlist using the existing Minerva engine

---

## 1. Overview

A local backtest tool that simulates the Minerva trading engine over historical data. It fetches 2 years of OHLC history for all TASE watchlist symbols, then replays daily scanning from 1 year ago to today — running both `technical-swing` and `mean-reversion-bounce` workflows, managing a virtual 20,000 ILS portfolio, and writing detailed trade + performance output to CSV/JSON files.

**Goals:**
- Measure engine win rate, average P&L, and total return over a 1-year simulation
- Validate that pre-screen gates, LLM signals, and scale-out exits work as designed
- Produce per-trade research details (entry rationale, setup score, verdict, RS rank)
- Re-run cheaply via LLM result caching

**Non-goals (v1):**
- UI for results (CSV/JSON output only)
- Multi-user or scheduled runs
- US market symbols
- Slippage or commission modeling

---

## 2. File Structure

```
backend/scripts/backtest/
├── __main__.py         # Entry point: python -m scripts.backtest
├── data_loader.py      # Fetch & cache 2yr OHLC for all 40 TASE symbols
├── simulator.py        # Day-by-day loop — signal detection, entry/exit
├── portfolio.py        # Position tracker — cash, open trades, scale-out state
├── llm_cache.py        # Persist LLM results to JSON (re-run at zero cost)
└── reporter.py         # Write output CSV + JSON files

backend/scripts/backtest/cache/
└── llm_cache.json      # Persisted LLM call results (keyed by symbol+date+workflow)

backend/scripts/backtest/output/
├── backtest_trades.csv
├── backtest_daily_portfolio.csv
└── backtest_summary.json
```

---

## 3. Data Flow

```
Supabase watchlist (40 TASE symbols)
        ↓
data_loader  →  2yr OHLC per symbol (yfinance, cached to local JSON)
        ↓
simulator loops day D from (today−1yr) → today
    ┌── for each symbol not already in open position:
    │       df_slice = full_df[:D]             # point-in-time — no lookahead
    │       compute_indicators(df_slice)
    │       pre_screen()                        # technical-swing gate
    │       pre_screen_mean_reversion()         # MR gate
    │       if signal + cash available:
    │           llm_cache hit? → reuse ticket
    │                    miss? → OpenRouter call → store in cache
    │           resolve entry (current=D+1 open, breakout=if D+1 high ≥ entry_price)
    │
    └── for each open position:
            check T1/T2/T3 vs D+1 high
            check stop_loss vs D+1 low
            apply trailing stop logic
            update cash + position state
        ↓
reporter  →  backtest_trades.csv
             backtest_daily_portfolio.csv
             backtest_summary.json
```

**Code reuse (no changes to production files):**
- `app.services.indicators.compute_indicators()` — fed sliced DataFrame
- `app.services.indicators.compute_mean_reversion_indicators()` — same
- `app.services.pre_screen.pre_screen()` — fed indicators dict
- `app.services.pre_screen.pre_screen_mean_reversion()` — same
- `app.services.prompts.build_research_prompt()` — fed indicators dict
- `app.services.prompts_mean_reversion` — same
- `app.services.openrouter_client.OpenRouterClient` — same instance

---

## 4. Portfolio & Trade Lifecycle

### Starting state
```
cash = 20,000 ILS
open_positions = []
```

### Entry logic

Signal fires on day D → attempt entry on day D+1:

| Entry type | Condition to fill | Fill price |
|---|---|---|
| `current` | Always | D+1 open price |
| `breakout` | D+1 high ≥ entry_price | entry_price exactly |

If `available_cash < cost_basis` → signal skipped, logged as `skipped: insufficient_cash`.

If both `technical-swing` and `mean-reversion-bounce` trigger for the same symbol on the same day → prefer `technical-swing` (more mature workflow).

### Position state
```python
symbol: str
workflow_type: str
entry_date: date
entry_price: float
shares_total: int          # from ticket.position_size
shares_remaining: int      # reduces at each scale-out
cost_basis: float          # entry_price × shares_total
stop_loss: float           # updates as trailing stop moves
t1: float                  # scale-out target 1
t2: float                  # scale-out target 2
t3: float                  # scale-out target 3
t1_hit: bool
t2_hit: bool
# research metadata
verdict: str
setup_score: int
rs_rank_pct: float
entry_rationale: str
```

### Scale-out logic (checked against D+1 intraday high/low each day)

```
T1 hit (day_high ≥ t1 and not t1_hit):
    sell shares_total // 3 at T1
    trail stop → entry_price (breakeven)
    t1_hit = True

T2 hit (day_high ≥ t2 and t1_hit and not t2_hit):
    sell shares_total // 3 at T2
    trail stop → T1
    t2_hit = True

T3 hit (day_high ≥ t3 and t2_hit):
    sell shares_remaining at T3
    close position

Stop hit (day_low ≤ stop_loss):
    sell shares_remaining at stop_loss
    close position (partial loss if T1/T2 already hit)

Conflict (T2 or T3 and stop hit same day):
    stop fills first — entire remaining position exits at stop_loss
    (T2/T3 price never reached in settlement sense)

Conflict (T1 and stop hit same day):
    → governed by Section 9 edge case rule:
      T1 tranche (n // 3 shares) exits at T1; remaining exits at pre-T1 stop
```

### Cash accounting
```
On entry:    cash -= entry_price × shares_total            (immediate)
On T1 exit:  settlement_queue += (t1 × (shares_total // 3), settle_on=D+2)
On T2 exit:  settlement_queue += (t2 × (shares_total // 3), settle_on=D+2)
On T3 exit:  settlement_queue += (t3 × shares_remaining,    settle_on=D+2)
On stop:     settlement_queue += (stop_loss × shares_remaining, settle_on=D+2)

# Each morning: cash += all settlements due on day D (TASE T+2)
# available_cash = cash + sum(settlements due ≤ D)
```
Note: entry debit is immediate (order placed); exit credits settle T+2 per TASE rules.

---

## 5. LLM Cache

**File:** `backend/scripts/backtest/cache/llm_cache.json`

**Cache key:** `"{symbol}_{YYYY-MM-DD}_{workflow_type}"`
Example: `"OPCE_2025-06-15_technical-swing"`

**Cached fields (raw LLM output only — no position_size, no RS rank):**
```json
{
  "entry_price": 412.0,
  "entry_type": "breakout",
  "stop_loss": 385.0,
  "t1": 445.0,
  "t2": 480.0,
  "t3": 520.0,
  "verdict": "Strong Buy",
  "setup_score": 42,
  "entry_rationale": "...",
  "cached_at": "2026-03-23T10:00:00Z"
}
```

`position_size` is **not cached** — it is re-computed each time using current portfolio equity at day D so that re-runs with different capital work correctly. `rs_rank_pct` is **not cached** — it is always `null` in backtest output (RS is skipped to avoid lookahead bias).

On cache hit: skip OpenRouter call entirely.
On cache miss: call OpenRouter → validate → store → use.

This allows re-running the backtest with different portfolio rules (capital, scale-out fractions) at zero additional LLM cost.

---

## 6. Output Files

All files written to `backend/scripts/backtest/output/`.

### `backtest_trades.csv`
One row per **closed** trade:

| Column | Description |
|---|---|
| symbol | TASE symbol |
| workflow | `technical-swing` or `mean-reversion-bounce` |
| entry_date | Date position opened |
| exit_date | Date position fully closed |
| hold_days | Calendar days held |
| entry_price | Actual fill price |
| exit_t1 / exit_t2 / exit_t3 | Fill prices at each scale-out (blank if not hit) |
| exit_stop | Stop fill price if triggered |
| shares_t1 / shares_t2 / shares_t3 / shares_stopped | Shares sold at each exit |
| pnl_ils | Total realized P&L in ILS |
| pnl_pct | % return on cost basis |
| outcome | `win` (T3 hit), `partial` (T1 or T2 hit, then stopped), `loss` (stopped before T1) |
| verdict | LLM verdict field |
| setup_score | Synthesized setup score (0-60) |
| rs_rank_pct | RS percentile rank at signal date |
| entry_rationale | LLM entry rationale (truncated to 200 chars) |

### `backtest_daily_portfolio.csv`
One row per trading day:

| Column | Description |
|---|---|
| date | Trading day |
| cash | Available cash ILS |
| open_positions_value | Mark-to-market value of open positions (at day close) |
| total_equity | cash + open_positions_value |
| num_open_positions | Count of open trades |
| num_new_signals | Signals fired that day |
| num_entries | Entries filled that day |
| num_exits | Exits (full or partial) that day |

### `backtest_summary.json`
Aggregate statistics:

```json
{
  "simulation_period": { "start": "2025-03-23", "end": "2026-03-23" },
  "starting_capital_ils": 20000,
  "ending_equity_ils": 23680,
  "total_return_pct": 18.4,
  "max_drawdown_pct": -12.1,
  "total_trades": 42,
  "wins": 28,
  "partials": 6,
  "losses": 8,
  "win_rate_pct": 66.7,
  "avg_win_pct": 14.2,
  "avg_loss_pct": -6.1,
  "avg_hold_days": 18.3,
  "expectancy_ils": 380.0,
  "skipped_signals": 12,
  "by_workflow": {
    "technical-swing": {
      "trades": 28,
      "win_rate_pct": 71.4,
      "avg_pnl_pct": 10.2
    },
    "mean-reversion-bounce": {
      "trades": 14,
      "win_rate_pct": 57.1,
      "avg_pnl_pct": 7.8
    }
  }
}
```

---

## 7. Entry Point Usage

```bash
cd backend
python -m scripts.backtest

# Options (via CLI args or env vars):
# --start-date    Simulation start (default: today - 1yr)
# --end-date      Simulation end (default: today)
# --capital       Starting capital ILS (default: 20000)
# --no-cache      Ignore LLM cache, re-call everything
# --dry-run       Run pre-screen only, skip LLM calls (fast validation)
```

---

## 8. Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| LLM calls | Real OpenRouter calls | Full fidelity; cache makes re-runs free |
| Entry timing | D+1 (next day after signal) | Realistic — signal fires EOD, trade next morning |
| Breakout entry | Only if D+1 high ≥ entry_price | No fill if price gaps past without reaching level |
| Conflict resolution | Stop wins over target (same day) | Conservative assumption |
| Dual workflow on same symbol | Prefer technical-swing | Avoids double position; MR suppression is intentional and logged in output |
| Point-in-time isolation | `df[df.index.normalize() <= pd.Timestamp(D)]` | Handles tz-aware yfinance timestamps (Asia/Jerusalem) safely |
| Trading calendar | **Union** of all loaded symbols' date indexes | Every day any symbol has data is a candidate replay day; each symbol is skipped individually on days it has no bar (e.g., recent IPO, data gap); no risk of silently truncating the simulation window if one symbol has a shorter history |
| RS rank in backtest | Skipped (null) | Avoids lookahead bias; all backtest trades have `rs_rank_pct = null` |
| Market breadth | Neutral stub for all replay days | TASE returns neutral stub in production; eliminates live-data lookahead |
| Position sizing | Re-computed per trade from current equity at day D | Cache stores raw LLM fields only; sizing always reflects live portfolio state |
| LLM cache key date | Signal day D (not entry day D+1) | Deduplicates setup analysis, not the execution attempt |
| LLM cache contents | entry_price, entry_type, stop_loss, t1/t2/t3, verdict, setup_score, entry_rationale | Excludes position_size and rs_rank_pct; re-runs with different capital cost nothing |
| portfolio_size in LLM prompt | Fixed 20,000 ILS (starting capital) — cosmetic only | LLM rationale text uses this value; actual position sizing is re-computed independently from current equity |
| Share tranche formula | T1 = `n // 3`; T2 = `n // 3`; T3 = `n - (n // 3) * 2` | Explicit formula; T3 absorbs rounding; no share count drift across hundreds of trades |
| Trailing stop state update timing | End-of-day only; same-day T1+stop uses pre-T1 stop level | Cannot infer intraday order from daily OHLC; trailing state never activates within the same day T1 fires |
| Trailing stop price basis | Actual fill price (D+1 open for `current`; ticket's `entry_price` for `breakout`) | Not the LLM-returned `entry_price` field, which can differ from actual fill for current-entry trades |
| Returned cash (T+2) | Each exit's proceeds available D+2 from that exit day | TASE T+2 settlement; no intraday reinvestment |
| Mark-to-market open positions | Day D closing price | Used for `open_positions_value` in daily equity curve; cost basis used for P&L |
| Max drawdown definition | Maximum peak-to-trough % decline of daily total equity series (cash + open_positions_value) | Standard definition — not single-trade or consecutive-loss |
| Production code changes | Zero | Backtest calls existing services directly with no modifications |
| Output format | CSV + JSON in `output/` subfolder | Simple, no infra, openable in Excel |

---

## 9. Edge Case Handling

| Edge case | Resolution |
|---|---|
| Symbol has < 20 bars at slice day D | `compute_indicators` returns `{}`; pre-screen returns FAIL; skip symbol this day; log warning |
| Symbol has < 200 bars (MA200 = None) | Pre-screen `long_term_trend` returns `False`; symbol **not excluded** — re-evaluated each day; will qualify once it accumulates enough history |
| T1/T2/T3 null or missing from LLM | Skip trade; log as `skipped: invalid_targets` |
| `entry_price` null or ≤ 0 | Skip trade; log as `skipped: invalid_entry_price` |
| Breakout not filled (D+1 high < entry_price) and D+1 low < stop | No entry ever opened — no stop-out; signal treated as never filled |
| T1 and T2 (or T1/T2/T3) all hit on same day | All eligible tranches exit same day at respective prices (T1 first, T2 second, T3 last) |
| T1 hit and stop hit on same day | T1 tranche exits at T1; remaining shares exit at pre-T1 stop (trailing state not yet active) |
| Watchlist | Frozen at backtest start; never re-queried mid-loop |
| Symbol fetch failure (yfinance error) | Skip symbol for entire backtest; log error; continue with remaining symbols |
| < 5 symbols loaded from Supabase | Fail fast with clear error before replay loop starts |
| `--dry-run` flag | Load data + run pre-screen for all symbols all days; no LLM calls, no portfolio changes; write `output/dry_run_signals.csv` (date, symbol, workflow, pre_screen_passed) |
