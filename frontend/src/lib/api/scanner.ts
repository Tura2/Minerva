import { AxiosError } from "axios";
import apiClient from "../apiClient";
import { ApiError, Candidate, Market, ScanHistoryItem, ScanResult } from "../types";

function toApiError(err: unknown): never {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail ?? err.message;
    throw new ApiError(err.response?.status ?? 0, detail);
  }
  throw new ApiError(0, String(err));
}

export interface ScanRequest {
  market: Market;
  limit?: number;
  symbols?: string[];          // if set, scan these instead of watchlist
  min_price?: number | null;
  max_price?: number | null;
  min_volume?: number | null;
}

export async function runScan(req: ScanRequest): Promise<ScanResult> {
  try {
    const res = await apiClient.post<ScanResult>("/scanner/scan", req);
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function getCandidates(market?: Market, limit = 50): Promise<Candidate[]> {
  try {
    const params: Record<string, unknown> = { limit };
    if (market) params.market = market;
    const res = await apiClient.get<Candidate[]>("/scanner/candidates", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function getScanHistory(market?: Market, limit = 20): Promise<ScanHistoryItem[]> {
  try {
    const params: Record<string, unknown> = { limit };
    if (market) params.market = market;
    const res = await apiClient.get<ScanHistoryItem[]>("/scanner/history", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}
