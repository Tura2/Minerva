import { AxiosError } from "axios";
import apiClient from "../apiClient";
import { ApiError, Market, MarketHistory } from "../types";

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

export async function getHistory(params: HistoryParams): Promise<MarketHistory> {
  try {
    const res = await apiClient.get<MarketHistory>("/market/history", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}
