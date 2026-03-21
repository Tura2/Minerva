"""
Watchlists router — CRUD for named watchlists.

A watchlist is a named container for watchlist_items.
Each item belongs to exactly one watchlist (watchlist_id FK).
Deleting a watchlist cascades to its items.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.db import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class WatchlistOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    created_at: str
    item_count: int = 0
    us_count: int = 0
    tase_count: int = 0


class CreateWatchlistRequest(BaseModel):
    name: str
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 80:
            raise ValueError("name must be 80 characters or fewer")
        return v


class UpdateWatchlistRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be empty")
            if len(v) > 80:
                raise ValueError("name must be 80 characters or fewer")
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=list[WatchlistOut])
async def list_watchlists():
    """Return all watchlists with per-list item counts."""
    db = get_db()

    lists = db.table("watchlists").select("*").order("created_at", desc=False).execute().data

    # Fetch item counts in one query, grouped by watchlist_id + market
    items = db.table("watchlist_items").select("watchlist_id, market").execute().data

    # Build count maps
    total: dict[str, int] = {}
    us: dict[str, int] = {}
    tase: dict[str, int] = {}
    for row in items:
        wid = row["watchlist_id"]
        total[wid] = total.get(wid, 0) + 1
        if row["market"] == "US":
            us[wid] = us.get(wid, 0) + 1
        else:
            tase[wid] = tase.get(wid, 0) + 1

    return [
        WatchlistOut(
            **wl,
            item_count=total.get(wl["id"], 0),
            us_count=us.get(wl["id"], 0),
            tase_count=tase.get(wl["id"], 0),
        )
        for wl in lists
    ]


@router.post("", response_model=WatchlistOut, status_code=201)
async def create_watchlist(req: CreateWatchlistRequest):
    """Create a new named watchlist."""
    db = get_db()
    try:
        result = db.table("watchlists").insert({
            "name": req.name,
            "description": req.description,
        }).execute()
        row = result.data[0]
        return WatchlistOut(**row, item_count=0, us_count=0, tase_count=0)
    except Exception as e:
        logger.error(f"Create watchlist failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to create watchlist")


@router.patch("/{watchlist_id}", response_model=WatchlistOut)
async def update_watchlist(watchlist_id: str, req: UpdateWatchlistRequest):
    """Rename or update description of a watchlist."""
    db = get_db()

    existing = db.table("watchlists").select("*").eq("id", watchlist_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    updates: dict = {}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description

    if not updates:
        row = existing.data[0]
    else:
        result = db.table("watchlists").update(updates).eq("id", watchlist_id).execute()
        row = result.data[0]

    # Recount
    items = db.table("watchlist_items").select("market").eq("watchlist_id", watchlist_id).execute().data
    us = sum(1 for i in items if i["market"] == "US")
    tase = sum(1 for i in items if i["market"] == "TASE")
    return WatchlistOut(**row, item_count=len(items), us_count=us, tase_count=tase)


@router.delete("/{watchlist_id}", status_code=204)
async def delete_watchlist(watchlist_id: str):
    """
    Delete a watchlist and all its items (CASCADE).
    The last watchlist cannot be deleted.
    """
    db = get_db()

    # Guard: at least one list must remain
    all_lists = db.table("watchlists").select("id").execute().data
    if len(all_lists) <= 1:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete the last watchlist. Create another list first.",
        )

    result = db.table("watchlists").delete().eq("id", watchlist_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Watchlist not found")
