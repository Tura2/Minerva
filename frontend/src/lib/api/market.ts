import { AxiosError } from "axios";
import apiClient from "../apiClient";
import { ApiError, Market, MarketHistory } from "../types";

export interface Quote {
  symbol: string;
  market: Market;
  price: number;
  change: number;
  change_pct: number;
  volume: number | null;
  error?: string;
}

function toApiError(err: unknown): never {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail ?? err.message;
    throw new ApiError(err.response?.status ?? 0, detail);
  }
  throw new ApiError(0, String(err));
}

export interface HistoryParams {
  symbol: string;
  market: Market;
  period?: string;
  interval?: string;
  ticket_id?: string;
}

export async function getQuotes(symbols: string[], market: Market): Promise<Quote[]> {
  try {
    const res = await apiClient.post<Quote[]>("/market/quotes", { symbols, market });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function getHistory(params: HistoryParams): Promise<MarketHistory> {
  try {
    const res = await apiClient.get<MarketHistory>("/market/history", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}
