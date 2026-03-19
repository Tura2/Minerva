"use client";

import { useEffect, useState } from "react";
import { getCandidates, runScan } from "@/lib/api/scanner";
import type { Candidate, Market } from "@/lib/types";
import { ApiError } from "@/lib/types";
import ResearchModal from "@/components/ResearchModal";

function formatVolume(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");
  const [scanMarket, setScanMarket] = useState<Market>("US");

  // Research modal
  const [researchTarget, setResearchTarget] = useState<{
    symbol: string;
    market: Market;
  } | null>(null);

  async function loadCandidates(market?: Market) {
    try {
      const data = await getCandidates(market, 200);
      setCandidates(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCandidates(filterMarket === "ALL" ? undefined : filterMarket);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterMarket]);

  async function handleScan() {
    setScanning(true);
    setScanError(null);
    try {
      const result = await runScan({ market: scanMarket, limit: 200 });
      // Reload candidates after scan
      const fresh = await getCandidates(filterMarket === "ALL" ? undefined : filterMarket, 200);
      setCandidates(fresh);
      setScanError(
        `Scan complete — ${result.total_passed} of ${result.total_in_watchlist} symbols passed filters.`,
      );
    } catch (err) {
      if (err instanceof ApiError) {
        setScanError(
          typeof err.detail === "string" ? err.detail : "Scan failed. Check backend logs.",
        );
      } else {
        setScanError("Network error. Is the backend running?");
      }
    } finally {
      setScanning(false);
    }
  }

  const filtered =
    filterMarket === "ALL" ? candidates : candidates.filter((c) => c.market === filterMarket);

  return (
    <div className="space-y-6">
      {researchTarget && (
        <ResearchModal
          symbol={researchTarget.symbol}
          market={researchTarget.market}
          onClose={() => setResearchTarget(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1
            className="font-mono text-xl font-semibold tracking-wide"
            style={{ color: "var(--text)" }}
          >
            Candidates
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-dim)" }}>
            {filtered.length} symbol{filtered.length !== 1 ? "s" : ""} passed screening
          </p>
        </div>

        {/* Scan controls */}
        <div className="flex items-center gap-2">
          <select
            value={scanMarket}
            onChange={(e) => setScanMarket(e.target.value as Market)}
            className="px-3 py-1.5 text-xs font-mono"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              borderRadius: "2px",
              color: "var(--text)",
              cursor: "pointer",
            }}
          >
            <option value="US">US</option>
            <option value="TASE">TASE</option>
          </select>

          <button
            onClick={handleScan}
            disabled={scanning}
            className="px-4 py-1.5 text-xs font-mono font-semibold uppercase tracking-wide transition-colors"
            style={{
              background: scanning ? "var(--surface-2)" : "var(--accent-dim)",
              border: "1px solid var(--accent)",
              borderRadius: "2px",
              color: scanning ? "var(--text-dim)" : "var(--accent)",
              cursor: scanning ? "not-allowed" : "pointer",
            }}
          >
            {scanning ? "Scanning…" : "▶ Run Scan"}
          </button>
        </div>
      </div>

      {/* Scan result banner */}
      {scanError && (
        <div
          className="px-4 py-2 text-xs font-mono rounded"
          style={{
            background: scanError.startsWith("Scan complete")
              ? "var(--green-dim)"
              : "var(--red-dim)",
            border: `1px solid ${scanError.startsWith("Scan complete") ? "var(--green)" : "var(--red)"}`,
            color: scanError.startsWith("Scan complete") ? "var(--green)" : "#fca5a5",
          }}
        >
          {scanError}
        </div>
      )}

      {/* Market filter */}
      <div className="flex gap-1">
        {(["ALL", "US", "TASE"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setFilterMarket(m)}
            className="px-3 py-1.5 text-xs font-mono uppercase tracking-wide transition-colors"
            style={{
              background: filterMarket === m ? "var(--surface-2)" : "transparent",
              border: "1px solid",
              borderColor: filterMarket === m ? "var(--border)" : "transparent",
              borderRadius: "2px",
              color: filterMarket === m ? "var(--text)" : "var(--text-dim)",
              cursor: "pointer",
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Table */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          className="grid px-4 py-2 text-xs font-mono uppercase tracking-widest"
          style={{
            gridTemplateColumns: "80px 70px 100px 100px 80px 1fr 100px",
            borderBottom: "1px solid var(--border)",
            color: "var(--text-dim)",
          }}
        >
          <span>Symbol</span>
          <span>Market</span>
          <span className="text-right">Price</span>
          <span className="text-right">Volume</span>
          <span className="text-right">Score</span>
          <span className="pl-4">Screened</span>
          <span className="text-right">Action</span>
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="skeleton h-10 rounded" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              No candidates yet.
            </p>
            <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
              Add symbols to your watchlist and run a scan.
            </p>
          </div>
        ) : (
          filtered.map((c) => (
            <div
              key={c.id}
              className="grid items-center px-4 py-3 hover:bg-zinc-800 transition-colors"
              style={{
                gridTemplateColumns: "80px 70px 100px 100px 80px 1fr 100px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <span className="font-mono text-sm font-semibold" style={{ color: "var(--text)" }}>
                {c.symbol}
              </span>

              <span
                className="px-1.5 py-0.5 text-xs font-mono rounded w-fit"
                style={{
                  background: c.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                  color: c.market === "US" ? "#93c5fd" : "var(--accent)",
                }}
              >
                {c.market}
              </span>

              <span
                className="font-mono text-sm text-right"
                style={{ color: "var(--text)" }}
              >
                {c.price.toFixed(2)}
              </span>

              <span
                className="font-mono text-xs text-right"
                style={{ color: "var(--text-muted)" }}
              >
                {formatVolume(c.volume)}
              </span>

              {/* Score bar */}
              <div className="flex items-center justify-end gap-1.5">
                <span
                  className="font-mono text-xs"
                  style={{
                    color:
                      c.score >= 70
                        ? "var(--green)"
                        : c.score >= 50
                          ? "var(--accent)"
                          : "var(--text-muted)",
                  }}
                >
                  {c.score.toFixed(0)}
                </span>
              </div>

              <span className="pl-4 text-xs font-mono" style={{ color: "var(--text-dim)" }}>
                {formatDate(c.screened_at)}
              </span>

              <div className="flex justify-end">
                <button
                  onClick={() => setResearchTarget({ symbol: c.symbol, market: c.market })}
                  className="px-2 py-1 text-xs font-mono uppercase tracking-wide transition-colors"
                  style={{
                    background: "var(--blue-dim)",
                    border: "1px solid var(--blue)",
                    borderRadius: "2px",
                    color: "#93c5fd",
                    cursor: "pointer",
                  }}
                >
                  Research
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
