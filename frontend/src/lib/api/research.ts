import { AxiosError } from "axios";
import apiClient from "../apiClient";
import {
  ApiError,
  ExecuteResearchRequest,
  Market,
  ResearchTicket,
  TicketStatus,
} from "../types";

function toApiError(err: unknown): never {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail ?? err.message;
    throw new ApiError(err.response?.status ?? 0, detail);
  }
  throw new ApiError(0, String(err));
}

export async function executeResearch(req: ExecuteResearchRequest): Promise<ResearchTicket> {
  try {
    const res = await apiClient.post<ResearchTicket>("/research/execute", {
      workflow_type: "technical-swing",
      force: false,
      ...req,
    });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function listTickets(opts?: {
  market?: Market;
  status?: TicketStatus;
  limit?: number;
}): Promise<ResearchTicket[]> {
  try {
    const params: Record<string, unknown> = { limit: opts?.limit ?? 50 };
    if (opts?.market) params.market = opts.market;
    if (opts?.status) params.status = opts.status;
    const res = await apiClient.get<ResearchTicket[]>("/research/tickets", { params });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function getTicket(id: string): Promise<ResearchTicket> {
  try {
    const res = await apiClient.get<ResearchTicket>(`/research/tickets/${id}`);
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}

export async function updateTicketStatus(
  id: string,
  status: TicketStatus,
): Promise<ResearchTicket> {
  try {
    const res = await apiClient.patch<ResearchTicket>(`/research/tickets/${id}/status`, null, {
      params: { status },
    });
    return res.data;
  } catch (err) {
    toApiError(err);
  }
}
