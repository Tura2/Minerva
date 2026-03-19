"""Watchlist router — CRUD for user-tracked symbols (also the scan universe)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.db import get_db
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class WatchlistAddRequest(BaseModel):
    symbol: str
    market: str  # "US" or "TASE"
    notes: Optional[str] = None


class WatchlistItem(BaseModel):
    id: str
    symbol: str
    market: str
    added_at: str
    notes: Optional[str] = None


@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(market: Optional[str] = None):
    """Return all watchlist items, optionally filtered by market."""
    db = get_db()
    query = db.table("watchlist_items").select("*").order("added_at", desc=True)
    if market:
        query = query.eq("market", market.upper())
    result = query.execute()
    return result.data


@router.post("", response_model=WatchlistItem, status_code=201)
async def add_to_watchlist(req: WatchlistAddRequest):
    """Add a symbol to the watchlist."""
    symbol = req.symbol.upper().strip()
    market = req.market.upper().strip()

    if market not in ("US", "TASE"):
        raise HTTPException(status_code=400, detail="market must be US or TASE")

    db = get_db()
    try:
        result = db.table("watchlist_items").insert({
            "symbol": symbol,
            "market": market,
            "notes": req.notes,
        }).execute()
        return result.data[0]
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"{symbol} already in watchlist for {market}")
        logger.error(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to add symbol")


@router.delete("/{item_id}", status_code=204)
async def remove_from_watchlist(item_id: str):
    """Remove a symbol from the watchlist by ID."""
    db = get_db()
    result = db.table("watchlist_items").delete().eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
