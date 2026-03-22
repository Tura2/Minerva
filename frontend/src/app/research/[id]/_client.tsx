"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getTicket, updateTicketStatus } from "@/lib/api/research";
import { getHistory } from "@/lib/api/market";
import type {
  Candle,
  ExecutionLevels,
  ResearchTicket,
  Scenario,
  ScaleOutPlanEntry,
  SynthesizedScore,
  TicketStatus,
} from "@/lib/types";

// Dynamically import CandlestickChart to avoid SSR issues with DOM APIs
const CandlestickChart = dynamic(() => import("@/components/CandlestickChart"), {
  ssr: false,
  loading: () => <div className="skeleton" style={{ height: 520 }} />,
});

const CHECK_LABELS: Record<string, string> = {
  price_above_ma150: "Price above MA150",
  price_above_ma200: "Price above MA200",
  ma150_above_ma200: "MA150 > MA200",
  ma200_trending_up: "MA200 trending up (30-day)",
  price_above_ma50: "Price above MA50",
  above_52w_low_25pct: "≥25% above 52-week low",
  within_52w_high_25pct: "Within 25% of 52-week high",
  min_volume: "Minimum volume threshold",
};

// ── Shared primitive components ──────────────────────────────────────────────

function StatusBadge({ status }: { status: TicketStatus }) {
  const styles: Record<TicketStatus, { bg: string; color: string }> = {
    pending: { bg: "var(--accent-dim)", color: "var(--accent)" },
    approved: { bg: "var(--green-dim)", color: "var(--green)" },
    rejected: { bg: "var(--red-dim)", color: "var(--red)" },
  };
  const s = styles[status];
  return (
    <span
      className="px-2 py-1 text-xs font-mono rounded uppercase tracking-wide"
      style={{ background: s.bg, color: s.color }}
    >
      {status}
    </span>
  );
}

function VerdictBadge({ verdict }: { verdict?: string | null }) {
  if (!verdict) return null;
  const map: Record<string, { bg: string; color: string }> = {
    "Strong Buy": { bg: "#14532d", color: "#4ade80" },
    "Buy":        { bg: "var(--green-dim)", color: "var(--green)" },
    "Watch":      { bg: "var(--accent-dim)", color: "var(--accent)" },
    "Avoid":      { bg: "var(--red-dim)", color: "var(--red)" },
  };
  const s = map[verdict] ?? { bg: "var(--surface-2)", color: "var(--text-dim)" };
  return (
    <span
      className="px-3 py-1 text-sm font-mono font-semibold rounded uppercase tracking-wide"
      style={{ background: s.bg, color: s.color }}
    >
      {verdict}
    </span>
  );
}

function SetupScoreBadge({ score }: { score?: number | null }) {
  if (score == null) return null;
  const color = score >= 42 ? "var(--green)" : score >= 34 ? "var(--accent)" : score >= 25 ? "#f97316" : "var(--red)";
  return (
    <span
      className="px-3 py-1 font-mono text-sm font-bold rounded"
      style={{ background: "var(--surface-2)", border: `1px solid ${color}`, color }}
    >
      {score}/60
    </span>
  );
}

function QualityBadge({ q }: { q?: string }) {
  if (!q) return null;
  const styles: Record<string, { bg: string; color: string; label: string }> = {
    A: { bg: "var(--green-dim)", color: "var(--green)", label: "A — High Quality" },
    B: { bg: "var(--accent-dim)", color: "var(--accent)", label: "B — Moderate" },
    C: { bg: "#431407", color: "#f97316", label: "C — Low Confidence" },
  };
  const s = styles[q];
  if (!s) return null;
  return (
    <span
      className="px-2 py-1 text-xs font-mono rounded"
      style={{ background: s.bg, color: s.color }}
    >
      {s.label}
    </span>
  );
}

function PriceStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div
      className="p-3"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: "4px",
      }}
    >
      <p className="text-xs uppercase tracking-widest mb-1.5" style={{ color: "var(--text-dim)" }}>
        {label}
      </p>
      <p className="font-mono text-xl font-semibold" style={{ color: color ?? "var(--text)" }}>
        {value}
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3
        className="text-xs font-mono uppercase tracking-widest pb-2"
        style={{ color: "var(--text-dim)", borderBottom: "1px solid var(--border-subtle)" }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

// ── Rich analytical sections ─────────────────────────────────────────────────

// Labels for all known dimension keys across all workflows.
const DIMENSION_LABELS: Record<string, string> = {
  // technical-swing
  trend_template:   "Trend Template",
  vcp_pattern:      "VCP Pattern",
  volume_profile:   "Volume Profile",
  rs_strength:      "RS Strength",
  breadth_context:  "Market Breadth",
  weekly_alignment: "Weekly Align",
  // mean-reversion-bounce
  long_term_trend:   "Long-Term Trend",
  dip_depth_quality: "Dip Quality",
  exhaustion_signals:"Exhaustion",
  support_confluence:"Support",
  rs_quality:        "RS Quality",
};

function SynthesizedScoreTable({ score }: { score: SynthesizedScore }) {
  const total = score.total ?? 0;
  const verdictColor = total >= 42 ? "#4ade80" : total >= 34 ? "var(--accent)" : total >= 25 ? "#f97316" : "var(--red)";
  const verdictLabel = total >= 42 ? "Strong Buy" : total >= 34 ? "Buy" : total >= 25 ? "Watch" : "Avoid";

  // Dynamically extract dimension entries — works for both swing and MR workflows
  const dimensions = Object.entries(score)
    .filter(([key, val]) => key !== "total" && typeof val === "object" && val !== null)
    .map(([key, val]) => ({
      key,
      label: DIMENSION_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      dim: val as { score: number; note: string },
    }));

  return (
    <Section title="Synthesized Setup Score">
      <div
        style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          overflow: "hidden",
        }}
      >
        <div className="overflow-x-auto">
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border)" }}>
                <th className="text-left text-xs font-mono uppercase tracking-widest px-3 py-2" style={{ color: "var(--text-dim)", width: "16%" }}>Dimension</th>
                <th className="text-center text-xs font-mono uppercase tracking-widest px-3 py-2" style={{ color: "var(--text-dim)", width: "9%" }}>Score</th>
                <th className="text-left px-3 py-2" style={{ width: "15%" }}>
                  <span className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>Bar</span>
                </th>
                <th className="text-left text-xs font-mono uppercase tracking-widest px-3 py-2" style={{ color: "var(--text-dim)" }}>Note</th>
              </tr>
            </thead>
            <tbody>
              {dimensions.map(({ key, label, dim }) => {
                const pct = Math.min(100, (dim.score / 10) * 100);
                const barColor = dim.score >= 8 ? "var(--green)" : dim.score >= 5 ? "var(--accent)" : "var(--red)";
                return (
                  <tr key={key} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td className="px-3 py-2 text-sm font-mono" style={{ color: "var(--text-muted)" }}>{label}</td>
                    <td className="px-3 py-2 text-center font-mono font-bold text-sm" style={{ color: barColor }}>{dim.score}/10</td>
                    <td className="px-3 py-2">
                      <div className="h-1.5 rounded-full" style={{ background: "var(--border)", width: "100px" }}>
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: barColor }} />
                      </div>
                    </td>
                    <td className="px-3 py-2 text-xs" style={{ color: "var(--text-dim)" }}>{dim.note}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ borderTop: "1px solid var(--border)" }}>
                <td className="px-3 py-2 font-mono text-sm font-bold" style={{ color: "var(--text)" }}>Total</td>
                <td className="px-3 py-2 text-center font-mono font-bold" style={{ color: verdictColor }}>{total}/60</td>
                <td />
                <td className="px-3 py-2 text-xs font-mono font-semibold" style={{ color: verdictColor }}>→ {verdictLabel}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </Section>
  );
}

function ScaleOutPlanSection({ plan, sym }: { plan: ScaleOutPlanEntry[]; sym: string }) {
  if (!plan.length) return null;
  return (
    <Section title="Scale-Out Plan">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {plan.map((t) => {
          const rColor = t.r_multiple != null && t.r_multiple >= 2 ? "var(--green)" : t.r_multiple != null && t.r_multiple >= 1 ? "var(--accent)" : "var(--text-dim)";
          return (
            <div
              key={t.label}
              className="p-3 space-y-2"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "4px",
              }}
            >
              <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{t.label}</p>
              <p className="font-mono text-xl font-bold" style={{ color: "var(--green)" }}>
                {t.price > 0 ? `${sym}${t.price.toFixed(2)}` : "—"}
              </p>
              <div className="flex items-center justify-between text-xs font-mono" style={{ color: "var(--text-dim)" }}>
                <span>{t.share_pct}% of shares</span>
                {t.r_multiple != null && (
                  <span style={{ color: rColor }}>{t.r_multiple.toFixed(1)}R</span>
                )}
              </div>
              {t.shares > 0 && (
                <p className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                  {t.shares} shares
                  {t.partial_value ? ` · ${sym}${t.partial_value.toLocaleString()}` : ""}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function ScenariosSection({ scenarios }: { scenarios: Scenario[] }) {
  const COLORS: Record<string, { bg: string; border: string; color: string }> = {
    "Bull Case":  { bg: "#14532d20", border: "#4ade80", color: "#4ade80" },
    "Base Case":  { bg: "var(--accent-dim)", border: "var(--accent)", color: "var(--accent)" },
    "Bear Case":  { bg: "#7c341120", border: "#f97316", color: "#f97316" },
    "Breakdown":  { bg: "var(--red-dim)", border: "var(--red)", color: "var(--red)" },
  };

  return (
    <Section title="Scenario Planning">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {scenarios.map((s) => {
          const c = COLORS[s.name] ?? { bg: "var(--surface-2)", border: "var(--border)", color: "var(--text-dim)" };
          const probPct = Math.round(s.probability * 100);
          return (
            <div
              key={s.name}
              className="p-4 space-y-3"
              style={{
                background: c.bg,
                border: `1px solid ${c.border}`,
                borderRadius: "4px",
              }}
            >
              <div className="flex items-center justify-between">
                <p className="text-xs font-mono font-semibold uppercase tracking-wide" style={{ color: c.color }}>
                  {s.name}
                </p>
                <span className="font-mono font-bold text-lg" style={{ color: c.color }}>{probPct}%</span>
              </div>
              <div className="h-1 rounded-full" style={{ background: "var(--border)" }}>
                <div className="h-full rounded-full" style={{ width: `${probPct}%`, background: c.color }} />
              </div>
              <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>{s.description}</p>
              {s.target > 0 && (
                <p className="text-xs font-mono" style={{ color: c.color }}>
                  Target: {s.target.toFixed(2)}
                </p>
              )}
              {s.invalidation && (
                <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                  ⊗ {s.invalidation}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function FinalRecommendationSection({
  recommendation,
  checklist,
}: {
  recommendation: NonNullable<ResearchTicket["metadata"]["final_recommendation"]>;
  checklist?: ResearchTicket["metadata"]["execution_checklist"];
}) {
  const convictionColor =
    recommendation.conviction === "high"   ? "var(--green)"  :
    recommendation.conviction === "medium" ? "var(--accent)" : "var(--text-dim)";

  return (
    <div
      className="p-5 space-y-4"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderLeft: "4px solid var(--accent)",
        borderRadius: "4px",
      }}
    >
      <div className="flex items-start gap-4 flex-wrap">
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              Final Recommendation
            </p>
            <VerdictBadge verdict={recommendation.verdict} />
            <span className="text-xs font-mono capitalize" style={{ color: convictionColor }}>
              {recommendation.conviction} conviction
            </span>
          </div>
          {recommendation.action && (
            <p className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {recommendation.action}
            </p>
          )}
          {recommendation.narrative && (
            <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
              {recommendation.narrative}
            </p>
          )}
        </div>
      </div>

      {checklist && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-3" style={{ borderTop: "1px solid var(--border-subtle)" }}>
          {[
            { label: "Prerequisites", items: checklist.prerequisites ?? [], color: "var(--accent)" },
            { label: "Entry Triggers", items: checklist.entry_triggers ?? [], color: "var(--green)" },
            { label: "Invalidation", items: checklist.invalidation_conditions ?? [], color: "var(--red)" },
          ].map(({ label, items, color }) =>
            items.length > 0 ? (
              <div key={label} className="space-y-2">
                <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</p>
                <ul className="space-y-1">
                  {items.map((item, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
                      <span className="mt-0.5 shrink-0 font-mono" style={{ color }}>▸</span>
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null
          )}
        </div>
      )}
    </div>
  );
}

// ── Main page component ───────────────────────────────────────────────────────

export default function TicketClient({ id }: { id: string }) {
  const [ticket, setTicket] = useState<ResearchTicket | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [executionLevels, setExecutionLevels] = useState<ExecutionLevels | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [preScreenOpen, setPreScreenOpen] = useState(false);
  const [fsMode, setFsMode] = useState(false);
  const [screenH, setScreenH] = useState(800);

  useEffect(() => {
    setScreenH(window.innerHeight);
    function onResize() { setScreenH(window.innerHeight); }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") setFsMode(false); }
    window.addEventListener("resize", onResize);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const t = await getTicket(id);
        setTicket(t);

        // Load chart data — failures here are non-fatal; ticket still renders
        try {
          const hist = await getHistory({
            symbol: t.symbol,
            market: t.market,
            period: "1y",
            interval: "1d",
            ticket_id: t.id,
          });
          setCandles(hist.candles);
          if (hist.execution_levels) {
            setExecutionLevels(hist.execution_levels);
          } else {
            setExecutionLevels({ entry: t.entry_price, stop: t.stop_loss, target: t.target });
          }
        } catch {
          setExecutionLevels({ entry: t.entry_price, stop: t.stop_loss, target: t.target });
          setChartError("Chart data unavailable — backend returned an error.");
        } finally {
          setChartLoading(false);
        }
      } catch {
        setError("Ticket not found or failed to load.");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  async function handleStatus(status: TicketStatus) {
    if (!ticket) return;
    setUpdating(true);
    try {
      const updated = await updateTicketStatus(ticket.id, status);
      setTicket(updated);
    } finally {
      setUpdating(false);
    }
  }

  function handleDownloadDebugLogs() {
    if (!ticket) return;
    const payload = {
      ticket_id: ticket.id,
      symbol: ticket.symbol,
      market: ticket.market,
      created_at: ticket.created_at,
      workflow_type: ticket.workflow_type,
      debug_logs: ticket.metadata?.debug_logs ?? [],
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `debug_${ticket.symbol}_${ticket.id.slice(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="skeleton h-8 w-48 rounded" />
        <div className="grid grid-cols-3 gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="skeleton h-24 rounded" />
          ))}
        </div>
        <div className="skeleton h-[520px] rounded" />
      </div>
    );
  }

  if (error || !ticket) {
    return (
      <div className="text-center py-20">
        <p style={{ color: "var(--red)" }}>{error ?? "Ticket not found."}</p>
        <Link
          href="/research"
          className="text-xs font-mono mt-3 inline-block"
          style={{ color: "var(--accent)" }}
        >
          ← Back to tickets
        </Link>
      </div>
    );
  }

  const sym = ticket.currency === "ILS" ? "₪" : "$";
  const prob = Math.round(ticket.bullish_probability * 100);
  const meta = ticket.metadata ?? {};
  const rr = meta.risk_reward_ratio ? meta.risk_reward_ratio.toFixed(1) : "—";
  const probColor = prob >= 65 ? "var(--green)" : prob >= 50 ? "var(--accent)" : "var(--red)";

  // Rich fields
  const synthesizedScore = meta.synthesized_score;
  const scaleOutPlan = meta.scale_out_plan ?? [];
  const scenarios = meta.scenarios ?? [];
  const finalRec = meta.final_recommendation;
  const checklist = meta.execution_checklist;
  const techAnalysis = meta.technical_analysis;
  const rsIndicators = meta.rs_indicators;

  const ChartLegend = () => (
    <div className="flex items-center gap-5 mt-2 px-1">
      {[
        { color: "#3b82f6", style: "dashed", label: `Entry ${sym}${ticket.entry_price.toFixed(2)}` },
        { color: "#ef4444", style: "solid",  label: `Stop ${sym}${ticket.stop_loss.toFixed(2)}` },
        { color: "#22c55e", style: "solid",  label: `Target ${sym}${ticket.target.toFixed(2)}` },
      ].map((l) => (
        <div key={l.label} className="flex items-center gap-2">
          <div className="w-5 h-0" style={{ border: `1.5px ${l.style} ${l.color}` }} />
          <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>{l.label}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
      {/* Breadcrumb + title row */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Link href="/research" className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
              Research
            </Link>
            <span style={{ color: "var(--text-dim)" }}>/</span>
            <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>{ticket.symbol}</span>
          </div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="font-mono text-2xl font-semibold tracking-wide" style={{ color: "var(--text)" }}>
              {ticket.symbol}
            </h1>
            <span
              className="px-2 py-0.5 text-xs font-mono rounded"
              style={{
                background: ticket.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                color: ticket.market === "US" ? "#93c5fd" : "var(--accent)",
              }}
            >
              {ticket.market}
            </span>
            <StatusBadge status={ticket.status} />
            {/* Verdict takes precedence over quality badge when available */}
            {ticket.verdict || finalRec?.verdict
              ? <VerdictBadge verdict={ticket.verdict ?? finalRec?.verdict} />
              : <QualityBadge q={meta.setup_quality} />
            }
            {(ticket.setup_score != null || synthesizedScore?.total != null) && (
              <SetupScoreBadge score={ticket.setup_score ?? synthesizedScore?.total} />
            )}
            {rsIndicators?.rs_rank_pct != null && (
              <span
                className="px-2 py-1 text-xs font-mono rounded"
                style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text-dim)" }}
              >
                RS {rsIndicators.rs_rank_pct.toFixed(0)}/100
              </span>
            )}
            {techAnalysis?.pattern_stage && (
              <span
                className="px-2 py-0.5 text-xs font-mono rounded"
                style={{ background: "var(--surface-2)", color: "var(--text-dim)" }}
              >
                {techAnalysis.pattern_stage}
              </span>
            )}
          </div>
          <p className="text-xs mt-1 font-mono" style={{ color: "var(--text-dim)" }}>
            {new Date(ticket.created_at).toLocaleString()} · {ticket.workflow_type} · {meta.research_model ?? ""}
          </p>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2 flex-wrap">
          {meta.debug_logs && meta.debug_logs.length > 0 && (
            <button
              onClick={handleDownloadDebugLogs}
              className="px-3 py-2 text-xs font-mono uppercase tracking-wide transition-colors"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "3px",
                color: "var(--text-dim)",
                cursor: "pointer",
              }}
              title="Download node trace and full LLM prompt as JSON"
            >
              ↓ Debug Logs
            </button>
          )}
          {ticket.status !== "rejected" && (
            <button
              onClick={() => handleStatus("rejected")}
              disabled={updating}
              className="px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wide transition-colors"
              style={{
                background: "var(--red-dim)",
                border: "1px solid var(--red)",
                borderRadius: "3px",
                color: updating ? "var(--text-dim)" : "var(--red)",
                cursor: updating ? "not-allowed" : "pointer",
              }}
            >
              Reject
            </button>
          )}
          {ticket.status !== "approved" && (
            <button
              onClick={() => handleStatus("approved")}
              disabled={updating}
              className="px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wide transition-colors"
              style={{
                background: "var(--green-dim)",
                border: "1px solid var(--green)",
                borderRadius: "3px",
                color: updating ? "var(--text-dim)" : "var(--green)",
                cursor: updating ? "not-allowed" : "pointer",
              }}
            >
              {updating ? "Saving…" : "Approve"}
            </button>
          )}
          {ticket.status !== "pending" && (
            <button
              onClick={() => handleStatus("pending")}
              disabled={updating}
              className="px-3 py-2 text-xs font-mono uppercase tracking-wide transition-colors"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "3px",
                color: "var(--text-dim)",
                cursor: updating ? "not-allowed" : "pointer",
              }}
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Full-width chart */}
      {!fsMode && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              Price Chart · 1Y Daily
              {candles.length > 0 && (
                <span className="ml-3 normal-case">({candles.length} candles)</span>
              )}
              {chartError && (
                <span className="ml-3 normal-case" style={{ color: "var(--red)" }}>
                  ⚠ {chartError}
                </span>
              )}
            </span>
            <button
              onClick={() => setFsMode(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono transition-colors"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "3px",
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M1 4V1h3M8 1h3v3M11 8v3H8M4 11H1V8" />
              </svg>
              Fullscreen
            </button>
          </div>
          <CandlestickChart
            candles={candles}
            executionLevels={executionLevels}
            height={520}
            isLoading={chartLoading}
          />
          <ChartLegend />
        </div>
      )}

      {/* Fullscreen chart overlay */}
      {fsMode && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            background: "var(--bg)",
            display: "flex",
            flexDirection: "column",
            padding: "20px 24px",
          }}
        >
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-3">
              <span className="font-mono font-semibold text-lg" style={{ color: "var(--text)" }}>
                {ticket.symbol}
              </span>
              <span className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                Price Chart · 1Y Daily
              </span>
            </div>
            <button
              onClick={() => setFsMode(false)}
              className="flex items-center gap-2 px-4 py-2 text-xs font-mono transition-colors"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "3px",
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M2 5V2h3M7 2h3v3M10 7v3H7M5 10H2V7" />
              </svg>
              Exit Fullscreen · ESC
            </button>
          </div>
          <div style={{ flex: 1, overflow: "hidden" }}>
            <CandlestickChart
              candles={candles}
              executionLevels={executionLevels}
              height={Math.max(500, screenH - 120)}
              isLoading={chartLoading}
            />
          </div>
          <ChartLegend />
        </div>
      )}

      {/* Stats row — Trade Levels | Position Sizing | Conviction */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Section title="Trade Levels">
          <div className="grid grid-cols-3 gap-2">
            <PriceStat label="Entry" value={`${sym}${ticket.entry_price.toFixed(2)}`} color="#3b82f6" />
            <PriceStat label="Stop"  value={`${sym}${ticket.stop_loss.toFixed(2)}`}  color="var(--red)" />
            <PriceStat label="Target" value={`${sym}${ticket.target.toFixed(2)}`}   color="var(--green)" />
          </div>
          {techAnalysis?.entry_type && (
            <p className="text-xs font-mono mt-1" style={{ color: "var(--text-dim)" }}>
              Entry type: <span style={{ color: "var(--accent)" }}>{techAnalysis.entry_type}</span>
            </p>
          )}
        </Section>

        <Section title="Position Sizing">
          <div className="grid grid-cols-2 gap-2">
            <PriceStat label="Shares" value={String(ticket.position_size)} />
            <PriceStat label={`Max Risk (${ticket.currency})`} value={`${sym}${ticket.max_risk.toFixed(2)}`} color="var(--accent)" />
            <PriceStat label="R/R Ratio" value={`${rr}:1`} />
            <PriceStat label="Portfolio %" value={meta.max_risk_pct ? `${meta.max_risk_pct}%` : "—"} />
          </div>
        </Section>

        <Section title="Conviction">
          <div
            className="p-4 space-y-3"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-sm" style={{ color: "var(--text-muted)" }}>Bullish probability</span>
              <span className="font-mono font-bold text-2xl" style={{ color: probColor }}>{prob}%</span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
              <div className="h-full rounded-full transition-all" style={{ width: `${prob}%`, background: probColor }} />
            </div>
            {meta.breadth_zone && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                Breadth: {meta.breadth_zone}{meta.breadth_score ? ` (${meta.breadth_score.toFixed(1)})` : ""}
              </p>
            )}
            {rsIndicators?.rs_composite != null && (
              <p className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
                RS vs {rsIndicators.benchmark_used}: <span style={{ color: rsIndicators.rs_composite >= 0 ? "var(--green)" : "var(--red)" }}>
                  {rsIndicators.rs_composite >= 0 ? "+" : ""}{rsIndicators.rs_composite.toFixed(1)}%
                </span>
              </p>
            )}
          </div>
        </Section>
      </div>

      {/* Synthesized Score Table (Phase 7) */}
      {synthesizedScore && <SynthesizedScoreTable score={synthesizedScore} />}

      {/* Scale-Out Plan (Phase 7) */}
      {scaleOutPlan.length > 0 && <ScaleOutPlanSection plan={scaleOutPlan} sym={sym} />}

      {/* Scenarios (Phase 7) */}
      {scenarios.length > 0 && <ScenariosSection scenarios={scenarios} />}

      {/* Final Recommendation + Execution Checklist (Phase 7) */}
      {finalRec && <FinalRecommendationSection recommendation={finalRec} checklist={checklist} />}

      {/* Key Triggers + Caveats */}
      {(ticket.key_triggers?.length > 0 || meta.caveats?.length > 0) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {ticket.key_triggers?.length > 0 && (
            <Section title="Key Triggers">
              <ul className="space-y-2">
                {ticket.key_triggers.map((t, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 p-3"
                    style={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderLeft: "3px solid var(--accent)",
                      borderRadius: "4px",
                    }}
                  >
                    <span className="font-mono text-base mt-0.5 shrink-0" style={{ color: "var(--accent)" }}>→</span>
                    <span className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>{t}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {meta.caveats?.length > 0 && (
            <Section title="Caveats">
              <ul className="space-y-2">
                {meta.caveats.map((c: string, i: number) => (
                  <li
                    key={i}
                    className="flex items-start gap-3 p-3"
                    style={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderLeft: "3px solid var(--red)",
                      borderRadius: "4px",
                    }}
                  >
                    <span className="font-mono text-base mt-0.5 shrink-0" style={{ color: "var(--red)" }}>⚠</span>
                    <span className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>{c}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      )}

      {/* Chain of Thought */}
      {meta.chain_of_thought && (
        <div
          className="p-4 space-y-2"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid var(--accent)",
            borderRadius: "4px",
          }}
        >
          <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            LLM Reasoning
          </p>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {meta.chain_of_thought}
          </p>
        </div>
      )}

      {/* Context sections */}
      {(meta.entry_rationale || meta.trend_context || meta.volume_context || meta.market_breadth_context) && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {[
            { label: "Entry Rationale", text: meta.entry_rationale },
            { label: "Trend Context",   text: meta.trend_context },
            { label: "Volume Context",  text: meta.volume_context },
            { label: "Market Breadth",  text: meta.market_breadth_context },
          ]
            .filter((s) => s.text)
            .map((s) => (
              <div
                key={s.label}
                className="p-4 space-y-2"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "4px",
                }}
              >
                <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
                  {s.label}
                </p>
                <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  {s.text}
                </p>
              </div>
            ))}
        </div>
      )}

      {/* Pre-screen accordion */}
      {meta.pre_screen && (
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            overflow: "hidden",
          }}
        >
          <button
            onClick={() => setPreScreenOpen((o) => !o)}
            className="w-full flex items-center justify-between px-4 py-3 text-left transition-colors hover:bg-[var(--surface-2)]"
            style={{ cursor: "pointer", background: "none", border: "none" }}
          >
            <span className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
              Pre-Screen Checks (Stage 2 Trend Template)
            </span>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono" style={{ color: meta.pre_screen.passed ? "var(--green)" : "var(--red)" }}>
                {meta.pre_screen.passed ? "PASSED" : "FAILED"}
              </span>
              <span style={{ color: "var(--text-dim)" }}>{preScreenOpen ? "▲" : "▼"}</span>
            </div>
          </button>

          {preScreenOpen && (
            <div className="px-4 pb-4 pt-2" style={{ borderTop: "1px solid var(--border-subtle)" }}>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(meta.pre_screen.checks ?? {}).map(([key, passed]) => (
                  <div key={key} className="flex items-center gap-2 text-sm">
                    <span className="font-mono w-4 text-center" style={{ color: passed ? "var(--green)" : "var(--red)" }}>
                      {passed ? "✓" : "✗"}
                    </span>
                    <span style={{ color: passed ? "var(--text-muted)" : "#fca5a5" }}>
                      {CHECK_LABELS[key] ?? key}
                    </span>
                  </div>
                ))}
              </div>
              {meta.pre_screen.vcp && (
                <p className="text-xs mt-3" style={{ color: "var(--text-dim)" }}>
                  VCP: {meta.pre_screen.vcp.contraction_count} contraction(s)
                  {meta.pre_screen.vcp.is_vcp ? " — Pattern confirmed ✓" : ""}
                </p>
              )}
              {meta.pre_screen.reasons?.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {meta.pre_screen.reasons.map((r: string, i: number) => (
                    <li key={i} className="text-sm" style={{ color: "#fca5a5" }}>{r}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
