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
- [ ] Verify `npm run build` completes without errors on Vercel

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
- [ ] Install and wire real `langgraph` dependency
- [ ] Define `WorkflowState` dataclass for `technical-swing` workflow
- [ ] Define graph nodes in order:
  1. `validate_symbol` — deterministic, no LLM
  2. `fetch_market_data` — yfinance fetch, no LLM
  3. `deterministic_analysis` — compute trend/volume signals, no LLM
  4. `llm_research` — call OpenRouter, shortlisted candidates only
  5. `validate_output` — assert JSON schema before DB write
  6. `persist_ticket` — write to `research_tickets` table
- [ ] Compile graph and expose `WorkflowEngine.execute()`

### 3.2 OpenRouter Client
- [ ] Implement `OpenRouterClient.research()` with:
  - Strict `response_format: {"type": "json_object"}` enforcement
  - Retry on HTTP 429 and 5xx (exponential backoff via `tenacity`)
  - Retry on timeout/transport exceptions
  - Log raw request/response in debug mode
- [ ] Cache: check if same `(symbol, market, workflow_type)` was recently run → return cached ticket
- [ ] Unit test: mock OpenRouter response, assert retry triggers on 429

### 3.3 Skill Prompt Adaptation
- [ ] Read `reference/claude-trading-skills/skills/technical-analyst/SKILL.md`
- [ ] Port prompt to OpenRouter-compatible format (no Anthropic CLI coupling)
- [ ] Add US vs TASE localization branches in the prompt (USD/ILS, trading hours)
- [ ] Define and validate output JSON contract for `technical-swing` workflow:
  ```json
  {
    "entry_price", "entry_rationale",
    "stop_loss", "target",
    "position_size", "max_risk",
    "bullish_probability", "key_triggers", "caveats"
  }
  ```
- [ ] Integration test: run workflow with mocked OpenRouter, assert ticket schema

### 3.4 Research Endpoints
- [ ] `POST /research/execute` — accepts `{symbol, market, workflow_type}`, runs graph, returns ticket
- [ ] `GET /research/tickets/{ticket_id}` — fetch by UUID from DB
- [ ] `GET /research/tickets` — list all tickets with optional `market` / `status` filters
- [ ] `PATCH /research/tickets/{ticket_id}/status` — approve / reject a ticket

---

## Phase 4 — Risk & Position Sizing

- [ ] Implement `RiskService.compute_position_size(entry, stop, account_size, max_risk_pct)`:
  - Fixed-risk sizing: `quantity = floor(max_risk / (entry - stop))`
  - Validate result against `max_quantity` guardrail
- [ ] Integrate into `validate_output` workflow node
- [ ] Market-aware currency formatting in output: USD for US, ILS for TASE
- [ ] Explicit `max_risk` field in ticket (e.g. `"max_risk_usd": 550.00`)
- [ ] Unit tests: edge cases (stop = entry, negative risk, zero account size)

---

## Phase 5 — Frontend UI

### 5.1 API Integration Layer
- [ ] Define TypeScript types mirroring backend schemas (`Candidate`, `ResearchTicket`, `Candle`)
- [ ] Add `api/scanner.ts`, `api/research.ts`, `api/market.ts` wrappers in `src/lib/`
- [ ] Handle error states and loading states with React `Suspense`-compatible patterns

### 5.2 Candidate Queue Page (`/candidates`)
- [ ] Fetch and display candidates table from `GET /scanner/candidates`
- [ ] Columns: symbol, market, price, volume, score, timestamp
- [ ] "Run Scan" button → `POST /scanner/scan` → refresh list
- [ ] Market selector: US / TASE toggle

### 5.3 Research Ticket Page (`/research/[id]`)
- [ ] Fetch ticket from `GET /research/tickets/{id}`
- [ ] Display: entry, stop, target, size, risk, rationale, triggers, caveats
- [ ] Approve / Reject buttons → `PATCH /research/tickets/{id}/status`
- [ ] Chart integration (see 5.4)

### 5.4 Candlestick Chart Component
- [ ] Install and configure `lightweight-charts`
- [ ] `<CandlestickChart candles={...} />` renders interactive OHLC chart
- [ ] Overlay execution levels as horizontal lines:
  - Entry (checkpoint): blue dashed line
  - Stop loss (support): red line
  - Target (resistance): green line
- [ ] Pan, zoom, and fullscreen toggle
- [ ] Loading skeleton while data fetches
- [ ] Responsive resize via `ResizeObserver`

### 5.5 Watchlist Page (`/watchlist`)
- [ ] Display watchlist items from DB
- [ ] Add symbol to watchlist button
- [ ] Remove from watchlist
- [ ] Quick chart preview on hover (optional, v1+)

### 5.6 Scan History
- [ ] `GET /scanner/history` endpoint returns recent scan runs
- [ ] History panel in sidebar or `/history` page

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
