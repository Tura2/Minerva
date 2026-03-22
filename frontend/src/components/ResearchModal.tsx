"use client";

import { useState } from "react";
import { useResearch } from "@/lib/ResearchContext";
import type { Market, WorkflowType } from "@/lib/types";

const WORKFLOW_META: Record<WorkflowType, { label: string; description: string; color: string }> = {
  "technical-swing": {
    label: "Technical Swing",
    description: "Minervini Stage 2 breakout — buy new highs from VCP base",
    color: "var(--blue)",
  },
  "mean-reversion-bounce": {
    label: "Mean Reversion",
    description: "Oversold bounce — buy the dip in a confirmed uptrend",
    color: "var(--accent)",
  },
};

interface Props {
  symbol: string;
  market: Market;
  applicable_workflows?: WorkflowType[];
  onClose: () => void;
}

export default function ResearchModal({ symbol, market, applicable_workflows, onClose }: Props) {
  const { startResearch } = useResearch();

  const currency = market === "TASE" ? "ILS (₪)" : "USD ($)";
  const currencyPrefix = market === "TASE" ? "₪" : "$";

  const defaultWorkflow: WorkflowType =
    (applicable_workflows?.[0] as WorkflowType) ?? "technical-swing";

  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowType>(defaultWorkflow);
  const [portfolioSize, setPortfolioSize] = useState<string>("");
  const [maxRiskPct, setMaxRiskPct] = useState<string>("1.0");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showPicker = (applicable_workflows?.length ?? 0) >= 2;
  const meta = WORKFLOW_META[selectedWorkflow];

  function handleSubmit() {
    const size = parseFloat(portfolioSize);
    const riskPct = parseFloat(maxRiskPct);

    if (!size || size <= 0) {
      setError("Portfolio size must be a positive number.");
      return;
    }
    if (!riskPct || riskPct < 0.1 || riskPct > 10) {
      setError("Max risk % must be between 0.1 and 10.");
      return;
    }

    startResearch({
      symbol,
      market,
      workflow_type: selectedWorkflow,
      portfolio_size: size,
      max_risk_pct: riskPct,
      force: false,
      force_refresh: forceRefresh,
    });

    onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="w-full max-w-md"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          boxShadow: "0 24px 64px rgba(0,0,0,0.5)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-base font-bold" style={{ color: "var(--text)" }}>
                {symbol}
              </span>
              <span
                className="px-1.5 py-0.5 text-xs font-mono rounded"
                style={{
                  background: market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                  color: market === "US" ? "#93c5fd" : "var(--accent)",
                }}
              >
                {market}
              </span>
            </div>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
              {meta.label} — configure your position parameters
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex items-center justify-center w-7 h-7 rounded"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--text-dim)",
              cursor: "pointer",
              fontSize: 18,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Workflow picker */}
          {showPicker && (
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-widest font-semibold" style={{ color: "var(--text-dim)" }}>
                Strategy — 2 setups detected
              </p>
              <div className="grid grid-cols-2 gap-2">
                {(applicable_workflows as WorkflowType[]).map((wf) => {
                  const m = WORKFLOW_META[wf];
                  const active = selectedWorkflow === wf;
                  return (
                    <button
                      key={wf}
                      onClick={() => { setSelectedWorkflow(wf); setError(null); }}
                      className="text-left p-3 rounded-sm transition-colors"
                      style={{
                        background: active ? "var(--surface-2)" : "transparent",
                        border: `1px solid ${active ? m.color : "var(--border)"}`,
                        cursor: "pointer",
                      }}
                    >
                      <p className="text-xs font-mono font-semibold" style={{ color: active ? m.color : "var(--text-muted)" }}>
                        {m.label}
                      </p>
                      <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
                        {m.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Portfolio size */}
          <div className="space-y-1">
            <label
              htmlFor="portfolio-size"
              className="block text-xs uppercase tracking-wide"
              style={{ color: "var(--text-muted)" }}
            >
              Portfolio Size ({currency})
            </label>
            <div className="relative">
              <span
                className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-mono pointer-events-none"
                style={{ color: "var(--text-dim)" }}
              >
                {currencyPrefix}
              </span>
              <input
                id="portfolio-size"
                type="number"
                value={portfolioSize}
                onChange={(e) => { setPortfolioSize(e.target.value); setError(null); }}
                placeholder="100000"
                min="1000"
                step="1000"
                className="w-full pl-7 pr-3 py-2.5 text-sm font-mono rounded-sm"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>
          </div>

          {/* Max risk */}
          <div className="space-y-1">
            <label
              htmlFor="max-risk"
              className="block text-xs uppercase tracking-wide"
              style={{ color: "var(--text-muted)" }}
            >
              Max Risk per Trade (%)
            </label>
            <div className="relative">
              <input
                id="max-risk"
                type="number"
                value={maxRiskPct}
                onChange={(e) => { setMaxRiskPct(e.target.value); setError(null); }}
                placeholder="1.0"
                min="0.1"
                max="10"
                step="0.1"
                className="w-full px-3 py-2.5 pr-8 text-sm font-mono rounded-sm"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
              <span
                className="absolute right-3 top-1/2 -translate-y-1/2 text-sm font-mono pointer-events-none"
                style={{ color: "var(--text-dim)" }}
              >
                %
              </span>
            </div>
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>Range: 0.1% – 10%</p>
          </div>

          {/* Force refresh */}
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={forceRefresh}
              onChange={(e) => setForceRefresh(e.target.checked)}
              style={{ accentColor: "var(--accent)", width: 14, height: 14 }}
            />
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              Force refresh (bypass 24h dedup cache)
            </span>
          </label>

          {/* Error */}
          {error && (
            <p
              className="text-xs p-2 rounded"
              style={{ background: "var(--red-dim)", color: "#fca5a5" }}
            >
              {error}
            </p>
          )}

          {/* Info note */}
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Research runs in the background — you can continue browsing while it analyzes.
          </p>

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 text-xs font-semibold font-mono uppercase tracking-wide"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: 2,
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!portfolioSize}
              className="flex-[2] py-2.5 text-xs font-semibold font-mono uppercase tracking-wide transition-colors"
              style={{
                background: !portfolioSize ? "var(--surface-2)" : "#1e3a5f",
                border: `1px solid ${meta.color}`,
                borderRadius: 2,
                color: !portfolioSize ? "var(--text-dim)" : meta.color,
                cursor: !portfolioSize ? "not-allowed" : "pointer",
              }}
            >
              Run Research
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
