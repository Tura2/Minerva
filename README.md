# Minerva — Trading Research Copilot

Automated swing-trading research with cost-efficient multi-market architecture.

## Overview

Minerva combines a **Python screener** (deterministic), **LLM workflows** (OpenRouter), and a **web dashboard** (Next.js) to generate structured trade plans from watchlist symbols.

**Supported markets:** US (S&P 500 / Nasdaq) · TASE (Tel Aviv Stock Exchange)

**Current status:** Phase 3 complete — workflow engine live with full `technical-swing` pipeline.

---

## Project Structure

```
Minerva/
├── CLAUDE.md               # Claude Code instructions
├── .env.example            # Environment variables template
│
├── docs/                   # Project documentation
│   ├── API.md              # Full API endpoint reference
│   ├── ARCHITECTURE.md     # System design & DB schema
│   ├── WORKFLOW.md         # Workflow engine node docs
│   ├── DEPLOYMENT.md       # Railway + Vercel setup
│   ├── MinervaPRD.md       # Product specification
│   └── DEVELOPMENT_PLAN.md # Phase-by-phase build plan
│
├── frontend/               # Next.js 15 App Router
│   └── src/
│       ├── app/            # Pages & layouts
│       ├── components/     # React components
│       └── lib/            # API client
│
├── backend/                # FastAPI · Python 3.11
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── routers/        # scanner, research, market, watchlist
│   │   └── services/       # indicators, pre_screen, market_breadth,
│   │       │               # position_sizer_service, prompts, openrouter_client
│   │       └── workflows/  # swing_trade.py (6-node pipeline)
│   ├── scripts/
│   │   └── migrations/     # 001_initial_schema.sql, 002_ticket_metadata.sql
│   ├── requirements.txt
│   └── pyproject.toml
│
└── reference/              # Source skills (read-only)
    └── claude-trading-skills/
```

---

## Quick Start

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env   # fill in OPENROUTER_API_KEY, SUPABASE_URL, SUPABASE_KEY
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
# .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

---

## Core Workflow: `technical-swing`

```
POST /research/execute { symbol, market, portfolio_size, max_risk_pct }
  ↓
1. Fetch 1yr OHLC + compute MA20/50/150/200, ATR14, RSI14, VCP
2. Pre-screen: Minervini 7-point Stage 2 gate (FAIL → 422, use force=true)
3. Fetch market breadth (Monty's CSV — US only)
4. LLM research via OpenRouter → structured JSON trade plan
5. Compute position size (fixed-fractional)
6. Persist research ticket to Supabase
```

**Output — Research Ticket:**

```json
{
  "entry_price": 192.50,
  "stop_loss": 186.00,
  "target": 208.00,
  "position_size": 53,
  "max_risk": 344.50,
  "bullish_probability": 0.72,
  "key_triggers": ["Break above $192.50 pivot", "Volume confirmation"],
  "status": "pending"
}
```

---

## API Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET/POST/DELETE | `/watchlist` | Manage scan universe |
| POST | `/scanner/scan` | Run screener against watchlist |
| GET | `/scanner/candidates` | Latest scan results |
| GET | `/market/history` | OHLC candles (epoch ms, staleness flag) |
| POST | `/research/execute` | Run full research workflow |
| GET | `/research/tickets` | List research tickets |
| PATCH | `/research/tickets/{id}/status` | Approve / reject |

Full reference: [docs/API.md](docs/API.md)

---

## Environment Variables

```bash
OPENROUTER_API_KEY=sk_or_...
RESEARCH_MODEL=openai/gpt-4-turbo
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for full setup.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 18, Tailwind CSS, lightweight-charts |
| Backend | FastAPI, Python 3.11, yfinance, pandas |
| LLM | OpenRouter API (configurable model) |
| Database | Supabase PostgreSQL |
| Hosting | Vercel (frontend) · Railway (backend) |

---

## Documentation

- [docs/API.md](docs/API.md) — API endpoint reference
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System design & DB schema
- [docs/WORKFLOW.md](docs/WORKFLOW.md) — Workflow engine details
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Deployment guide
- [docs/MinervaPRD.md](docs/MinervaPRD.md) — Product specification
- [docs/DEVELOPMENT_PLAN.md](docs/DEVELOPMENT_PLAN.md) — Build plan & progress
