# Minerva — Deployment Guide

## Environment Variables

Copy `.env.example` to `backend/.env` and fill in all values.

```bash
# ── LLM ──────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY=sk_or_...
RESEARCH_MODEL=openai/gpt-4-turbo          # or anthropic/claude-3-5-sonnet
RESEARCH_OPENROUTER_RETRY_COUNT=3
RESEARCH_OPENROUTER_BACKOFF_SECONDS=2

# ── Database ─────────────────────────────────────────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJ...  # anon key

# ── App ──────────────────────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000,https://your-vercel-app.vercel.app

# ── Frontend (set in Vercel dashboard or .env.local) ─────────────────────
NEXT_PUBLIC_API_URL=https://your-railway-app.railway.app
```

---

## Database Setup (Supabase)

1. Create a project at [supabase.com](https://supabase.com)
2. Run migrations in order:
   ```sql
   -- In Supabase SQL editor or via MCP tool:
   -- 1. backend/scripts/migrations/001_initial_schema.sql
   -- 2. backend/scripts/migrations/002_ticket_metadata.sql
   ```
3. Copy `SUPABASE_URL` and `SUPABASE_KEY` (anon key) from Project Settings → API

---

## Backend (Railway)

1. Connect GitHub repo at [railway.app](https://railway.app)
2. Railway auto-detects Python + FastAPI via `requirements.txt`
3. Set all env vars from the table above in Railway dashboard → Variables
4. Create `Procfile` in `backend/`:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
5. Set root directory to `backend/` in Railway service settings
6. Verify health check: `GET /health` → `{"status": "ok"}`

---

## Frontend (Vercel)

1. Import GitHub repo at [vercel.com](https://vercel.com)
2. Set build configuration:
   ```
   Root Directory:   frontend
   Build Command:    npm run build
   Output Directory: .next
   ```
3. Add environment variable: `NEXT_PUBLIC_API_URL=https://your-app.railway.app`
4. Enable automatic deployments on `main` branch push

---

## Local Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env   # then fill in your keys
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
# create .env.local with: NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

---

## CI / Production Checklist

- [ ] `GET /health` returns `200 ok` on Railway URL
- [ ] CORS origins include Vercel production URL
- [ ] Supabase migrations 001 + 002 applied
- [ ] `OPENROUTER_API_KEY` set and has credits
- [ ] `RESEARCH_MODEL` set to desired model
- [ ] Frontend `.env.local` / Vercel env points to Railway backend URL
- [ ] Test: add watchlist item → run scan → execute research → view ticket
