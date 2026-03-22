export type Market = "US" | "TASE";
export type TicketStatus = "pending" | "approved" | "rejected";
export type SetupQuality = "A" | "B" | "C";
export type Currency = "USD" | "ILS";

export interface Watchlist {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
  item_count: number;
  us_count: number;
  tase_count: number;
}

export interface WatchlistItem {
  id: string;
  symbol: string;
  market: Market;
  watchlist_id: string;
  added_at: string;
  notes: string | null;
}

export type WorkflowType = "technical-swing" | "mean-reversion-bounce";

export interface Candidate {
  id: string;
  symbol: string;
  market: Market;
  price: number;
  volume: number;
  score: number;
  screened_at: string;
  is_stale?: boolean;
  applicable_workflows?: WorkflowType[];
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
  total_in_watchlist: number;
  ran_at: string;
  status: string;
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

export interface DebugLogEntry {
  node: string;
  ts: string;
  [key: string]: unknown;
}

// ── Rich ticket schema (Phase 7) ───────────────────────────────────────────

export interface TechnicalAnalysis {
  entry_price: number;
  entry_type: "current" | "breakout" | "buy_stop";
  stop_loss: number;
  atr_stop_check: "valid" | "violated";
  pivot_level: number | null;
  key_support: number[];
  key_resistance: number[];
  // swing workflow stages
  pattern_stage: "pre-vcp" | "developing" | "entry-ready" | "extended"
    // mean-reversion workflow stages
    | "approaching-support" | "at-support" | "capitulating" | "reversing"
    | string;
}

export interface ScaleOutTarget {
  label: string;
  price: number;
  share_pct: number;
}

export interface ScaleOutPlanEntry extends ScaleOutTarget {
  shares: number;
  r_multiple: number | null;
  partial_value: number | null;
}

export interface Scenario {
  name: string;
  probability: number;
  description: string;
  target: number;
  invalidation: string;
}

export interface SynthesizedScoreDimension {
  score: number;
  note: string;
}

export interface SynthesizedScore {
  // technical-swing dimensions
  trend_template?: SynthesizedScoreDimension;
  vcp_pattern?: SynthesizedScoreDimension;
  volume_profile?: SynthesizedScoreDimension;
  rs_strength?: SynthesizedScoreDimension;
  breadth_context?: SynthesizedScoreDimension;
  weekly_alignment?: SynthesizedScoreDimension;
  // mean-reversion-bounce dimensions
  long_term_trend?: SynthesizedScoreDimension;
  dip_depth_quality?: SynthesizedScoreDimension;
  exhaustion_signals?: SynthesizedScoreDimension;
  support_confluence?: SynthesizedScoreDimension;
  rs_quality?: SynthesizedScoreDimension;
  total: number;
  [key: string]: SynthesizedScoreDimension | number | undefined;
}

export interface ExecutionChecklist {
  prerequisites: string[];
  entry_triggers: string[];
  invalidation_conditions: string[];
}

export interface FinalRecommendation {
  verdict: "Strong Buy" | "Buy" | "Watch" | "Avoid";
  action: string;
  conviction: "high" | "medium" | "low";
  narrative: string;
}

export interface RsIndicators {
  rs_63?: number | null;
  rs_126?: number | null;
  rs_189?: number | null;
  rs_composite?: number | null;
  rs_rank_pct?: number | null;
  benchmark_used?: string;
}

// ── ──────────────────────────────────────────────────────────────────────────

export interface ResearchTicketMetadata {
  // Legacy fields
  entry_rationale: string;
  stop_rationale: string;
  target_rationale: string;
  risk_reward_ratio: number;
  setup_quality: SetupQuality;
  chain_of_thought?: string;
  trend_context: string;
  volume_context: string;
  market_breadth_context: string;
  caveats: string[];
  pre_screen: PreScreenResult | null;
  breadth_zone: string;
  breadth_score: number;
  weekly_trend?: string;
  research_model: string;
  portfolio_size: number;
  max_risk_pct: number;
  debug_logs?: DebugLogEntry[];
  // Rich fields (Phase 7)
  technical_analysis?: TechnicalAnalysis;
  scale_out_targets?: ScaleOutTarget[];
  scale_out_plan?: ScaleOutPlanEntry[];
  scenarios?: Scenario[];
  synthesized_score?: SynthesizedScore;
  execution_checklist?: ExecutionChecklist;
  final_recommendation?: FinalRecommendation;
  rs_indicators?: RsIndicators;
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
  // Phase 7 flat columns
  rs_rank_pct?: number | null;
  setup_score?: number | null;
  verdict?: "Strong Buy" | "Buy" | "Watch" | "Avoid" | null;
  entry_type?: "current" | "breakout" | null;
  metadata: ResearchTicketMetadata;
}

export interface ExecuteResearchRequest {
  symbol: string;
  market: Market;
  workflow_type?: WorkflowType | string;
  portfolio_size: number;
  max_risk_pct: number;
  force?: boolean;
  force_refresh?: boolean;
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
