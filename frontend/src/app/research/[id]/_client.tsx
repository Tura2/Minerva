"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useState } from "react";
import { getTicket, updateTicketStatus } from "@/lib/api/research";
import { getHistory } from "@/lib/api/market";
import type { Candle, ExecutionLevels, ResearchTicket, TicketStatus } from "@/lib/types";

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

function PriceStat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
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
      <p
        className="font-mono text-xl font-semibold"
        style={{ color: color ?? "var(--text)" }}
      >
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

export default function TicketClient({ id }: { id: string }) {
  const [ticket, setTicket] = useState<ResearchTicket | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [executionLevels, setExecutionLevels] = useState<ExecutionLevels | null>(null);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
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

        // Load chart data with execution levels
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
            setExecutionLevels({
              entry: t.entry_price,
              stop: t.stop_loss,
              target: t.target,
            });
          }
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

  const ChartLegend = () => (
    <div className="flex items-center gap-5 mt-2 px-1">
      {[
        { color: "#3b82f6", style: "dashed", label: `Entry ${sym}${ticket.entry_price.toFixed(2)}` },
        { color: "#ef4444", style: "solid", label: `Stop ${sym}${ticket.stop_loss.toFixed(2)}` },
        { color: "#22c55e", style: "solid", label: `Target ${sym}${ticket.target.toFixed(2)}` },
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
            {meta.setup_quality && <QualityBadge q={meta.setup_quality} />}
          </div>
          <p className="text-xs mt-1 font-mono" style={{ color: "var(--text-dim)" }}>
            {new Date(ticket.created_at).toLocaleString()} · {ticket.workflow_type} · {meta.research_model ?? ""}
          </p>
        </div>

        {/* Approve/Reject buttons */}
        <div className="flex gap-2">
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
            <PriceStat label="Stop" value={`${sym}${ticket.stop_loss.toFixed(2)}`} color="var(--red)" />
            <PriceStat label="Target" value={`${sym}${ticket.target.toFixed(2)}`} color="var(--green)" />
          </div>
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
              <span className="font-mono font-bold text-2xl" style={{ color: probColor }}>
                {prob}%
              </span>
            </div>
            <div className="h-2 rounded-full overflow-hidden" style={{ background: "var(--border)" }}>
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${prob}%`, background: probColor }}
              />
            </div>
            {meta.breadth_zone && (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                Breadth: {meta.breadth_zone}{meta.breadth_score ? ` (${meta.breadth_score.toFixed(1)})` : ""}
              </p>
            )}
          </div>
        </Section>
      </div>

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

      {/* Context sections */}
      {(meta.entry_rationale || meta.trend_context || meta.volume_context || meta.market_breadth_context) && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {[
            { label: "Entry Rationale", text: meta.entry_rationale },
            { label: "Trend Context", text: meta.trend_context },
            { label: "Volume Context", text: meta.volume_context },
            { label: "Market Breadth", text: meta.market_breadth_context },
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
