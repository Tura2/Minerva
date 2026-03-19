# Product Requirements Document (PRD)
## Project: Minerva (Web Trading Research Copilot)

### 0. Core Architecture Directive
Minerva is strictly an adaptation and orchestration layer for strategy skills from `tradermonty/claude-trading-skills`.
**Minerva is strictly focused on Swing Trading and short-to-medium term trading. Skills related to dividends, long-term investing, options trading, or statistical arbitrage will NOT be imported or supported.**

### 1. Overview
Project Minerva is a web application that automates swing-trading research with a cost-efficient architecture.
The system combines a hosted Python screener for quantitative filtering and adapted AI workflows for qualitative analysis.

Minerva v1 is designed to support both:
- US markets (S&P 500 and Nasdaq)
- TASE (Tel Aviv Stock Exchange)

The product returns structured Research Tickets with explicit entry/exit rules and risk-aware position sizing.

### 2. Core Objectives
- **Cost Efficiency:** Run data-heavy screening in Python first, and call LLMs only for shortlisted candidates.
- **Dual-Market Support:** Handle both US and TASE market conventions in one product.
- **Agentic Workflow Adaptation Control:** Port source skills into deterministic workflow steps and output contracts for repeatability.
- **Production-Ready Web Delivery:** Frontend on Vercel, backend on managed hosting, cloud database.

### 2.1 Source Skill Adaptation Rules
- Primary source repository: `tradermonty/claude-trading-skills`.
- Every workflow capability must include traceability to source skill files and adaptation notes.
- All adapted prompts must be OpenRouter-compatible and platform-agnostic (no Anthropic CLI coupling).
- Output contracts must be structured and validated (JSON first, optional YAML where required by downstream contracts).
- US and TASE localization is mandatory for each adapted skill path.

### 3. Product Decisions (Locked for v1)
- **Frontend Hosting:** Vercel
- **Backend Hosting:** Railway
- **Backend Runtime:** Single Python FastAPI service
- **Database:** Supabase Postgres
- **Authentication:** No auth in v1 (private/single-user mode)
- **Scan Triggering:** Manual scans only in v1
- **Market Scope:** US + TASE from day one

### 4. Tech Stack (v1)
- **Frontend UI:** Next.js (App Router)
- **Frontend Hosting:** Vercel
- **Backend API:** FastAPI (Python)
- **Data/Screener Engine:** Python 3.x + yfinance + pandas
- **LLM Provider:** OpenRouter API
- **Agentic Layer:** Workflow engine in backend service (LangGraph-compatible design)
- **Database:** Supabase Postgres
- **Report Format:** Structured JSON (optional YAML export)

### 5. Key Functional Components
1. **Scanner Service (Backend):** Fetches and filters symbols from US + TASE using yfinance and predefined trigger logic.
2. **Workflow Engine (Backend):** Executes adapted source-skill playbooks and guardrails, then generates Research Tickets.
3. **Risk & Position Sizing (Backend):** Computes share quantity and validates max-risk constraints.
4. **Web Dashboard (Frontend):** Candidate queue, workflow controls, ticket viewer, and watchlist.
5. **Persistence Layer:** Stores candidates, tickets, watchlist items, and run history in Supabase Postgres.

### 6. v1 Non-Goals
- Multi-user collaboration
- Broker execution integration
- Real-time streaming market data
- Automated scheduled scans
- Authoring new proprietary strategy logic independent of source skill adaptation

#### 7.1 OpenRouter Research Connectivity
- Research execution uses a dedicated HTTP OpenRouter client in backend services.
- Requests enforce strict JSON response format for deterministic node outputs.
- Retry policy is implemented for transient provider failures:
	- Retry on HTTP 429 and 5xx
	- Retry on timeout/transport exceptions
	- Exponential backoff per retry attempt
- Workflow routing is executed through LangGraph-compatible state graph orchestration by workflow type.
- Deduplication-aware persistence can return cached ticket outcomes and short-circuit repeated LLM calls.

Required runtime variables:
- `OPENROUTER_API_KEY`
- `RESEARCH_MODEL`
- `RESEARCH_OPENROUTER_RETRY_COUNT`
- `RESEARCH_OPENROUTER_BACKOFF_SECONDS`

#### 7.2 Data Fetching and Chart Representation
- Frontend retrieves market history through backend endpoint `/market/history`.
- Frontend API normalization converts candles into chart-ready format (`time -> ts` in epoch ms, plus OHLC values).
- Ticket detail page combines persisted ticket payload with fetched market candles.
- Candlestick rendering is implemented using `lightweight-charts`.
- Execution levels are represented on-chart from ticket context:
	- Support line (stop)
	- Resistance line (target)
	- Checkpoint line (entry where available)
- Chart loading states and fullscreen toggle are implemented in ticket detail UX.

#### 7.3 Chart Display and Edit Scope (Current)
- Responsive resize behavior and interaction controls (pan/zoom) are active.
- Overlay and annotation plumbing exists for EMA lines, support/resistance, checkpoints, trailing stop, and trade overlays.
- Current edit capability is interactive viewing only (non-persistent).
- Persisted manual chart editing (for example drag-to-edit lines with save-to-database) is not in v1 baseline yet.

### 9. Guardrails for Ongoing Rebuild Work
- Preserve market-aware defaults and validation behavior:
	- US uses USD defaults.
	- TASE uses ILS defaults.
- Keep explicit rejection reasons mandatory for invalid candidates or trades.
- Prefer deterministic validation and structured contracts before LLM-dependent nodes.
- Keep v1 manual and unauthenticated until scan -> research -> ticket loop remains stable under iteration.