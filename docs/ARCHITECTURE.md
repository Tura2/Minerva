# Minerva — Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend (Vercel)                       │
│                    Next.js 15 App Router                    │
│  ├─ /candidates      Candidate queue + Run Scan             │
│  ├─ /research/[id]   Ticket viewer + Approve/Reject         │
│  ├─ /watchlist       Symbol management (scan universe)      │
│  └─ /history         Scan history log                       │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP/REST
┌──────────────────────────▼──────────────────────────────────┐
│                   Backend (Railway)                         │
│                  FastAPI · Python 3.11                      │
│                                                             │
│  /scanner    ScannerService    yfinance + pandas filtering  │
│  /market     MarketData        OHLC history + normalization │
│  /watchlist  WatchlistCRUD     Scan universe management     │
│  /research   WorkflowEngine    LangGraph-style pipeline     │
│                                                             │
│  services/                                                  │
│  ├─ indicators.py          MA, ATR, RSI, VCP detection      │
│  ├─ market_breadth.py      Monty's uptrend CSV (US only)    │
│  ├─ pre_screen.py          Stage 2 Trend Template gate      │
│  ├─ position_sizer_service.py  Fixed-fractional sizing      │
│  ├─ prompts.py             LLM prompt construction          │
│  ├─ openrouter_client.py   OpenRouter API + retry           │
│  └─ workflows/                                              │
│      └─ swing_trade.py     6-node sequential pipeline       │
└──────────────────────────┬──────────────────────────────────┘
                           │ SQL / Supabase Client
┌──────────────────────────▼──────────────────────────────────┐
│               Persistence (Supabase PostgreSQL)             │
│  watchlist_items     Scan universe (user-managed symbols)   │
│  scan_history        Scan run log                           │
│  candidates          Screened symbols per scan run          │
│  research_tickets    LLM-generated trade plans              │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Scan Flow
```
User adds symbols to /watchlist
        ↓
POST /scanner/scan
        ↓
ScannerService.load_symbols(market, db)   ← reads watchlist_items
        ↓
ScannerService.fetch_market_data()        ← yfinance batch fetch
        ↓
ScannerService.apply_filters()            ← market-aware thresholds
        ↓
Persist → candidates + scan_history tables
```

### Research Flow
```
POST /research/execute { symbol, market, portfolio_size, max_risk_pct }
        ↓
Node 1: _node_fetch_data()
  └─ yfinance 1yr OHLC → compute_indicators() [MA20/50/150/200, ATR14, RSI14, VCP]
        ↓
Node 2: _node_pre_screen()
  └─ Minervini 7-point Trend Template + liquidity check
  └─ FAIL → 422 with check details (user can force=true to override)
        ↓
Node 3: _node_fetch_breadth()
  └─ Monty's uptrend ratio CSV (US) / neutral stub (TASE)
        ↓
Node 4: _node_llm_research()
  └─ OpenRouter JSON call with combined prompt (4 skills merged)
  └─ Retry: tenacity exponential backoff
        ↓
Node 5: _node_compute_sizing()
  └─ Fixed-fractional: shares = floor((account × risk%) / (entry − stop))
        ↓
Node 6: _node_persist_ticket()
  └─ Insert to research_tickets with metadata JSONB
```

---

## Database Schema

### `watchlist_items`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| symbol | TEXT | e.g. `AAPL`, `OPCE` (no .TA suffix stored) |
| market | TEXT | `US` or `TASE` |
| added_at | TIMESTAMPTZ | |
| notes | TEXT | optional |

Unique constraint: `(symbol, market)`

### `scan_history`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| market | TEXT | |
| ran_at | TIMESTAMPTZ | |
| candidate_count | INTEGER | |
| filters | JSONB | min_price, max_price, min_volume overrides |
| status | TEXT | `running` / `completed` / `failed` |

### `candidates`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| scan_id | UUID FK → scan_history | |
| symbol | TEXT | |
| market | TEXT | |
| price | DECIMAL | latest close |
| volume | BIGINT | latest volume |
| score | DECIMAL | volatility × 50 + vol_ratio × 10 |
| screened_at | TIMESTAMPTZ | |
| metadata | JSONB | raw yfinance fields |

### `research_tickets`
| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| symbol | TEXT | |
| market | TEXT | |
| workflow_type | TEXT | e.g. `technical-swing` |
| entry_price | DECIMAL | |
| stop_loss | DECIMAL | |
| target | DECIMAL | |
| position_size | INTEGER | shares |
| max_risk | DECIMAL | dollar risk |
| currency | TEXT | `USD` or `ILS` |
| bullish_probability | DECIMAL | 0.0–1.0 |
| key_triggers | TEXT[] | from LLM output |
| status | TEXT | `pending` / `approved` / `rejected` |
| created_at | TIMESTAMPTZ | |
| updated_at | TIMESTAMPTZ | auto-updated via trigger |
| metadata | JSONB | full analysis blob (rationale, caveats, breadth, sizing detail, model used) |

Migrations: `backend/scripts/migrations/001_initial_schema.sql`, `002_ticket_metadata.sql`

---

## Skill Adaptation

All LLM prompts adapt from `reference/claude-trading-skills/`:

| Source Skill | Adapted Into |
|-------------|-------------|
| `technical-analyst` | Trend/S&R analysis in `prompts.py` |
| `vcp-screener` | VCP detection in `indicators.py` + prompt |
| `uptrend-analyzer` | `market_breadth.py` (CSV port) + prompt context |
| `position-sizer` | `position_sizer_service.py` (full port) |

**Rule:** Only swing-trade focused skills. Exclude: options, dividends, long-term, statistical arb.

---

## Market Localization

| Setting | US | TASE |
|---------|----|----|
| Currency | USD ($) | ILS (₪) |
| yfinance suffix | none | `.TA` appended automatically |
| Trading hours | 9:30–16:00 ET Mon–Fri | 9:15–17:00 IL Sun–Thu |
| Min avg volume | 500,000 | 50,000 |
| Price range | $5–$2,000 | ₪1–₪500 |
| Market breadth | Available (Monty's CSV) | Neutral stub (no data source) |

---

## Key Design Decisions

- **Watchlist as universe:** No static CSVs. Scan universe = `watchlist_items` table.
- **Cost-first:** Deterministic pre-screen runs before any LLM call. Fail fast, save tokens.
- **Pre-screen bypass:** `force=true` on execute lets user override a failing pre-screen.
- **Single LLM call:** All 4 skills merged into one prompt per symbol. No multi-turn chains.
- **JSON mode:** OpenRouter `response_format: {"type": "json_object"}` enforced. No parsing hacks.
- **Market breadth context:** US gets real uptrend ratio; TASE gets neutral assumption (noted in prompt).
