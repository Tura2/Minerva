import { AxiosError } from "axios";
import apiClient from "../apiClient";
import { ApiError, Market, WatchlistItem } from "../types";

function toApiError(err: unknown): never {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail ?? err.message;
    throw new ApiError(err.response?.status ?? 0, detail);
  }
  throw new ApiError(0, String(err));
}

export async function listWatchlist(market?: Market): Promise<WatchlistItem[]> {
  try {
    const params = market ? { market } : {};
    const res = await apiClient.get<WatchlistItem[]>("/watchlist", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function addWatchlistItem(
  symbol: string,
  market: Market,
  notes?: string,
): Promise<WatchlistItem> {
  try {
    const res = await apiClient.post<WatchlistItem>("/watchlist", {
      symbol: symbol.toUpperCase().trim(),
      market,
      notes: notes || null,
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
