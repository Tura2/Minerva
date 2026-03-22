# Minerva — Workflows & Skill Improvement Roadmap

> Last updated: 2026-03-22
> See also: CLAUDE.md §"Codebase State" for applied fixes

## Registered Workflows

| workflow_type            | File                          | Strategy                      | Pre-Screen                                 |
| ------------------------ | ----------------------------- | ----------------------------- | ------------------------------------------ |
| `technical-swing`        | `workflows/swing_trade.py`    | Minervini Stage 2 breakout    | 7 Trend Template checks + VCP              |
| `mean-reversion-bounce`  | `workflows/mean_reversion.py` | Oversold bounce in uptrend    | 7 MR checks (RSI<38, price<MA20, >MA200)   |

Both workflows use the identical node structure, JSON output contract, and DB schema.
The frontend renders tickets from both workflows without any conditional logic.

---

## 2. Workflow: `mean-reversion-bounce`

### Pipeline Overview

Identical node order to `technical-swing`. Only the pre-screen gate, indicator set, and LLM prompt differ.

```
POST /research/execute  (workflow_type="mean-reversion-bounce")
        │
        ▼
[Dedup Check] ──── hit ────► return cached ticket (24h window)
        │ miss
        ▼
 Node 1: fetch_data       — yfinance OHLC (1y) + indicators + MR indicators (BB, cap vol, RSI div)
        │
        ▼
 Node 2: fetch_rs         — RS vs benchmark + universe rank (non-blocking)
        │
        ▼
 Node 3: pre_screen_mr    — Mean Reversion gate (7 checks)
        │ fail (force=false)        │ pass (or force=true)
        ▼                           ▼
  HTTP 422 with                Node 4: fetch_breadth
  pre_screen details                   │
                                       ▼
                               Node 5: llm_research   ← MR prompt (floor, not breakout)
                                       │
                                       ▼
                               Node 6: compute_sizing  — T1=MA20, T2=resistance, T3=full trend
                                       │
                                       ▼
                               Node 7: persist_ticket  — workflow_type="mean-reversion-bounce"
```

---

### Pre-Screen: Mean Reversion Gate (7 checks)

| Check | Condition | Rationale |
| ----- | --------- | --------- |
| `long_term_trend_intact` | `price > ma200` | Only buy dips in confirmed uptrends |
| `ma200_rising` | MA200 slope positive (22/15 sessions) | Structural foundation |
| `price_below_mean` | `price < ma20` | Short-term dip from mean confirmed |
| `rsi_oversold` | `rsi14 < 38` (US) / `< 40` (TASE) | Quantified oversold condition |
| `not_in_freefall` | `price > ma200 × 0.85` | Dip, not breakdown |
| `not_extended_down` | Less than 45% below 52w high | Avoids structural damage |
| `min_volume` | Same RVOL gate as swing | Liquidity floor |

VCP detection is computed but **non-blocking** (MR setups rarely have VCPs).

---

### New Indicators (computed by `compute_mean_reversion_indicators()`)

| Indicator | Description |
| --------- | ----------- |
| `bb_upper/middle/lower` | Bollinger Bands (20, 2) |
| `bb_pct_b` | Where price sits: 0 = lower band, 1 = upper band, <0 = pierced below |
| `distance_from_lower_bb_pct` | % gap between price and lower band |
| `capitulation_detected` | Any down-day in last 10 sessions with volume ≥ 2× 50d avg |
| `capitulation_vol_ratio` | Peak volume ratio on that day |
| `capitulation_days_ago` | Sessions since the capitulation day |
| `rsi_divergence` | True if price made lower low but RSI made higher low (30-session window) |
| `rsi_trough_1/2` | The two RSI lows used for divergence detection |
| `price_low_1/2` | Corresponding price lows |

---

### LLM Prompt Philosophy

- **System role:** Mean reversion specialist. Hunts FLOORS, not breakouts.
- **Entry type:** `"current"` (buy at support now) or `"buy_stop"` (wait for first bounce confirmation)
- **Stop:** Structural — below MA200, swing low, or gap fill. ATR minimum is an absolute floor only.
- **T1 (40%):** MA20 ± 3% — the primary mean-reversion target (enforced in prompt rules)
- **T2 (35%):** Prior resistance, gap fill, or MA50
- **T3 (25%):** Full trend resumption / 52w high area
- **R:R minimum:** 1.5:1 (relaxed from 2:1 — MR setups are higher-frequency, tighter stops)

### Synthesized Score Dimensions (MR)

| Dimension | What it measures |
| --------- | ---------------- |
| `long_term_trend` | MA200 slope + price above MA150/MA200 |
| `dip_depth_quality` | RSI level + %B position + distance from MA20 |
| `exhaustion_signals` | Capitulation vol ratio + RSI divergence |
| `support_confluence` | How many S/R layers converge at entry |
| `breadth_context` | Market breadth zone (shared with swing) |
| `rs_quality` | RS rank — leader temporarily weak vs laggard in distress |

---

### Workflow Auto-Detection (Scanner)

The scanner (`scanner.py`) now runs **both** pre-screen gates per candidate symbol after the RVOL/ATR filter passes. Results are stored in `candidates.metadata.applicable_workflows[]`.

The frontend candidate card shows `Swing` / `MR` / both badges. Clicking **Research**:

- 1 workflow → opens ResearchModal pre-filled with that workflow
- 2 workflows → shows a strategy picker step before the form
- 0 workflows → falls back to `["technical-swing"]` (safety default)

**Scanner data period changed:** `period="1mo"` → `period="1y"` to supply enough history for MA200 computation during classification. Scan runtime will be slightly longer for large watchlists.

---

## 1. Workflow: `technical-swing` (Minervini Breakout)

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

---

## 7. Market Adaptation — TASE vs US

### Root Causes of Low TASE Pass Rate (Fixed 2026-03-19)

| Problem | Root Cause | Fix Applied |
|---------|-----------|-------------|
| Most TASE stocks filtered before pre-screen | Scanner `max_price: 500` rejected agorot prices (e.g. 2000 agorot = 20 NIS → rejected) | Agorot ÷100 in `fetch_market_data()`, max_price raised to 2000 ILS |
| All thresholds same for both markets | Minervini criteria designed for US large-caps | Market-specific `STAGE2_THRESHOLDS` dict in pre_screen.py |
| MA200 requiring 22 sessions of uptrend | TASE has fewer sessions due to Sun–Thu trading + Israeli holidays | Reduced to 15 sessions for TASE |
| 52w high proximity too strict | TASE stocks swing wider; 25% cutoff excludes setups that are still valid | Relaxed to 30% for TASE |
| 52w low recovery too strict | TASE stocks can bounce from deeper drawdowns | Relaxed to 20% for TASE (from 25%) |

### Current Market-Specific Thresholds

| Parameter | US | TASE |
|-----------|-----|------|
| Scanner min_price | $5 | ₪1 |
| Scanner max_price | $2,000 | ₪2,000 |
| Scanner min_volume (daily) | 500k | 30k |
| Pre-screen min avg_vol_50 | 200k | 30k |
| 52w low recovery | ≥25% | ≥20% |
| 52w high proximity | within 25% | within 30% |
| MA200 trending sessions | 22 | 15 |

### Remaining TASE-Specific Improvements

- **TA-35 breadth data**: TASE breadth always returns neutral stub. Compute breadth from TA-35 components (% above MA50/MA200). This would unlock richer LLM analysis for Israeli stocks.
- **Shekel-hedged context**: Include USD/ILS rate trend in TASE prompt. A weakening shekel amplifies downside for imported-cost companies (energy, telecom).
- **Israeli market calendar**: Account for Passover, Rosh Hashana, and other closures in staleness checks. A 3-day gap is normal around major holidays, not a data problem.
- **TASE sector mapping**: Israeli sectors differ from US (defense tech, generic pharma, real estate funds are dominant). Build TASE sector-to-company mapping for sector RS scoring.

---

## 8. Additional Workflow Ideas

### 8.1 `relative-strength-leader` (High Value)

**Goal:** Find stocks consistently outperforming their market index over multiple timeframes.

**Pipeline:**
1. Fetch stock OHLC + benchmark (SPY for US, TA-35 ETF for TASE)
2. Compute RS ratio = stock return / benchmark return over 3m, 6m, 1y
3. Score: weighted average (40% 1y, 35% 6m, 25% 3m) — penalise recent decay
4. Pass threshold: score ≥ 1.10 (10% outperformance)
5. No LLM needed — pure math output ranked by RS score

**Use case:** Best setups come from market leaders, not average performers. Supplements Stage 2 filter.

---

### 8.2 `golden-cross-alert` (Low Effort)

**Goal:** Detect stocks where MA50 just crossed above MA200 (within last 5 sessions).

**Pipeline:**
1. Fetch 1y daily OHLC
2. Compute MA50 and MA200
3. Check: MA50 < MA200 five sessions ago AND MA50 > MA200 today
4. Score by: how many sessions since cross (fresher = higher score) + volume on cross day
5. No LLM — deterministic output

**Use case:** Golden crosses are high-probability continuation signals when accompanied by volume. Fast to compute for the entire watchlist.

---

### 8.3 `52w-high-breakout` (Medium Value)

**Goal:** Identify stocks within 1–3% of their 52-week high on above-average volume — potential breakout imminent.

**Pipeline:**
1. Fetch data, compute 52w high and current price
2. Gate: price within 3% of 52w high AND today's volume > 1.5× avg_vol_50
3. Optionally: confirm with consolidation (low ATR last 5 sessions)
4. Optional LLM: "Is this a valid breakout or exhaustion near a resistance ceiling?"

**Use case:** Stocks at 52w highs in strong uptrends tend to continue higher. Complements the Stage 2 `near_52w_high` check which just requires being within 25%.

---

### 8.4 `vcp-pure-scanner` (Medium Value)

**Goal:** Scan entire watchlist for VCP patterns without running the full LLM workflow.

**Pipeline:**
1. Fetch 6m daily for all watchlist symbols (batch yfinance)
2. Run `detect_vcp_contractions()` for each
3. Score: `contraction_count × tightening_quality` (deeper = lower score)
4. Return top 10 VCP setups ranked by score
5. No LLM — deterministic

**Use case:** VCP is the highest-quality swing setup. Scanning for them across the full watchlist without spending LLM tokens is a fast daily check.

---

### 8.5 `mean-reversion-bounce` (Medium Value)

**Goal:** Find oversold stocks in otherwise strong uptrends (RSI < 35 while above MA200).

**Pipeline:**
1. Fetch data, compute indicators
2. Gate: price > MA200 AND RSI14 < 35 AND price still within 30% of 52w high
3. This filters for pullbacks within uptrends, not broken stocks
4. LLM prompt: "The stock is in a long-term uptrend but has pulled back. Identify the bounce entry, stop below the pullback low, target near prior high."

**Use case:** Mean reversion in an uptrend is a lower-risk setup with a defined catalyst (oversold bounce). Works especially well in choppy markets.

---

### 8.6 `earnings-gap-continuation` (High Value)

**Goal:** Stocks that gapped up >5% on earnings with above-average volume often continue higher.

**Pipeline:**
1. Detect if most recent earnings were within last 10 sessions (yfinance `.calendar`)
2. Compute gap: `open[earnings_day] / close[earnings_day - 1] - 1`
3. Gate: gap ≥ 5% upside AND earnings day volume ≥ 2× avg_vol_50
4. Check: price still holding above gap day open (not filled)
5. LLM: "This stock reported strong earnings and gapped up. Is the gap holding? What is the continuation entry above the gap day high?"

**Use case:** Post-earnings momentum is statistically significant. The key is confirming the gap isn't being filled (which signals distribution).

---

### 8.7 `sector-rotation-leader` (Medium Value)

**Goal:** Identify which sectors are rotating in and find the top stock within each leading sector.

**Pipeline:**
1. Fetch weekly returns for sector ETFs (XLK, XLF, XLE, XLV, XLI, etc.) — or TA-35 sub-sectors for TASE
2. Rank sectors by 4-week momentum
3. For the top 2 sectors: run RS leader scan against watchlist stocks mapped to those sectors
4. Output: sector ranking + top 1–2 stock picks per sector

**Use case:** Rotating into leading sectors before the crowd is the core of momentum investing. Adds macro layer absent in the current single-stock analysis.

---

### 8.8 `insider-accumulation` (Advanced, External API)

**Goal:** Stocks with significant insider buying in the last 30 days are statistically more likely to rise.

**Pipeline:**
1. Fetch insider transactions from OpenInsider API (US only) or similar
2. Filter: purchases ≥ $100k by officers/directors (not option exercises)
3. Cross-reference with watchlist; flag overlapping symbols
4. Optionally run full `technical-swing` workflow on flagged symbols automatically

**Use case:** Insider buying is one of the strongest positive signals. Combining it with technical analysis (Stage 2 + VCP) creates high-conviction setups.

**Note:** Requires external API integration (OpenInsider is free for US).

---

### 8.9 `trend-strength-score` (Low Effort, High Impact)

**Goal:** Composite score that ranks all watchlist symbols by overall trend quality — not pass/fail, but a 0–100 score.

**Score components:**
- Price vs MA50/MA150/MA200: each MA above → +15 pts
- MA150 > MA200 → +10 pts
- MA200 trending up → +10 pts
- RSI14 ∈ [50, 70] → +10 pts (healthy trend, not overbought)
- Price within 15% of 52w high → +10 pts
- VCP confirmed → +10 bonus pts

**Use case:** Instead of binary pass/fail, gives a ranked list. Useful for prioritizing which symbols to research first when many pass Stage 2.

---

### 8.10 `failed-breakout-short` (Advanced)

**Goal:** Stocks that failed a 52w high breakout (gapped up then reversed below breakout level) — potential short setup.

**Pipeline:**
1. Detect: price was within 2% of 52w high in last 5 sessions AND today's price is >5% below that level
2. Confirm: above-average volume on the reversal day (distribution signal)
3. LLM: "A breakout attempt failed. Identify the short entry, stop above the failed breakout high, target at support."

**Use case:** Failed breakouts are among the most reliable short setups. Only relevant if user trades short. Requires `direction: short` flag in ticket schema.

---

## 9. Skill Ideas (Claude Prompt Skills)

These are new `.claude/skills/` prompt templates that could be added to the project:

| Skill | Description |
|-------|-------------|
| `earnings-analyst` | Reads earnings transcript context, rates the quality of the beat, estimates whether gap will hold |
| `sector-analyst` | Given a sector name and recent data, rates sector momentum and suggests top themes |
| `risk-manager` | Reviews a batch of approved tickets, checks portfolio concentration, flags correlated positions |
| `market-regime-detector` | Classifies current market as trending/choppy/risk-off using SPY/VIX data. Adjusts position sizing recommendations accordingly |
| `tase-analyst` | Specialized for Israeli market context: shekel exposure, dual-listed stocks (TASE + NASDAQ), geopolitical risk factors |
| `exit-optimizer` | Given an open position, recommends whether to hold/trim/exit based on current price relative to target and stop |
| `journal-reviewer` | Reviews past approved/rejected tickets, identifies patterns in what the user approves, tunes future research to their style |
