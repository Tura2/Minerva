# Minerva - Trading Research Copilot

Automated swing-trading research with cost-efficient multi-market architecture.

## Overview

Minerva is a web application that combines:
- **Python screener** (backend) for quantitative filtering via yfinance
- **LLM workflows** (OpenRouter) for qualitative analysis
- **Web dashboard** (frontend) for candidate review and research ticket management

### Supported Markets
- **US**: S&P 500, Nasdaq
- **TASE**: Tel Aviv Stock Exchange

### Key Outputs
- Structured **Research Tickets** with explicit entry/exit rules
- Risk-aware position sizing
- Market-localized currency and hours

## Project Structure

```
Minerva/
├── CLAUDE.md               # Claude Code instructions
├── MinervaPRD.md           # Product specification
├── .env.example            # Environment variables template
├── README.md               # This file
│
├── reference/              # Source material (read-only)
│   └── claude-trading-skills/
│
├── frontend/               # Next.js App Router
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   └── lib/
│   ├── package.json
│   ├── tsconfig.json
│   └── ...
│
└── backend/                # FastAPI
    ├── app/
    │   ├── main.py
    │   ├── config.py
    │   ├── routers/
    │   ├── services/
    │   ├── models/
    │   └── utils/
    ├── requirements.txt
    ├── pyproject.toml
    └── ...
```

## Quick Start

### Backend Setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp ../.env.example .env
# Edit .env with your API keys

# Run development server
uvicorn app.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp ../.env.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000

# Run development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Environment Variables

Required variables (copy from `.env.example` to `.env`):

```bash
# OpenRouter LLM API
OPENROUTER_API_KEY=sk_your_key_here
RESEARCH_MODEL=openai/gpt-4-turbo

# Supabase Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_key_here

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Development Workflow

### Adding a New Research Workflow

1. Identify source skill in `reference/claude-trading-skills/skills/`
2. Create workflow state schema in `backend/app/models/`
3. Implement workflow handler in `backend/app/services/workflow.py`
4. Add endpoint in `backend/app/routers/research.py`
5. Update frontend UI to expose workflow option

### Testing

Backend:
```bash
cd backend
pytest                    # Run all tests
pytest --cov=app        # With coverage
```

Frontend:
```bash
cd frontend
npm test                 # Run tests
npm run lint            # ESLint check
```

## Deployment

### Frontend (Vercel)

```bash
# Push to GitHub - Vercel auto-deploys main branch
# Set environment variables in Vercel dashboard
```

### Backend (Railway)

```bash
# Connect GitHub repo to Railway
# Set environment variables in Railway dashboard
# Railway auto-detects Python + FastAPI
```

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15+, React 18, Tailwind CSS, lightweight-charts |
| Backend | FastAPI, Python 3.9+ |
| Data | yfinance, pandas |
| LLM | OpenRouter API |
| Database | Supabase PostgreSQL |
| Hosting | Vercel (frontend), Railway (backend) |

## Key Documentation

- [CLAUDE.md](CLAUDE.md) - Claude Code instructions and best practices
- [MinervaPRD.md](MinervaPRD.md) - Complete product specification
- [backend/README.md](backend/README.md) - Backend architecture and API docs
- [frontend/README.md](frontend/README.md) - Frontend setup and component docs

## Support

For issues or feature requests, check the project documentation or submit a GitHub issue.
