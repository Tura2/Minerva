"""
Watchlist items router — CRUD for symbols inside a named watchlist.

All write operations require a watchlist_id.
The scanner reads from this table (optionally scoped to a watchlist).
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WatchlistAddRequest(BaseModel):
    symbol: str
    market: str          # "US" or "TASE"
    watchlist_id: str    # required — every item belongs to a list
    notes: Optional[str] = None


class WatchlistMoveRequest(BaseModel):
    watchlist_id: str    # destination list id


class WatchlistItem(BaseModel):
    id: str
    symbol: str
    market: str
    watchlist_id: str
    added_at: str
    notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(
    market: Optional[str] = None,
    watchlist_id: Optional[str] = None,
):
    """
    Return watchlist items.
    - watchlist_id: filter to a specific list
    - market: further filter by US / TASE
    """
    db = get_db()
    query = db.table("watchlist_items").select("*").order("added_at", desc=True)
    if watchlist_id:
        query = query.eq("watchlist_id", watchlist_id)
    if market:
        query = query.eq("market", market.upper())
    return query.execute().data


@router.post("", response_model=WatchlistItem, status_code=201)
async def add_to_watchlist(req: WatchlistAddRequest):
    """Add a symbol to a named watchlist."""
    symbol = req.symbol.upper().strip()
    market = req.market.upper().strip()

    if market not in ("US", "TASE"):
        raise HTTPException(status_code=400, detail="market must be US or TASE")

    db = get_db()

    # Verify the target watchlist exists
    wl = db.table("watchlists").select("id").eq("id", req.watchlist_id).execute()
    if not wl.data:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    try:
        result = db.table("watchlist_items").insert({
            "symbol": symbol,
            "market": market,
            "watchlist_id": req.watchlist_id,
            "notes": req.notes,
        }).execute()
        return result.data[0]
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail=f"{symbol} ({market}) is already in this watchlist.",
            )
        logger.error(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=500, detail="Failed to add symbol")


@router.patch("/{item_id}", response_model=WatchlistItem)
async def move_watchlist_item(item_id: str, req: WatchlistMoveRequest):
    """Move an item to a different watchlist."""
    db = get_db()

    # Verify destination exists
    wl = db.table("watchlists").select("id").eq("id", req.watchlist_id).execute()
    if not wl.data:
        raise HTTPException(status_code=404, detail="Destination watchlist not found")

    result = db.table("watchlist_items").update(
        {"watchlist_id": req.watchlist_id}
    ).eq("id", item_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return result.data[0]


@router.delete("/{item_id}", status_code=204)
async def remove_from_watchlist(item_id: str):
    """Remove a symbol from its watchlist."""
    db = get_db()
    result = db.table("watchlist_items").delete().eq("id", item_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
