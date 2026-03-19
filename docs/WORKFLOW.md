# Minerva — Workflow Engine

## Overview

The workflow engine executes research pipelines on individual stocks.
Each workflow is a sequential node pipeline (LangGraph-style) that runs
deterministic checks first, then calls the LLM only for passing candidates.

Current workflows: `technical-swing` (Phase 3)

---

## technical-swing

**File:** `backend/app/services/workflows/swing_trade.py`

**Trigger:** `POST /research/execute`

**Required inputs:**
- `symbol` — ticker (no `.TA` suffix)
- `market` — `US` or `TASE`
- `portfolio_size` — account size in local currency
- `max_risk_pct` — max % of account to risk per trade

---

### Node 1 — `_node_fetch_data`

Fetches 1-year daily OHLC from yfinance and computes all technical indicators.

**Computed indicators** (`indicators.py`):
| Indicator | Notes |
|-----------|-------|
| MA20, MA50, MA150, MA200 | Simple moving averages |
| ATR-14 | Wilder's Average True Range |
| RSI-14 | Relative Strength Index |
| 52-week high / low | Rolling 252-day window |
| Avg volume (50-day) | Liquidity baseline |
| MA200 trending up | `True` if MA200 today > MA200[-22 sessions]` |

**Outputs to state:** `df` (DataFrame), `indicators` (dict)

---

### Node 2 — `_node_pre_screen` (Gate)

Runs Minervini's 7-point Trend Template + liquidity check. No LLM.

**Checks:**
| Check | Criteria |
|-------|---------|
| price_above_ma150 | Close > MA150 |
| price_above_ma200 | Close > MA200 |
| ma150_above_ma200 | MA150 > MA200 |
| ma200_trending_up | MA200 today > MA200 22 sessions ago |
| price_above_ma50 | Close > MA50 |
| above_52w_low | Price ≥ 25% above 52-week low |
| near_52w_high | Price within 25% of 52-week high |
| min_volume | 50-day avg volume ≥ market minimum |

**VCP detection** (informational, non-blocking):
- Finds swing-high to swing-low depth contractions in last 60 sessions
- Flags if ≥2 contractions with each depth ≤75% of prior (tightening)
- Reports `pivot_buy_point` if VCP confirmed

**Gate behavior:**
- All 8 checks must pass → proceed to Node 3
- Any failure → raise `PreScreenFailed` → router returns `422` with full check details
- `force=true` on request → bypass gate, proceed anyway

---

### Node 3 — `_node_fetch_breadth`

Downloads market breadth data from Monty's public GitHub CSV.

**Source:** `https://github.com/tradermonty/uptrend-dashboard`

**US:** Fetches `uptrend_ratio_timeseries.csv`:
- Overall uptrend ratio (% of S&P 500 stocks above MA150)
- 10-sector breakdown with ratio, MA10, trend direction
- Composite score (0–100) with zone: `Bear / Cautious / Neutral / Bull / Strong Bull`

**TASE:** Returns neutral stub — no equivalent free data source.

**Failure handling:** If CSV fetch fails, continues with `{"zone": "Neutral", "available": false}`.

---

### Node 4 — `_node_llm_research`

Single OpenRouter API call with combined prompt from 4 adapted skills.

**Prompt construction** (`prompts.py`):
- Technical indicators snapshot
- Stage 2 check results
- VCP detection summary
- Market breadth context
- Portfolio size + risk budget

**Model:** Configured via `RESEARCH_MODEL` env var (default: `openai/gpt-4-turbo`)

**Response format:** `json_object` mode enforced

**Required output fields:**
```
entry_price, stop_loss, target, bullish_probability, key_triggers
```

**Optional fields:**
```
entry_rationale, stop_rationale, target_rationale,
risk_reward_ratio, setup_quality (A/B/C),
trend_context, volume_context, market_breadth_context, caveats
```

**Retry:** tenacity exponential backoff (configurable via `RESEARCH_OPENROUTER_RETRY_COUNT`)

---

### Node 5 — `_node_compute_sizing`

Deterministic position calculator using LLM's entry and stop prices.

**Formula (fixed-fractional):**
```
risk_per_share = entry_price - stop_price
dollar_risk    = account_size × (max_risk_pct / 100)
shares         = floor(dollar_risk / risk_per_share)
```

**Outputs:** `shares`, `position_value`, `dollar_risk`, `risk_pct_actual`, `currency`

---

### Node 6 — `_node_persist_ticket`

Writes the final ticket to `research_tickets` table.

**Stored fields:**
- Core: `symbol, market, workflow_type, entry_price, stop_loss, target`
- Sizing: `position_size, max_risk, currency`
- LLM: `bullish_probability, key_triggers`
- Status: `pending` (initial)
- `metadata JSONB`: all rationale, caveats, breadth context, pre-screen results, model info

**Returns:** Full ticket row including auto-generated UUID and timestamps.

---

## Adding a New Workflow

1. Create `backend/app/services/workflows/<name>.py`
2. Define state dataclass and sequential node functions
3. Identify source skills from `reference/claude-trading-skills/skills/`
   - Only swing-trade skills (no dividends, options, long-term)
4. Add prompt builder to `prompts.py`
5. Register in `backend/app/routers/research.py` under `VALID_WORKFLOWS`
6. Add frontend option in the research UI

---

## Error Handling

| Error | HTTP | Cause |
|-------|------|-------|
| `WorkflowError` | 500 | yfinance fetch failed, LLM missing required fields |
| `PreScreenFailed` | 422 | Stage 2 checks failed (use `force=true` to bypass) |
| OpenRouter 429/5xx | auto-retry | tenacity handles via exponential backoff |
| DB insert failure | 500 | Supabase connection issue or schema mismatch |
