# Minerva — Development Plan

Ordered by priority. Each phase builds on the one before it.
Reference: [MinervaPRD.md](MinervaPRD.md) · [CLAUDE.md](CLAUDE.md)

---

## Phase 1 — Foundation (Infrastructure & Health)

### 1.1 Backend Baseline
- [x] Initialize FastAPI app with CORS middleware
- [x] `GET /health` → `{"status": "ok", "service": "minerva-backend"}`
- [x] Pydantic-based config loading from `.env` (OpenRouter, Supabase, market defaults)
- [x] Router stubs: `/scanner`, `/research`, `/market`
- [x] `requirements.txt` with all production dependencies
- [x] `pyproject.toml` with Ruff + Black + pytest config

### 1.2 Frontend Baseline
- [x] Initialize Next.js 15 App Router project (TypeScript, Tailwind CSS)
- [x] Root layout with metadata: "Minerva - Trading Research Copilot"
- [x] Home page: renders "Minerva - Trading Research Copilot" heading
- [x] `src/lib/apiClient.ts` — Axios instance pointed at `NEXT_PUBLIC_API_URL`
- [x] Verify `npm run build` completes without errors on Vercel

### 1.3 Database Setup
- [x] Create Supabase project and note connection strings
- [x] Write initial SQL migration: `candidates`, `research_tickets`, `watchlist_items`, `scan_history` tables
- [x] Store migration in `backend/scripts/migrations/001_initial_schema.sql`
- [x] Test connection from backend via Supabase Python client
- [x] Confirm `DATABASE_URL` and `SUPABASE_KEY` work end-to-end

---

## Phase 2 — Data Layer (Market Data & Screener)

### 2.1 Symbol Universe (Watchlist-driven)
> **Design decision:** The scan universe is the user's watchlist, not a static CSV.
> Symbols are added via the Watchlist UI → stored in `watchlist_items` → `POST /scanner/scan` reads from there.
- [x] `GET /market/symbols/{market}` — return watchlist symbols for a given market
- [x] `POST /watchlist`, `GET /watchlist`, `DELETE /watchlist/{id}` — CRUD endpoints
- [x] ~~CSV files~~ — not needed; watchlist is the source of truth

### 2.2 yfinance Integration
- [x] `ScannerService.fetch_market_data()` — fetch OHLC + volume for a symbol list
- [x] Normalize timestamps to epoch ms (`time → ts`) for frontend compatibility
- [x] Handle yfinance errors and stale data gracefully (warn if data > 24h old)
- [x] `.TA` suffix applied automatically for TASE symbols

### 2.3 `GET /market/history` Endpoint
- [x] Accept `symbol`, `market`, `period`, `interval` query params
- [x] Return candles in normalized format: `{"ts", "open", "high", "low", "close", "volume"}`
- [x] `execution_levels` loaded from linked research ticket if `ticket_id` provided
- [x] Return `last_updated` + `is_stale` flag

### 2.4 Screener Logic
- [x] `ScannerService.apply_filters()` with configurable thresholds (price, volume, volatility)
- [x] Market-aware defaults: US (min_vol 500k, price 5–2000) vs TASE (min_vol 50k, price 1–500)
- [x] `POST /scanner/scan` — reads watchlist, runs yfinance, filters, persists to DB
- [x] `GET /scanner/candidates` — latest scan results from DB
- [x] `GET /scanner/history` — recent scan runs
- [x] Persist scan results to `candidates` and `scan_history` tables

---

## Phase 3 — Workflow Engine (LangGraph + LLM Integration)

### 3.1 LangGraph State Machine
- [x] Install `langgraph==0.2.76` + `langchain-core==0.2.38` in requirements.txt
- [x] Define `SwingTradeState` dataclass (`backend/app/services/workflows/swing_trade.py`)
- [x] Sequential node pipeline:
  1. `_node_fetch_data` — yfinance + `compute_indicators()`, no LLM
  2. `_node_pre_screen` — Stage 2 Trend Template + VCP gate, no LLM
  3. `_node_fetch_breadth` — Monty's uptrend CSV (US only), no LLM
  4. `_node_llm_research` — OpenRouter JSON call
  5. `_node_compute_sizing` — deterministic position calculator
  6. `_node_persist_ticket` — validate + write to `research_tickets`
- [x] Expose `execute_swing_trade()` async function

### 3.2 OpenRouter Client
- [x] `OpenRouterClient.research()` with strict `json_object` response format + tenacity retry
- [x] `backend/app/services/indicators.py` — MA20/50/150/200, ATR14, RSI14, 52w high/low, avg vol
- [x] `backend/app/services/market_breadth.py` — uptrend-analyzer port (CSV fetcher + composite scorer)
- [x] `backend/app/services/pre_screen.py` — Stage 2 + VCP gate, PASS/FAIL with reasons
- [x] `backend/app/services/position_sizer_service.py` — fixed-fractional calculator
- [x] `backend/app/services/prompts.py` — combined prompt (technical-analyst + vcp + breadth + sizer)

### 3.3 Skill Prompt Adaptation
- [x] Unified prompt combining technical-analyst, vcp-screener, uptrend-analyzer, position-sizer
- [x] US vs TASE localization (USD/ILS, trading hours, exchange note)
- [x] JSON contract for `technical-swing`:
  ```json
  {
    "entry_price", "entry_rationale", "stop_loss", "stop_rationale",
    "target", "target_rationale", "risk_reward_ratio",
    "bullish_probability", "setup_quality",
    "key_triggers", "caveats",
    "trend_context", "volume_context", "market_breadth_context"
  }
  ```
- [x] DB migration 002: `metadata JSONB` + `key_triggers TEXT[]` added to research_tickets

### 3.4 Research Endpoints
- [x] `POST /research/execute` — `{symbol, market, workflow_type, portfolio_size, max_risk_pct, force}`
- [x] `GET /research/tickets/{ticket_id}` — fetch by UUID from DB
- [x] `GET /research/tickets` — list with optional `market` / `status` filters
- [x] `PATCH /research/tickets/{ticket_id}/status` — approve / reject
- [x] Pre-screen gate: 422 with check details on fail; user can set `force=true` to override

---

## Phase 4 — Risk & Position Sizing

- [x] Implement `RiskService.compute_position_size(entry, stop, account_size, max_risk_pct)`:
  - Fixed-risk sizing: `quantity = floor(max_risk / (entry - stop))`
  - Validate result against `max_quantity` guardrail
- [x] Integrate into `_node_compute_sizing` workflow node (`backend/app/services/workflows/swing_trade.py`)
- [x] Market-aware currency formatting in output: USD for US, ILS (₪) for TASE
- [x] Explicit `max_risk` field in ticket
- [ ] Unit tests: edge cases (stop = entry, negative risk, zero account size)

---

## Phase 5 — Frontend UI

### 5.1 API Integration Layer
- [x] Define TypeScript types mirroring backend schemas (`Candidate`, `ResearchTicket`, `Candle`, `WatchlistItem`, `ExecutionLevels`, `PreScreenError`, `ApiError`)
- [x] `src/lib/api/scanner.ts` — `runScan()`, `getCandidates()`, `getScanHistory()`
- [x] `src/lib/api/research.ts` — `executeResearch()`, `listTickets()`, `getTicket()`, `updateTicketStatus()`
- [x] `src/lib/api/market.ts` — `getHistory()`
- [x] `src/lib/api/watchlist.ts` — `listWatchlist()`, `addWatchlistItem()`, `removeWatchlistItem()`
- [x] Typed `ApiError` class with `isPreScreenFailed()` discriminator

### 5.2 Candidate Queue Page (`/candidates`)
- [x] Fetch and display candidates table from `GET /scanner/candidates`
- [x] Columns: symbol, market, price, volume, score, timestamp
- [x] "Run Scan" button → `POST /scanner/scan` → refresh list
- [x] Market filter: US / TASE / All toggle
- [x] Research button per row → opens `ResearchModal`

### 5.3 Research Ticket Page (`/research/[id]`)
- [x] Fetch ticket from `GET /research/tickets/{id}`
- [x] Display: entry, stop, target, size, risk, rationale, triggers, caveats
- [x] Approve / Reject / Reset buttons → `PATCH /research/tickets/{id}/status`
- [x] CandlestickChart with execution level overlays
- [x] Pre-screen checks accordion (collapsed by default)
- [x] Context sections: entry rationale, trend, volume, breadth

### 5.4 Candlestick Chart Component
- [x] lightweight-charts v4 with dark theme
- [x] `<CandlestickChart candles={...} executionLevels={...} />` renders interactive OHLC chart
- [x] Execution level price lines: entry=blue dashed, stop=red, target=green
- [x] Responsive via `ResizeObserver`
- [x] Loading skeleton while data fetches
- [x] Dynamically imported (no SSR) in ticket page

### 5.5 Watchlist Page (`/watchlist`)
- [x] Display watchlist items with market badge and added date
- [x] Add symbol form: ticker input + market selector (US/TASE) + submit
- [x] Remove per item with loading state
- [x] Market filter toggle
- [x] Symbol icons: nvstly CDN with deterministic color+initials fallback
- [x] Live quotes: last price + change% fetched via `POST /market/quotes` (batched per market)

### 5.6 Research Tickets List (`/research`)
- [x] Full tickets table with entry/stop/target/size/prob/quality/status columns
- [x] Market + status filter toggles
- [x] Click row → navigate to ticket detail

### 5.7 Research Execute Flow
- [x] `ResearchModal` component: portfolio_size + max_risk_pct inputs with currency-aware labels
- [x] Pre-screen failure display: failed checks list + "Force Research" bypass button
- [x] Navigate to ticket page on success

### 5.8 Dashboard (`/`)
- [x] Stats: watchlist count, candidate count, ticket totals (pending/approved)
- [x] Recent tickets table with probability bars
- [x] Quick navigation cards

### 5.9 UI Polish & Theme

- [x] Light/dark mode toggle in nav (Sun/Moon SVG icons, persisted to localStorage)
- [x] `ThemeProvider` React context — `.light` CSS class toggled on `<html>`
- [x] Full CSS variable system: dark default + `.light` overrides
- [x] "Assistant" Google Font applied site-wide
- [x] Candidates page: two-panel scan controls (single-symbol search + watchlist scan)
- [x] `ScoreBar` component with color-coded fill (green ≥70, amber ≥50, dim <50)
- [x] `POST /market/quotes` batch endpoint for live quote ingestion
- [x] `POST /scanner/scan` accepts optional `symbols[]` to bypass watchlist
- [x] `apiClient` interceptor: network-level failures surface human-readable message

---

## Phase 6 — Persistence & Data Integrity

- [ ] All `research_tickets` writes guarded by Pydantic output validation (fail loudly before DB write)
- [ ] Add `created_at`, `updated_at` timestamps to all tables
- [ ] Deduplication check: same `(symbol, market, workflow_type)` within 24h → return cached ticket
- [ ] `scan_history` records: scan run ID, timestamp, candidate count, market
- [ ] Test: insert ticket → fetch ticket → assert round-trip integrity

---

## Phase 7 — Deployment

### 7.1 Backend (Railway)
- [ ] Create `Procfile`: `web: uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- [ ] Set all env vars in Railway dashboard
- [ ] Confirm `/health` returns `{"status": "ok"}` on deployed URL
- [ ] Enable Railway PostgreSQL addon (or confirm Supabase connection works)

### 7.2 Frontend (Vercel)
- [ ] Create `vercel.json` with build command and output directory
- [ ] Set `NEXT_PUBLIC_API_URL` to Railway backend URL
- [ ] Confirm Vercel preview deploy builds and loads home page
- [ ] Enable automatic deployments on `main` branch push

### 7.3 Environment Parity
- [ ] Document all required env vars in `.env.example`
- [ ] Confirm staging and production Supabase projects are separate
- [ ] Add Railway health check probe to `/health`

---

## Phase 8 — Testing & Quality

- [ ] Backend unit tests coverage ≥ 80% on `services/` and `utils/`
- [ ] Integration tests: full `scan → execute → ticket` flow (mocked OpenRouter)
- [ ] Frontend: ESLint + Prettier pass with no errors
- [ ] Backend: Ruff linting pass with no errors
- [ ] Manual smoke test: run scan for US market, execute research on top candidate, review ticket in UI
- [ ] Manual smoke test: same flow for TASE market

---

## Out of Scope for v1

- Multi-user auth
- Broker execution / order management
- Real-time streaming data
- Automated / scheduled scans
- Options, dividends, long-term investing workflows
- Drag-to-edit chart annotations with persistence
