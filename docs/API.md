# Minerva API Reference

Base URL: `http://localhost:8000` (dev) | `https://your-railway-app.railway.app` (prod)

All endpoints return JSON. Errors follow `{"detail": "..."}` shape.

---

## Health

### `GET /health`
```json
{ "status": "ok", "service": "minerva-backend" }
```

---

## Watchlist

The watchlist is the **scan universe** — symbols added here are what the scanner processes.

### `GET /watchlist`
List all watchlist items, optionally filtered by market.

**Query params:** `market` (optional) — `US` or `TASE`

**Response:**
```json
[
  { "id": "uuid", "symbol": "AAPL", "market": "US", "added_at": "...", "notes": null }
]
```

### `POST /watchlist`
Add a symbol to the watchlist.

**Body:**
```json
{ "symbol": "AAPL", "market": "US", "notes": "optional note" }
```

**Errors:** `409` if symbol already exists for that market.

### `DELETE /watchlist/{item_id}`
Remove a symbol. Returns `204 No Content`.

---

## Scanner

### `POST /scanner/scan`
Run the screener against the watchlist for a given market.

**Body:**
```json
{
  "market": "US",
  "limit": 50,
  "min_price": null,
  "max_price": null,
  "min_volume": null
}
```

**Flow:** Load watchlist symbols → fetch yfinance OHLC → apply market-aware filters → persist to DB.

**Response:**
```json
{
  "scan_id": "uuid",
  "market": "US",
  "candidates": [
    { "id": "uuid", "symbol": "AAPL", "market": "US", "price": 190.5, "volume": 1200000, "score": 72.3, "screened_at": "..." }
  ],
  "total_in_watchlist": 15,
  "total_passed": 8,
  "ran_at": "2026-03-19T10:00:00Z"
}
```

**Market defaults:**
| Market | Min Volume | Price Range |
|--------|-----------|-------------|
| US     | 500,000   | $5 – $2,000 |
| TASE   | 50,000    | ₪1 – ₪500   |

### `GET /scanner/candidates`
Return candidates from the most recent completed scan.

**Query params:** `market` (optional), `limit` (default 50, max 200)

### `GET /scanner/history`
Return recent scan runs.

**Query params:** `market` (optional), `limit` (default 20, max 100)

---

## Market Data

### `GET /market/history`
Fetch OHLC candlestick data for a symbol.

**Query params:**
| Param | Required | Default | Notes |
|-------|----------|---------|-------|
| `symbol` | Yes | — | Ticker without `.TA` suffix |
| `market` | Yes | — | `US` or `TASE` |
| `period` | No | `1y` | yfinance period string |
| `interval` | No | `1d` | yfinance interval |
| `ticket_id` | No | — | UUID — overlays execution levels from a research ticket |

**Response:**
```json
{
  "symbol": "AAPL",
  "market": "US",
  "candles": [
    { "ts": 1710867600000, "open": 190.2, "high": 191.5, "low": 190.0, "close": 191.0, "volume": 1200000 }
  ],
  "execution_levels": { "entry": 192.0, "stop": 186.0, "target": 205.0 },
  "last_updated": "2026-03-19T16:00:00Z",
  "is_stale": false
}
```

**Notes:**
- Timestamps normalized to epoch milliseconds (`ts`)
- `is_stale: true` if last candle is > 24 hours old
- TASE symbols get `.TA` suffix applied automatically

### `GET /market/symbols/{market}`
Return watchlist symbols for a given market (`US` or `TASE`).

---

## Research

### `POST /research/execute`
Execute a research workflow on a symbol. Runs the full 6-node pipeline.

**Body:**
```json
{
  "symbol": "AAPL",
  "market": "US",
  "workflow_type": "technical-swing",
  "portfolio_size": 100000,
  "max_risk_pct": 1.0,
  "force": false
}
```

**Fields:**
| Field | Required | Notes |
|-------|----------|-------|
| `symbol` | Yes | Ticker (no `.TA` suffix) |
| `market` | Yes | `US` or `TASE` |
| `workflow_type` | No | Default `technical-swing` |
| `portfolio_size` | Yes | Account size in local currency (USD/ILS) |
| `max_risk_pct` | Yes | Max % of account to risk per trade (e.g. `1.0`) |
| `force` | No | Skip pre-screen gate — default `false` |

**Success response:** Full research ticket (see schema below).

**Pre-screen failure (422):**
```json
{
  "detail": {
    "error": "pre_screen_failed",
    "pre_screen_summary": "FAIL — 3 check(s) failed: ...",
    "checks": { "price_above_ma150": false, "min_volume": true, ... },
    "reasons": ["Price 45.20 below MA150 62.10", ...],
    "vcp": { "contraction_count": 1, "is_vcp": false },
    "force_hint": "Set force=true to run LLM research anyway"
  }
}
```

### `GET /research/tickets`
List research tickets.

**Query params:** `market`, `status` (`pending`/`approved`/`rejected`), `limit` (default 50, max 200)

### `GET /research/tickets/{ticket_id}`
Fetch a single research ticket by UUID.

### `PATCH /research/tickets/{ticket_id}/status`
Approve or reject a ticket.

**Query param:** `status` — `approved`, `rejected`, or `pending`

---

## Research Ticket Schema

```json
{
  "id": "uuid",
  "symbol": "AAPL",
  "market": "US",
  "workflow_type": "technical-swing",
  "entry_price": 192.50,
  "stop_loss": 186.00,
  "target": 208.00,
  "position_size": 53,
  "max_risk": 344.50,
  "currency": "USD",
  "bullish_probability": 0.72,
  "key_triggers": ["Break above $192.50 pivot", "Volume confirmation", "Market breadth holding Bull zone"],
  "status": "pending",
  "created_at": "2026-03-19T10:00:00Z",
  "metadata": {
    "entry_rationale": "...",
    "stop_rationale": "...",
    "target_rationale": "...",
    "risk_reward_ratio": 2.4,
    "setup_quality": "A",
    "trend_context": "...",
    "volume_context": "...",
    "market_breadth_context": "...",
    "caveats": ["Earnings in 3 weeks", "Market in Neutral breadth zone"],
    "pre_screen": { "passed": true, "checks": {...}, "vcp": {...} },
    "breadth_zone": "Bull",
    "breadth_score": 68.4,
    "research_model": "openai/gpt-4-turbo",
    "portfolio_size": 100000,
    "max_risk_pct": 1.0
  }
}
```
