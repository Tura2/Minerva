"use client";

import { useEffect, useRef, useState } from "react";
import { getCandidates, getScanHistory, runScan } from "@/lib/api/scanner";
import type { Candidate, Market, ScanHistoryItem } from "@/lib/types";
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

function ScoreBar({ score }: { score: number }) {
  const color = score >= 70 ? "var(--green)" : score >= 50 ? "var(--accent)" : "var(--text-dim)";
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex-1 rounded-full overflow-hidden"
        style={{ height: 4, background: "var(--surface-2)" }}
      >
        <div style={{ width: `${score}%`, height: "100%", background: color, borderRadius: 9999 }} />
      </div>
      <span className="font-mono text-xs w-8 text-right" style={{ color }}>
        {score.toFixed(0)}
      </span>
    </div>
  );
}

// ── Toast banner ─────────────────────────────────────────────────────────────
function Banner({ msg, onDismiss }: { msg: { text: string; ok: boolean }; onDismiss: () => void }) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2 text-sm rounded"
      style={{
        background: msg.ok ? "var(--green-dim)" : "var(--red-dim)",
        border: `1px solid ${msg.ok ? "var(--green)" : "var(--red)"}`,
        color: msg.ok ? "var(--green)" : "var(--red)",
      }}
    >
      <span>{msg.text}</span>
      <button onClick={onDismiss} style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: 16 }}>
        ×
      </button>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [banner, setBanner] = useState<{ text: string; ok: boolean } | null>(null);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");
  const [scanMarket, setScanMarket] = useState<Market>("US");
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>([]);
  const [historyExpanded, setHistoryExpanded] = useState(false);

  // Single-symbol search
  const [searchSymbol, setSearchSymbol] = useState("");
  const [searchMarket, setSearchMarket] = useState<Market>("US");
  const searchRef = useRef<HTMLInputElement>(null);

  // Research modal
  const [researchTarget, setResearchTarget] = useState<{
    symbol: string;
    market: Market;
    applicable_workflows?: import("@/lib/types").WorkflowType[];
  } | null>(null);

  async function loadCandidates(market?: Market) {
    try {
      const data = await getCandidates(market, 200);
      setCandidates(data);
    } finally {
      setLoading(false);
    }
  }

  async function loadHistory() {
    try {
      const data = await getScanHistory(undefined, 20);
      setScanHistory(data);
    } catch {
      // non-critical, silently ignore
    }
  }

  useEffect(() => {
    loadCandidates(filterMarket === "ALL" ? undefined : filterMarket);
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterMarket]);

  // ── Watchlist scan ──────────────────────────────────────────────────────
  async function handleWatchlistScan() {
    setScanning(true);
    setBanner(null);
    try {
      const result = await runScan({ market: scanMarket, limit: 200 });
      const fresh = await getCandidates(filterMarket === "ALL" ? undefined : filterMarket, 200);
      setCandidates(fresh);
      loadHistory();
      setBanner({
        ok: true,
        text: `Scan complete — ${result.total_passed} of ${result.total_in_watchlist} watchlist symbols passed.`,
      });
    } catch (err) {
      setBanner({
        ok: false,
        text: err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : "Scan failed. Check backend logs.",
      });
    } finally {
      setScanning(false);
    }
  }

  // ── Single-symbol scan ──────────────────────────────────────────────────
  async function handleSymbolScan(e: React.FormEvent) {
    e.preventDefault();
    const sym = searchSymbol.trim().toUpperCase();
    if (!sym) return;

    setScanning(true);
    setBanner(null);
    try {
      const result = await runScan({ market: searchMarket, symbols: [sym], limit: 1 });
      // Prepend result to current list (or show inline)
      const fresh = await getCandidates(filterMarket === "ALL" ? undefined : filterMarket, 200);
      setCandidates(fresh);
      if (result.total_passed === 0) {
        setBanner({ ok: false, text: `${sym} did not pass screening filters for ${searchMarket}.` });
      } else {
        setBanner({ ok: true, text: `${sym} passed screening — added to candidates.` });
        setSearchSymbol("");
      }
    } catch (err) {
      setBanner({
        ok: false,
        text: err instanceof ApiError && typeof err.detail === "string"
          ? err.detail
          : `Could not scan ${sym}. Is it a valid ticker?`,
      });
    } finally {
      setScanning(false);
    }
  }

  const filtered =
    filterMarket === "ALL" ? candidates : candidates.filter((c) => c.market === filterMarket);

  return (
    <div className="space-y-5">
      {researchTarget && (
        <ResearchModal
          symbol={researchTarget.symbol}
          market={researchTarget.market}
          applicable_workflows={researchTarget.applicable_workflows}
          onClose={() => setResearchTarget(null)}
        />
      )}

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold" style={{ color: "var(--text)" }}>
          Candidates
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-dim)" }}>
          {filtered.length} symbol{filtered.length !== 1 ? "s" : ""} passed screening
        </p>
      </div>

      {/* Controls row */}
      <div
        className="p-4 space-y-4"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "6px",
          boxShadow: "var(--shadow)",
        }}
      >
        {/* ── Single symbol search ── */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Quick Scan — Single Symbol
          </p>
          <form onSubmit={handleSymbolScan} className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-48">
              <span
                className="absolute left-3 top-1/2 -translate-y-1/2 text-xs"
                style={{ color: "var(--text-dim)" }}
              >
                🔍
              </span>
              <input
                ref={searchRef}
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
                placeholder="Enter ticker  e.g. NVDA"
                maxLength={20}
                className="w-full pl-8 pr-3 py-2 text-sm font-mono uppercase rounded-sm"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
            </div>
            <select
              value={searchMarket}
              onChange={(e) => setSearchMarket(e.target.value as Market)}
              className="px-3 py-2 text-sm font-medium rounded-sm"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                cursor: "pointer",
              }}
            >
              <option value="US">US</option>
              <option value="TASE">TASE</option>
            </select>
            <button
              type="submit"
              disabled={scanning || !searchSymbol.trim()}
              className="px-4 py-2 text-sm font-semibold transition-colors rounded-sm"
              style={{
                background: scanning || !searchSymbol.trim() ? "var(--surface-2)" : "var(--blue-dim)",
                border: "1px solid var(--blue)",
                color: scanning || !searchSymbol.trim() ? "var(--text-dim)" : "var(--blue)",
                cursor: scanning || !searchSymbol.trim() ? "not-allowed" : "pointer",
              }}
            >
              {scanning ? "Scanning…" : "Scan Symbol"}
            </button>
          </form>
        </div>

        {/* Divider */}
        <div style={{ borderTop: "1px solid var(--border-subtle)" }} />

        {/* ── Watchlist scan ── */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Watchlist Scan — Full Universe
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={scanMarket}
              onChange={(e) => setScanMarket(e.target.value as Market)}
              className="px-3 py-2 text-sm font-medium rounded-sm"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                cursor: "pointer",
              }}
            >
              <option value="US">US Watchlist</option>
              <option value="TASE">TASE Watchlist</option>
            </select>
            <button
              onClick={handleWatchlistScan}
              disabled={scanning}
              className="px-4 py-2 text-sm font-semibold transition-colors rounded-sm"
              style={{
                background: scanning ? "var(--surface-2)" : "var(--accent-dim)",
                border: "1px solid var(--accent)",
                color: scanning ? "var(--text-dim)" : "var(--accent)",
                cursor: scanning ? "not-allowed" : "pointer",
              }}
            >
              {scanning ? "Scanning…" : "▶ Run Scan"}
            </button>
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              Scans all {scanMarket} symbols in your watchlist
            </span>
          </div>
        </div>
      </div>

      {/* Banner */}
      {banner && <Banner msg={banner} onDismiss={() => setBanner(null)} />}

      {/* Scan History */}
      {scanHistory.length > 0 && (
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            overflow: "hidden",
            boxShadow: "var(--shadow)",
          }}
        >
          <button
            onClick={() => setHistoryExpanded((x) => !x)}
            className="w-full flex items-center justify-between px-4 py-2 text-xs font-semibold uppercase tracking-widest"
            style={{
              color: "var(--text-dim)",
              background: "none",
              border: "none",
              cursor: "pointer",
              borderBottom: historyExpanded ? "1px solid var(--border)" : "none",
            }}
          >
            <span>Recent Scans</span>
            <span>{historyExpanded ? "▲" : "▼"}</span>
          </button>

          {historyExpanded && (
            <div>
              {(historyExpanded ? scanHistory.slice(0, 20) : scanHistory.slice(0, 5)).map((h) => (
                <div
                  key={h.id}
                  className="grid items-center px-4 py-2 text-xs"
                  style={{
                    gridTemplateColumns: "60px 1fr 80px 160px",
                    borderBottom: "1px solid var(--border-subtle)",
                    color: "var(--text-dim)",
                  }}
                >
                  <span
                    className="px-1.5 py-0.5 text-xs font-semibold rounded w-fit"
                    style={{
                      background: h.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                      color: h.market === "US" ? "var(--blue)" : "var(--accent)",
                    }}
                  >
                    {h.market}
                  </span>
                  <span className="font-mono" style={{ color: "var(--text)" }}>
                    {h.candidate_count} / {h.total_in_watchlist || "?"} passed
                  </span>
                  <span
                    className="px-1 py-0.5 rounded text-center"
                    style={{
                      background: h.status === "completed" ? "var(--green-dim)" : "var(--red-dim)",
                      color: h.status === "completed" ? "var(--green)" : "var(--red)",
                    }}
                  >
                    {h.status}
                  </span>
                  <span style={{ textAlign: "right" }}>{formatDate(h.ran_at)}</span>
                </div>
              ))}
              {!historyExpanded && scanHistory.length > 5 && (
                <button
                  onClick={() => setHistoryExpanded(true)}
                  className="w-full py-2 text-xs"
                  style={{ color: "var(--text-dim)", background: "none", border: "none", cursor: "pointer" }}
                >
                  View all {scanHistory.length} scans ▼
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Market filter */}
      <div className="flex gap-1">
        {(["ALL", "US", "TASE"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setFilterMarket(m)}
            className="px-3 py-1.5 text-xs font-semibold transition-colors"
            style={{
              background: filterMarket === m ? "var(--surface-2)" : "transparent",
              border: "1px solid",
              borderColor: filterMarket === m ? "var(--border)" : "transparent",
              borderRadius: "4px",
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
          borderRadius: "6px",
          overflow: "hidden",
          boxShadow: "var(--shadow)",
        }}
      >
        {/* Header */}
        <div
          className="grid px-4 py-2 text-xs font-semibold uppercase tracking-widest"
          style={{
            gridTemplateColumns: "80px 72px 90px 90px 1fr 120px 130px 100px",
            borderBottom: "1px solid var(--border)",
            color: "var(--text-dim)",
          }}
        >
          <span>Symbol</span>
          <span>Mkt</span>
          <span className="text-right">Price</span>
          <span className="text-right">Volume</span>
          <span className="pl-2">Score</span>
          <span>Strategy</span>
          <span>Screened</span>
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
              Add symbols to your watchlist and run a scan, or search a single symbol above.
            </p>
          </div>
        ) : (
          filtered.map((c) => (
            <div
              key={c.id}
              className="grid items-center px-4 py-3 transition-colors"
              style={{
                gridTemplateColumns: "80px 72px 90px 90px 1fr 120px 130px 100px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <span className="font-bold text-sm" style={{ color: "var(--text)" }}>
                {c.symbol}
              </span>

              <span
                className="px-1.5 py-0.5 text-xs font-semibold rounded w-fit"
                style={{
                  background: c.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                  color: c.market === "US" ? "var(--blue)" : "var(--accent)",
                }}
              >
                {c.market}
              </span>

              <span className="font-mono text-sm text-right" style={{ color: "var(--text)" }}>
                {c.price?.toFixed(2) ?? "—"}
              </span>

              <span className="font-mono text-xs text-right" style={{ color: "var(--text-muted)" }}>
                {c.volume ? formatVolume(c.volume) : "—"}
              </span>

              <div className="pl-2">
                <ScoreBar score={c.score ?? 0} />
              </div>

              {/* Workflow badge(s) */}
              <div className="flex flex-wrap gap-1">
                {(c.applicable_workflows ?? ["technical-swing"]).map((wf) => (
                  <span
                    key={wf}
                    className="px-1.5 py-0.5 text-xs font-mono rounded"
                    style={{
                      background: wf === "mean-reversion-bounce" ? "var(--accent-dim)" : "var(--blue-dim)",
                      color: wf === "mean-reversion-bounce" ? "var(--accent)" : "var(--blue)",
                      whiteSpace: "nowrap",
                    }}
                    title={wf}
                  >
                    {wf === "mean-reversion-bounce" ? "MR" : "Swing"}
                  </span>
                ))}
              </div>

              <span className="text-xs flex items-center gap-1" style={{ color: "var(--text-dim)" }}>
                {c.is_stale && (
                  <span title="Data older than 24h" style={{ color: "var(--accent)" }}>⚠</span>
                )}
                {formatDate(c.screened_at)}
              </span>

              <div className="flex justify-end">
                <button
                  onClick={() =>
                    setResearchTarget({
                      symbol: c.symbol,
                      market: c.market,
                      applicable_workflows: c.applicable_workflows,
                    })
                  }
                  className="px-3 py-1 text-xs font-semibold transition-colors rounded-sm"
                  style={{
                    background: "var(--blue-dim)",
                    border: "1px solid var(--blue)",
                    color: "var(--blue)",
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
