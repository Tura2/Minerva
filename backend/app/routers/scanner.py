"""Scanner router — run scans and retrieve candidates."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from app.services.scanner import ScannerService
from app.db import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
scanner = ScannerService()


class ScanRequest(BaseModel):
    market: str  # "US" or "TASE"
    limit: int = 50
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[int] = None


class CandidateOut(BaseModel):
    id: Optional[str] = None
    symbol: str
    market: str
    price: Optional[float] = None
    volume: Optional[int] = None
    score: Optional[float] = None
    screened_at: Optional[str] = None


class ScanResponse(BaseModel):
    scan_id: str
    market: str
    candidates: list[CandidateOut]
    total_in_watchlist: int
    total_passed: int
    ran_at: str


@router.post("/scan", response_model=ScanResponse)
async def run_scan(req: ScanRequest):
    """
    Run the screener against the watchlist for the given market.
    1. Load symbols from watchlist_items (scan universe)
    2. Fetch OHLC data via yfinance
    3. Apply market-aware filters
    4. Persist scan_history + candidates to DB
    """
    market = req.market.upper()
    if market not in ("US", "TASE"):
        raise HTTPException(status_code=400, detail="market must be US or TASE")

    db = get_db()

    # 1. Load universe from watchlist
    symbols = await scanner.load_symbols(market, db)
    if not symbols:
        raise HTTPException(
            status_code=422,
            detail=f"No symbols in watchlist for {market}. Add some via /watchlist first."
        )

    # 2. Create scan_history record (running)
    scan_record = db.table("scan_history").insert({
        "market": market,
        "status": "running",
        "filters": {
            "min_price": req.min_price,
            "max_price": req.max_price,
            "min_volume": req.min_volume,
        },
    }).execute()
    scan_id = scan_record.data[0]["id"]

    try:
        # 3. Fetch + filter
        data = await scanner.fetch_market_data(symbols, market)
        candidates = scanner.apply_filters(
            data,
            market=market,
            min_price=req.min_price,
            max_price=req.max_price,
            min_volume=req.min_volume,
        )
        candidates = candidates[:req.limit]

        # 4. Persist candidates
        if candidates:
            rows = [{**c, "scan_id": scan_id} for c in candidates]
            db.table("candidates").insert(rows).execute()

        # 5. Update scan_history to completed
        ran_at = datetime.now(timezone.utc).isoformat()
        db.table("scan_history").update({
            "status": "completed",
            "candidate_count": len(candidates),
            "ran_at": ran_at,
        }).eq("id", scan_id).execute()

    except Exception as e:
        db.table("scan_history").update({"status": "failed"}).eq("id", scan_id).execute()
        logger.error(f"Scan failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}")

    return ScanResponse(
        scan_id=scan_id,
        market=market,
        candidates=[CandidateOut(**c) for c in candidates],
        total_in_watchlist=len(symbols),
        total_passed=len(candidates),
        ran_at=ran_at,
    )


@router.get("/candidates", response_model=list[CandidateOut])
async def get_recent_candidates(
    market: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
):
    """Return candidates from the most recent scan, optionally filtered by market."""
    db = get_db()

    # Find the most recent completed scan
    scan_query = db.table("scan_history").select("id").eq("status", "completed").order("ran_at", desc=True)
    if market:
        scan_query = scan_query.eq("market", market.upper())
    scan_result = scan_query.limit(1).execute()

    if not scan_result.data:
        return []

    scan_id = scan_result.data[0]["id"]
    result = db.table("candidates").select("*").eq("scan_id", scan_id).order("score", desc=True).limit(limit).execute()
    return result.data


@router.get("/history")
async def get_scan_history(
    market: Optional[str] = Query(None),
    limit: int = Query(20, le=100),
):
    """Return recent scan runs."""
    db = get_db()
    query = db.table("scan_history").select("*").order("ran_at", desc=True).limit(limit)
    if market:
        query = query.eq("market", market.upper())
    result = query.execute()
    return result.data
