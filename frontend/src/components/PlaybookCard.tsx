// frontend/src/components/PlaybookCard.tsx
"use client";

import type {
  ResearchTicket,
  SupportBouncePlaybook,
  SynthesizedScore,
} from "@/lib/types";

// ── Primitive sub-components (same visual language as _client.tsx) ────────────

function StatBox({
  label,
  value,
  color,
  large,
}: {
  label: string;
  value: string;
  color?: string;
  large?: boolean;
}) {
  return (
    <div
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderRadius: 4,
        padding: "12px 16px",
      }}
    >
      <p
        className="text-xs uppercase tracking-widest mb-1"
        style={{ color: "var(--text-dim)" }}
      >
        {label}
      </p>
      <p
        className={`font-mono font-bold ${large ? "text-2xl" : "text-lg"}`}
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

// ── Setup Status Banner ────────────────────────────────────────────────────────

function SetupStatusBanner({ status }: { status: "READY" | "NOT_READY" | "BROKEN" }) {
  const config = {
    READY: {
      bg: "var(--green-dim)",
      border: "var(--green)",
      color: "var(--green)",
      label: "✓ READY TO TRADE",
    },
    NOT_READY: {
      bg: "#451a03",
      border: "#f97316",
      color: "#f97316",
      label: "⏳ SETUP NOT READY",
    },
    BROKEN: {
      bg: "var(--red-dim)",
      border: "var(--red)",
      color: "var(--red)",
      label: "✗ SUPPORT BROKEN",
    },
  }[status];

  return (
    <div
      className="px-4 py-3 rounded text-sm font-mono font-bold uppercase tracking-widest text-center"
      style={{
        background: config.bg,
        border: `1px solid ${config.border}`,
        color: config.color,
      }}
    >
      {config.label}
    </div>
  );
}

// ── Not Ready Card ─────────────────────────────────────────────────────────────

function NotReadyCard({
  reason,
  checkBack,
}: {
  reason: string | null;
  checkBack: string | null;
}) {
  return (
    <div
      className="p-4 space-y-2 rounded"
      style={{
        background: "#451a03",
        border: "1px solid #f97316",
      }}
    >
      <p className="text-xs font-mono uppercase tracking-widest" style={{ color: "#f97316" }}>
        Why Not Ready
      </p>
      <p className="text-sm" style={{ color: "#fed7aa" }}>
        {reason ?? "Setup conditions not yet met."}
      </p>
      {checkBack && (
        <>
          <p
            className="text-xs font-mono uppercase tracking-widest mt-3"
            style={{ color: "#f97316" }}
          >
            Come Back When
          </p>
          <p className="text-sm font-medium" style={{ color: "#fff7ed" }}>
            {checkBack}
          </p>
        </>
      )}
    </div>
  );
}

// ── Broken Card ────────────────────────────────────────────────────────────────

function BrokenCard({ stopLoss, currency }: { stopLoss: number; currency: string }) {
  return (
    <div
      className="p-4 rounded"
      style={{ background: "var(--red-dim)", border: "1px solid var(--red)" }}
    >
      <p className="text-sm font-mono" style={{ color: "var(--red)" }}>
        Support has been violated. Price closed below the stop zone ({stopLoss.toFixed(2)}{" "}
        {currency}). This setup is no longer valid — do not enter.
      </p>
    </div>
  );
}

// ── Entry Trigger Box (hero element for READY setups) ────────────────────────

function EntryTriggerBox({ trigger }: { trigger: string }) {
  return (
    <div
      className="p-4 rounded"
      style={{
        background: "var(--surface-2)",
        border: "2px solid var(--accent)",
      }}
    >
      <p
        className="text-xs font-mono uppercase tracking-widest mb-2"
        style={{ color: "var(--accent)" }}
      >
        Entry Trigger
      </p>
      <p className="text-base font-mono font-semibold" style={{ color: "var(--text)" }}>
        {trigger}
      </p>
    </div>
  );
}

// ── Abort Conditions ──────────────────────────────────────────────────────────

function AbortConditions({ conditions }: { conditions: string[] }) {
  if (!conditions.length) return null;
  return (
    <Section title="Abort If">
      <ul className="space-y-2">
        {conditions.map((c, i) => (
          <li
            key={i}
            className="flex gap-2 items-start text-sm"
            style={{ color: "var(--text-secondary)" }}
          >
            <span style={{ color: "var(--red)", flexShrink: 0, marginTop: 1 }}>✕</span>
            {c}
          </li>
        ))}
      </ul>
    </Section>
  );
}

// ── Expiry Range ───────────────────────────────────────────────────────────────

function ExpiryRange({
  range,
  currency,
}: {
  range: { low: number; high: number };
  currency: string;
}) {
  return (
    <div
      className="px-4 py-3 rounded flex items-center gap-3"
      style={{
        background: "var(--surface-2)",
        border: "1px solid var(--border)",
      }}
    >
      <span className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
        Valid While Price Stays In
      </span>
      <span className="font-mono font-bold" style={{ color: "var(--accent)" }}>
        {range.low.toFixed(2)} – {range.high.toFixed(2)} {currency}
      </span>
    </div>
  );
}

// ── Hidden Risks ────────────────────────────────────────────────────────────

function HiddenRisks({ risks }: { risks: string[] }) {
  if (!risks.length) return null;
  return (
    <Section title="What You Might Miss">
      <ul className="space-y-2">
        {risks.map((r, i) => (
          <li
            key={i}
            className="flex gap-2 items-start text-sm"
            style={{ color: "#fed7aa" }}
          >
            <span style={{ color: "#f97316", flexShrink: 0, marginTop: 1 }}>⚠</span>
            {r}
          </li>
        ))}
      </ul>
    </Section>
  );
}

// ── Synthesized Score ─────────────────────────────────────────────────────────

const SB_DIMENSION_LABELS: Record<string, string> = {
  support_zone_quality: "Support Zone",
  trend_integrity:      "Trend Integrity",
  momentum_setup:       "Momentum Setup",
  rr_quality:           "R:R Quality",
  market_context:       "Market Context",
  timing_readiness:     "Timing",
};

function SBScoreTable({ score }: { score: SynthesizedScore }) {
  const total = score.total ?? 0;
  const verdictColor =
    total >= 42 ? "var(--green)" : total >= 34 ? "var(--accent)" : total >= 25 ? "#f97316" : "var(--red)";
  const dimensions = Object.entries(score)
    .filter(([key, val]) => key !== "total" && typeof val === "object" && val !== null)
    .map(([key, val]) => ({
      key,
      label:
        SB_DIMENSION_LABELS[key] ??
        key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      dim: val as { score: number; note: string },
    }));

  return (
    <Section title="Setup Score">
      <div
        style={{
          background: "var(--surface-2)",
          border: "1px solid var(--border)",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {dimensions.map(({ key, label, dim }) => {
              const pct = Math.min(100, (dim.score / 10) * 100);
              const barColor =
                dim.score >= 8 ? "var(--green)" : dim.score >= 5 ? "var(--accent)" : "var(--red)";
              return (
                <tr key={key} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <td className="px-3 py-2 text-xs font-mono" style={{ color: "var(--text-dim)", width: "20%" }}>
                    {label}
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-sm font-bold" style={{ color: barColor, width: "8%" }}>
                    {dim.score}
                  </td>
                  <td className="px-3 py-2" style={{ width: "20%" }}>
                    <div style={{ background: "var(--border)", borderRadius: 2, height: 4 }}>
                      <div style={{ width: `${pct}%`, background: barColor, height: 4, borderRadius: 2 }} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                    {dim.note}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div
          className="px-3 py-2 text-right font-mono text-sm font-bold"
          style={{ borderTop: "1px solid var(--border)", color: verdictColor }}
        >
          Total: {total}/60
        </div>
      </div>
    </Section>
  );
}

// ── Main Export ───────────────────────────────────────────────────────────────

export function PlaybookCard({
  ticket,
  playbook,
}: {
  ticket: ResearchTicket;
  playbook: SupportBouncePlaybook;
}) {
  const currency = ticket.currency ?? "ILS";
  const status = playbook.setup_status ?? "NOT_READY";
  const isReady = status === "READY";
  const isBroken = status === "BROKEN";

  return (
    <div className="space-y-6">
      {/* Status Banner */}
      <SetupStatusBanner status={status} />

      {/* State-specific content */}
      {isBroken && (
        <BrokenCard stopLoss={ticket.stop_loss ?? 0} currency={currency} />
      )}

      {!isReady && !isBroken && (
        <NotReadyCard
          reason={playbook.not_ready_reason ?? null}
          checkBack={playbook.check_back_condition ?? null}
        />
      )}

      {isReady && (
        <>
          {/* Hero: Entry Trigger */}
          <EntryTriggerBox trigger={playbook.entry_trigger} />

          {/* Key numbers */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatBox
              label="Stop Loss"
              value={`${(ticket.stop_loss ?? 0).toFixed(2)} ${currency}`}
              color="var(--red)"
            />
            <StatBox
              label="Target 1 (60%)"
              value={`${(ticket.target ?? 0).toFixed(2)} ${currency}`}
              color="var(--green)"
            />
            <StatBox
              label="Target 2 (40%)"
              value={
                playbook.target_2 != null
                  ? `${playbook.target_2.toFixed(2)} ${currency}`
                  : "—"
              }
              color="var(--green)"
            />
            <StatBox
              label="R:R Ratio"
              value={playbook.rr_ratio != null ? `${playbook.rr_ratio.toFixed(1)}:1` : "—"}
              color={
                (playbook.rr_ratio ?? 0) >= 3
                  ? "var(--green)"
                  : (playbook.rr_ratio ?? 0) >= 2
                  ? "var(--accent)"
                  : "#f97316"
              }
              large
            />
          </div>

          {/* Expiry Range */}
          {playbook.expiry_range && (
            <ExpiryRange range={playbook.expiry_range} currency={currency} />
          )}

          {/* Abort conditions */}
          <AbortConditions conditions={playbook.abort_conditions ?? []} />
        </>
      )}

      {/* Hidden risks (always shown) */}
      <HiddenRisks risks={playbook.hidden_risks ?? []} />

      {/* Score (always shown when available) */}
      {playbook.synthesized_score && (
        <SBScoreTable score={playbook.synthesized_score} />
      )}

      {/* Final recommendation */}
      {playbook.final_recommendation && (
        <Section title="Recommendation">
          <div
            className="p-4 rounded space-y-1"
            style={{ background: "var(--surface-2)", border: "1px solid var(--border)" }}
          >
            <p className="text-sm font-mono font-semibold" style={{ color: "var(--text)" }}>
              {playbook.final_recommendation.action}
            </p>
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
              {playbook.final_recommendation.narrative}
            </p>
          </div>
        </Section>
      )}

      {/* Support zone info */}
      {playbook.sr_data && (
        <Section title="S/R Levels Detected">
          <div className="grid grid-cols-2 gap-3">
            {playbook.sr_data.nearest_support && (
              <StatBox
                label={`Support (${playbook.sr_data.nearest_support.strength})`}
                value={`${playbook.sr_data.nearest_support.price.toFixed(2)} ${currency}`}
                color="var(--accent)"
              />
            )}
            {playbook.sr_data.nearest_resistance && (
              <StatBox
                label="Resistance"
                value={`${playbook.sr_data.nearest_resistance.price.toFixed(2)} ${currency}`}
                color="var(--text-dim)"
              />
            )}
          </div>
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            {playbook.sr_data.support_zones_count} support zones ·{" "}
            Detected via pivot analysis + MA confluence
          </p>
        </Section>
      )}
    </div>
  );
}
