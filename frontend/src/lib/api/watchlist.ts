import { AxiosError } from "axios";
import apiClient from "../apiClient";
import { ApiError, Market, Watchlist, WatchlistItem } from "../types";

function toApiError(err: unknown): never {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail ?? err.message;
    throw new ApiError(err.response?.status ?? 0, detail);
  }
  throw new ApiError(0, String(err));
}

// ── Named watchlists CRUD ──────────────────────────────────────────────────

export async function listWatchlists(): Promise<Watchlist[]> {
  try {
    const res = await apiClient.get<Watchlist[]>("/watchlists");
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function createWatchlist(
  name: string,
  description?: string,
): Promise<Watchlist> {
  try {
    const res = await apiClient.post<Watchlist>("/watchlists", { name, description: description ?? null });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function updateWatchlist(
  id: string,
  updates: { name?: string; description?: string },
): Promise<Watchlist> {
  try {
    const res = await apiClient.patch<Watchlist>(`/watchlists/${id}`, updates);
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function deleteWatchlist(id: string): Promise<void> {
  try {
    await apiClient.delete(`/watchlists/${id}`);
  } catch (err) {
    toApiError(err);
  }
}

// ── Watchlist items ────────────────────────────────────────────────────────

export async function listWatchlistItems(
  watchlistId?: string,
  market?: Market,
): Promise<WatchlistItem[]> {
  try {
    const params: Record<string, string> = {};
    if (watchlistId) params.watchlist_id = watchlistId;
    if (market) params.market = market;
    const res = await apiClient.get<WatchlistItem[]>("/watchlist", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function addWatchlistItem(
  symbol: string,
  market: Market,
  watchlistId: string,
  notes?: string,
): Promise<WatchlistItem> {
  try {
    const res = await apiClient.post<WatchlistItem>("/watchlist", {
      symbol: symbol.toUpperCase().trim(),
      market,
      watchlist_id: watchlistId,
      notes: notes || null,
    });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function moveWatchlistItem(
  itemId: string,
  targetWatchlistId: string,
): Promise<WatchlistItem> {
  try {
    const res = await apiClient.patch<WatchlistItem>(`/watchlist/${itemId}`, {
      watchlist_id: targetWatchlistId,
    });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function removeWatchlistItem(id: string): Promise<void> {
  try {
    await apiClient.delete(`/watchlist/${id}`);
  } catch (err) {
    toApiError(err);
  }
}

// ── Legacy shim (used by scanner page) ────────────────────────────────────
// Kept for backward compatibility — returns all items across all lists.
export async function listWatchlist(market?: Market): Promise<WatchlistItem[]> {
  return listWatchlistItems(undefined, market);
}
