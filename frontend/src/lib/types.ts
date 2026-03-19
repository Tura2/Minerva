export type Market = "US" | "TASE";
export type TicketStatus = "pending" | "approved" | "rejected";
export type SetupQuality = "A" | "B" | "C";
export type Currency = "USD" | "ILS";

export interface WatchlistItem {
  id: string;
  symbol: string;
  market: Market;
  added_at: string;
  notes: string | null;
}

export interface Candidate {
  id: string;
  symbol: string;
  market: Market;
  price: number;
  volume: number;
  score: number;
  screened_at: string;
}

export interface ScanResult {
  scan_id: string;
  market: Market;
  candidates: Candidate[];
  total_in_watchlist: number;
  total_passed: number;
  ran_at: string;
}

export interface ScanHistoryItem {
  id: string;
  market: Market;
  candidate_count: number;
  ran_at: string;
}

export interface Candle {
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ExecutionLevels {
  entry: number | null;
  stop: number | null;
  target: number | null;
}

export interface MarketHistory {
  symbol: string;
  market: string;
  candles: Candle[];
  execution_levels: ExecutionLevels | null;
  last_updated: string;
  is_stale: boolean;
}

export interface VcpInfo {
  contraction_count: number;
  is_vcp: boolean;
}

export interface PreScreenChecks {
  price_above_ma150: boolean;
  price_above_ma200: boolean;
  ma150_above_ma200: boolean;
  ma200_trending_up: boolean;
  price_above_ma50: boolean;
  above_52w_low_25pct: boolean;
  within_52w_high_25pct: boolean;
  min_volume: boolean;
  [key: string]: boolean;
}

export interface PreScreenResult {
  passed: boolean;
  checks: PreScreenChecks;
  reasons: string[];
  vcp: VcpInfo;
  summary: string;
}

export interface ResearchTicketMetadata {
  entry_rationale: string;
  stop_rationale: string;
  target_rationale: string;
  risk_reward_ratio: number;
  setup_quality: SetupQuality;
  trend_context: string;
  volume_context: string;
  market_breadth_context: string;
  caveats: string[];
  pre_screen: PreScreenResult | null;
  breadth_zone: string;
  breadth_score: number;
  research_model: string;
  portfolio_size: number;
  max_risk_pct: number;
}

export interface ResearchTicket {
  id: string;
  symbol: string;
  market: Market;
  workflow_type: string;
  entry_price: number;
  stop_loss: number;
  target: number;
  position_size: number;
  max_risk: number;
  currency: Currency;
  bullish_probability: number;
  key_triggers: string[];
  status: TicketStatus;
  created_at: string;
  metadata: ResearchTicketMetadata;
}

export interface ExecuteResearchRequest {
  symbol: string;
  market: Market;
  workflow_type?: string;
  portfolio_size: number;
  max_risk_pct: number;
  force?: boolean;
}

export interface PreScreenError {
  error: "pre_screen_failed";
  pre_screen_summary: string;
  checks: Record<string, boolean>;
  reasons: string[];
  vcp: VcpInfo;
  force_hint: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.name = "ApiError";
  }

  isPreScreenFailed(): this is ApiError & { detail: PreScreenError } {
    return (
      this.status === 422 &&
      typeof this.detail === "object" &&
      this.detail !== null &&
      (this.detail as Record<string, unknown>).error === "pre_screen_failed"
    );
  }
}
