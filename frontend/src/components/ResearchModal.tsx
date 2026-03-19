"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { executeResearch } from "@/lib/api/research";
import { ApiError, Market, PreScreenError } from "@/lib/types";

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

interface Props {
  symbol: string;
  market: Market;
  onClose: () => void;
}

export default function ResearchModal({ symbol, market, onClose }: Props) {
  const router = useRouter();
  const currency = market === "TASE" ? "ILS (₪)" : "USD ($)";
  const currencyPrefix = market === "TASE" ? "₪" : "$";

  const [portfolioSize, setPortfolioSize] = useState<string>("");
  const [maxRiskPct, setMaxRiskPct] = useState<string>("1.0");
  const [forceRefresh, setForceRefresh] = useState(false);
  const [loading, setLoading] = useState(false);
  const [preScreenError, setPreScreenError] = useState<PreScreenError | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubmit(force = false) {
    const size = parseFloat(portfolioSize);
    const riskPct = parseFloat(maxRiskPct);

    if (!size || size <= 0) {
      setErrorMessage("Portfolio size must be a positive number.");
      return;
    }
    if (!riskPct || riskPct < 0.1 || riskPct > 10) {
      setErrorMessage("Max risk % must be between 0.1 and 10.");
      return;
    }

    setLoading(true);
    setErrorMessage(null);
    setPreScreenError(null);

    try {
      const ticket = await executeResearch({
        symbol,
        market,
        portfolio_size: size,
        max_risk_pct: riskPct,
        force,
        force_refresh: forceRefresh,
      });
      router.push(`/research/${ticket.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isPreScreenFailed()) {
          setPreScreenError(err.detail as PreScreenError);
        } else {
          const msg =
            typeof err.detail === "string"
              ? err.detail
              : "Research failed. Check backend logs.";
          setErrorMessage(msg);
        }
      } else {
        setErrorMessage("Network error. Is the backend running?");
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full max-w-md"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <span
              className="font-mono text-base font-semibold"
              style={{ color: "var(--text)" }}
            >
              {symbol}
            </span>
            <span
              className="ml-2 px-1.5 py-0.5 text-xs font-mono rounded"
              style={{
                background: market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                color: market === "US" ? "#93c5fd" : "var(--accent)",
              }}
            >
              {market}
            </span>
            <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
              technical-swing research
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-xl leading-none transition-colors"
            style={{ color: "var(--text-dim)" }}
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="px-5 py-4 space-y-4">
          {/* Pre-screen failure block */}
          {preScreenError && (
            <div
              className="rounded p-4 space-y-3"
              style={{ background: "var(--red-dim)", border: "1px solid #ef4444" }}
            >
              <p className="text-sm font-semibold" style={{ color: "#fca5a5" }}>
                Pre-Screen Failed
              </p>
              <p className="text-xs" style={{ color: "#fca5a5" }}>
                {preScreenError.pre_screen_summary}
              </p>

              {/* Check results */}
              <ul className="space-y-1">
                {Object.entries(preScreenError.checks).map(([key, passed]) => (
                  <li key={key} className="flex items-center gap-2 text-xs">
                    <span
                      className="font-mono w-3 text-center"
                      style={{ color: passed ? "var(--green)" : "#ef4444" }}
                    >
                      {passed ? "✓" : "✗"}
                    </span>
                    <span style={{ color: passed ? "var(--text-muted)" : "#fca5a5" }}>
                      {CHECK_LABELS[key] ?? key}
                    </span>
                  </li>
                ))}
              </ul>

              {/* VCP info */}
              {preScreenError.vcp && (
                <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                  VCP contractions detected: {preScreenError.vcp.contraction_count}
                  {preScreenError.vcp.is_vcp ? " — VCP pattern confirmed" : ""}
                </p>
              )}

              {/* Force button */}
              <button
                onClick={() => handleSubmit(true)}
                disabled={loading}
                className="w-full py-2 text-xs font-semibold font-mono tracking-wide uppercase transition-colors"
                style={{
                  background: loading ? "var(--surface-2)" : "#78350f",
                  border: "1px solid #f59e0b",
                  borderRadius: "2px",
                  color: loading ? "var(--text-dim)" : "var(--accent)",
                  cursor: loading ? "not-allowed" : "pointer",
                }}
              >
                {loading ? "Running..." : "Force Research (bypass pre-screen)"}
              </button>
            </div>
          )}

          {/* Input form */}
          {!preScreenError && (
            <>
              <div className="space-y-1">
                <label
                  className="block text-xs uppercase tracking-wide"
                  style={{ color: "var(--text-muted)" }}
                >
                  Portfolio Size ({currency})
                </label>
                <div className="relative">
                  <span
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-sm font-mono"
                    style={{ color: "var(--text-dim)" }}
                  >
                    {currencyPrefix}
                  </span>
                  <input
                    type="number"
                    value={portfolioSize}
                    onChange={(e) => setPortfolioSize(e.target.value)}
                    placeholder="100000"
                    min="1000"
                    step="1000"
                    className="w-full pl-7 pr-3 py-2 text-sm font-mono"
                    style={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: "2px",
                      color: "var(--text)",
                    }}
                  />
                </div>
              </div>

              <div className="space-y-1">
                <label
                  className="block text-xs uppercase tracking-wide"
                  style={{ color: "var(--text-muted)" }}
                >
                  Max Risk per Trade (%)
                </label>
                <div className="relative">
                  <input
                    type="number"
                    value={maxRiskPct}
                    onChange={(e) => setMaxRiskPct(e.target.value)}
                    placeholder="1.0"
                    min="0.1"
                    max="10"
                    step="0.1"
                    className="w-full px-3 py-2 text-sm font-mono"
                    style={{
                      background: "var(--surface-2)",
                      border: "1px solid var(--border)",
                      borderRadius: "2px",
                      color: "var(--text)",
                    }}
                  />
                  <span
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-sm font-mono"
                    style={{ color: "var(--text-dim)" }}
                  >
                    %
                  </span>
                </div>
                <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                  Range: 0.1% – 10%
                </p>
              </div>

              {/* Force refresh checkbox */}
              <label className="flex items-center gap-2 cursor-pointer">
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
            </>
          )}

          {/* Generic error */}
          {errorMessage && (
            <p
              className="text-xs p-2 rounded"
              style={{ background: "var(--red-dim)", color: "#fca5a5" }}
            >
              {errorMessage}
            </p>
          )}

          {/* Actions */}
          <div className="flex gap-2 pt-1">
            <button
              onClick={onClose}
              className="flex-1 py-2 text-xs font-semibold font-mono uppercase tracking-wide transition-colors"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "2px",
                color: "var(--text-muted)",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            {!preScreenError && (
              <button
                onClick={() => handleSubmit(false)}
                disabled={loading || !portfolioSize}
                className="flex-[2] py-2 text-xs font-semibold font-mono uppercase tracking-wide transition-colors"
                style={{
                  background: loading || !portfolioSize ? "var(--surface-2)" : "#1e3a5f",
                  border: "1px solid var(--blue)",
                  borderRadius: "2px",
                  color: loading || !portfolioSize ? "var(--text-dim)" : "#93c5fd",
                  cursor: loading || !portfolioSize ? "not-allowed" : "pointer",
                }}
              >
                {loading ? "Analyzing..." : "Run Research"}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
