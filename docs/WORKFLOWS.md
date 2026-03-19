# Minerva — Workflows & Skill Improvement Roadmap

## 1. Current Workflow: `technical-swing`

### Pipeline Overview

```
POST /research/execute
        │
        ▼
[Dedup Check] ──── hit ────► return cached ticket (24h window)
        │ miss
        ▼
 Node 1: fetch_data        — yfinance OHLC (1y daily) + indicators
        │
        ▼
 Node 2: pre_screen        — Minervini Stage 2 + VCP gate (7 checks)
        │ fail (force=false)        │ pass (or force=true)
        ▼                           ▼
  HTTP 422 with                Node 3: fetch_breadth
  pre_screen details                   │
                                       ▼
                               Node 4: llm_research   ← single OpenRouter call
                                       │
                                       ▼
                               Node 5: validate_output  — Pydantic schema
                                       │
                                       ▼
                               Node 6: compute_sizing   — position calculator
                                       │
                                       ▼
                               Node 7: persist_ticket   — write to DB
                                       │
                                       ▼
                                 return ticket
```

---

### Node-by-Node Reference

| # | Node | LLM | Purpose | Key Output |
|---|------|-----|---------|------------|
| 1 | `_node_fetch_data` | No | yfinance OHLC → DataFrame, compute_indicators | `state.df`, `state.indicators` |
| 2 | `_node_pre_screen` | No | Stage 2 Trend Template + VCP detection | `state.screen_result` |
| 3 | `_node_fetch_breadth` | No | Monty's uptrend CSV (US only; TASE = neutral stub) | `state.breadth` |
| 4 | `_node_llm_research` | **Yes** | DeepSeek analysis → entry/stop/target/triggers | `state.llm_raw` |
| 5 | `_node_validate_output` | No | Pydantic validation of LLM fields | raises on bad output |
| 6 | `_node_compute_sizing` | No | Position size, dollar risk, R/R | `state.sizing` |
| 7 | `_node_persist_ticket` | No | Build metadata, write to `research_tickets` | ticket dict |

---

### Pre-Screen: Minervini Stage 2 Checks

All 7 must pass (plus volume gate):

1. Price > MA150
2. Price > MA200
3. MA150 > MA200
4. MA200 trending up (22+ sessions)
5. Price > MA50
6. Price ≥25% above 52-week low
7. Price within 25% of 52-week high

**Volume gate:** avg 50-day vol ≥ 200K (US) / 30K (TASE)

**VCP (informational, non-blocking):** ≥2 contractions, each ≤75% depth of prior, 3–50% swing depth.
If `force=true`, pre-screen result is stored in metadata but doesn't block execution.

---

### LLM Contract

**Model:** `deepseek/deepseek-chat` (non-reasoning, supports JSON mode)
**Temperature:** 0.4
**Max tokens:** 2500
**Response format:** `json_object`

**Required output fields:**

```json
{
  "entry_price": float,
  "stop_loss": float,
  "target": float,
  "risk_reward_ratio": float,
  "bullish_probability": float,
  "key_triggers": ["string", ...],
  "entry_rationale": "string",
  "stop_rationale": "string",
  "target_rationale": "string",
  "caveats": ["string", ...],
  "setup_quality": "A | B | C",
  "trend_context": "string",
  "volume_context": "string",
  "market_breadth_context": "string"
}
```

**Validation gates after LLM:**
- entry > 0
- stop < entry
- target > entry (long-only)
- R/R ≥ 1.0
- bullish_probability ∈ [0.0, 1.0]
- position_size > 0
- ≥1 non-empty key_trigger

---

### Currency & Market Handling

| Market | Currency | Price Source | Agorot Fix |
|--------|----------|-------------|------------|
| US | USD ($) | yfinance raw | n/a |
| TASE | ILS (₪) | yfinance ÷ 100 | ✅ Applied at fetch + quotes + chart |

**TASE symbol handling:**
- Stored in DB without `.TA` suffix
- `.TA` appended only for yfinance calls
- User input `OPCE.TA` → stripped to `OPCE`, market inferred as TASE

---

## 2. Known Issues & Fixes Applied

| Issue | Severity | Status |
|-------|----------|--------|
| TASE agorot — prices 100x too large | Critical | ✅ Fixed (2026-03-19) |
| Hover color `zinc-800` hardcoded dark | Minor | ✅ Fixed |
| Dedup ignores portfolio_size changes | Low | Open |
| TASE market breadth — always neutral stub | Low | Open |
| Currency label "ILS (NIS)" inconsistency | Cosmetic | Open |

---

## 3. Workflow Improvement Roadmap

### 3.1 High Priority

#### TASE Market Breadth
- **Problem:** Breadth node always returns neutral stub for TASE; LLM gets no breadth context.
- **Fix:** Integrate TA-35 index components breadth. Fetch TASE top 35 symbols, compute % above MA50/MA200, return zone (Bullish / Neutral / Bearish).
- **Effort:** Medium — add `_tase_breadth()` to `market_breadth.py`, reuse existing ratio logic.

#### Dedup Key Should Include Sizing Params
- **Problem:** If user changes `portfolio_size` or `max_risk_pct`, they get the old cached ticket.
- **Fix:** Hash `(symbol, market, portfolio_size, max_risk_pct)` into the dedup key.
- **Effort:** Low — add `metadata->>portfolio_size` filter to the dedup query.

#### Multi-Timeframe Confirmation Node
- **Problem:** Analysis is based on 1D only. Weekly trend context missing.
- **Improvement:** Add `_node_fetch_weekly()` between fetch_data and pre_screen. Compute weekly MA50/MA200, trend direction, 52-week position. Pass to LLM prompt as "Weekly context: …".
- **Effort:** Low — second yfinance call with `interval="1wk"`, separate indicator pass.

---

### 3.2 Medium Priority

#### Volume Profile Node
- **Problem:** Volume context is a single avg figure. No info on accumulation/distribution patterns.
- **Improvement:** Compute:
  - Up-volume vs down-volume ratio (last 20 sessions)
  - Volume spike detection (session > 2× avg vol)
  - Dry-up pattern before potential breakout (last 3 sessions below avg)
- **Add to:** `compute_indicators()` → `state.indicators["volume_profile"]`
- **LLM benefit:** Richer volume analysis, better key_triggers.

#### Sector Relative Strength
- **Problem:** A stock may pass Stage 2 but its sector is lagging the market.
- **Improvement:** Fetch sector ETF (e.g., XLK for tech) alongside the stock. Compute stock RS vs sector and sector RS vs SPY. Include in prompt as a sentence: "Sector RS: outperforming / underperforming".
- **Effort:** Medium — requires sector-to-ETF mapping table.

#### Confidence Score Node
- **Problem:** `bullish_probability` is purely LLM-generated with no calibration.
- **Improvement:** Add post-LLM node that blends:
  - LLM probability (60% weight)
  - VCP confirmation bonus (+5-10%)
  - Breadth zone bonus/penalty (±5-15%)
  - ATR/volatility penalty (high ATR stocks → discount)
- **Result:** More consistent, auditable conviction scores.

---

### 3.3 Lower Priority

#### Stop Loss Methodology Options
- Currently: LLM chooses stop placement.
- Better: Offer 3 modes passed as param:
  1. `atr_based` — stop = entry - (1.5× ATR14)
  2. `swing_low` — stop below recent pivot low (last N sessions)
  3. `llm_discretionary` — current behavior
- Add `stop_method` param to `/execute` endpoint.

#### Partial Profit Target (R-multiple)
- Add second target field: `target_2` at 2× R, `target_3` at 3× R.
- LLM already suggests a target; compute the others deterministically.
- Show on chart as additional price lines.

#### TASE-Specific Pre-Screen Tuning
- US thresholds may not apply to TASE's smaller, less liquid market.
- Consider: lower the 52w high proximity check from 25% to 30% for TASE (more volatile).
- Consider: reduce MA200 requirement minimum history to 180 sessions (some TASE stocks are newer).

#### Re-run on Status Change
- When user clicks "Reject" on a ticket, offer a button: "Re-run with force_refresh=true".
- Avoids user needing to navigate back to Candidates page.

---

### 3.4 New Workflow Concepts

#### `earnings-gap` Workflow
- Detect stocks with recent earnings surprise (>5% gap up/down).
- Specialized prompt: focus on gap-fill probability, volume confirmation, continuation vs reversal setup.
- Node: check if earnings within last 5 sessions via yfinance `calendar`.

#### `breakout-scanner` Workflow
- Scan watchlist for stocks within 3% of 52-week high on above-average volume.
- No LLM needed — pure deterministic output ranked by score.
- Result feeds into Candidates queue as `breakout` type.

#### `sector-rotation` Summary
- Weekly job: scan all watchlist symbols, group by sector, compute sector-level average RS.
- Output: dashboard widget showing top/bottom 3 sectors.
- No per-symbol LLM needed — aggregate math only.

---

## 4. Prompt Engineering Improvements

### Current Prompt Weaknesses

1. **No chart data** — LLM only sees indicator values, not visual pattern. Can't identify cup-and-handle, ascending triangle etc.
2. **No historical comparison** — LLM doesn't know if current setup is similar to past setups that worked.
3. **Entry price too close to current price** — LLM sometimes sets entry = current price (not a valid limit order point).
4. **Stop placement too tight** — ATR not always respected; LLM may suggest 1% stop on a 3% ATR stock.

### Prompt Improvements

#### Enforce ATR-Based Stop Minimum
Add to system prompt:
```
Stop loss must be at least 0.8× ATR14 below entry price.
If your calculated stop is closer than this, widen it to entry - (0.8 × ATR14).
```

#### Entry Must Be a Breakout Point
Add to prompt context:
```
Entry should be:
- At or slightly above a recent resistance/pivot level
- NOT equal to the current price unless price just crossed resistance
- Ideal entry: VCP pivot + 1–2% (if VCP confirmed)
```

#### Structured Reasoning Format
Request chain-of-thought before JSON:
```
First, analyze the setup in 2-3 sentences.
Then output the JSON block.
```
Improves consistency of price levels.

---

## 5. Infrastructure Improvements

### Response Caching
- Cache LLM responses keyed by `(symbol, market, date, model)`.
- Reuse same-day responses for the same symbol without re-calling LLM.
- Storage: Redis or simple DB table with TTL.

### Workflow Retry on LLM Failure
- Current: workflow fails completely if LLM returns bad JSON.
- Better: retry the LLM call up to 2 times with a corrective prefix: "Your previous response was invalid JSON. Try again. Output only valid JSON."

### Streaming Research
- WebSocket endpoint that streams workflow node progress to frontend.
- Frontend shows live progress: "Fetching data… Pre-screen passed… Running LLM analysis…"
- Reduces perceived latency on 10-20s research calls.

### Batch Research
- `POST /research/batch` with list of symbols.
- Run workflow for each symbol with concurrency limit (e.g., 3 at a time).
- Return list of tickets or per-symbol errors.

---

## 6. Frontend Skill Improvements

### Candidates Page
- Add sortable columns (by score, volume, market).
- "Research All Passing" button — queue batch research for all Minervini-passing candidates.
- Color-code score bars: green ≥ 80, yellow 60-79, red < 60.

### Ticket Page
- Show ATR14 on the chart (as a info annotation, not a price line).
- Add "Similar setups" section — tickets with same symbol in last 30 days.
- Risk/reward ratio visualized as a bar: |←stop—entry—target→|.

### Watchlist
- Column for "Last Scanned" (most recent candidate date for this symbol).
- "Quick Research" button per row — one-click to open `/candidates` pre-filled with that symbol.
- Sort by market cap, volume, or last price change.

### Dashboard
- Research pipeline funnel: Watchlist → Candidates → Researched → Approved.
- TASE / US split metrics side-by-side.
- Weekly performance summary: tickets approved this week, avg R/R, avg bullish_probability.
