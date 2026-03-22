"use client";

import { useEffect, useRef, useState } from "react";
import { getCandidates, getScanHistory, runScan } from "@/lib/api/scanner";
import type { Candidate, Market, ScanHistoryItem } from "@/lib/types";
import { ApiError } from "@/lib/types";
import ResearchModal from "@/components/ResearchModal";

// ── Symbol icon ────────────────────────────────────────────────────────────────

const SYMBOL_COLORS = [
  "#3b82f6", "#8b5cf6", "#57c1d5", "#10b981", "#06b6d4",
  "#6366f1", "#14b8a6", "#0ea5e9", "#22d3ee", "#a78bfa",
];

function symbolColor(symbol: string): string {
  let hash = 0;
  for (let i = 0; i < symbol.length; i++) hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
  return SYMBOL_COLORS[Math.abs(hash) % SYMBOL_COLORS.length];
}

function SymbolIcon({ symbol }: { symbol: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <span
        className="inline-flex items-center justify-center shrink-0 rounded-full font-bold"
        style={{ width: 26, height: 26, background: symbolColor(symbol), color: "#fff", fontSize: 10 }}
      >
        {symbol.slice(0, 2).toUpperCase()}
      </span>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/${symbol}.png`}
      alt={symbol}
      width={26}
      height={26}
      className="rounded-full shrink-0 object-cover"
      onError={() => setFailed(true)}
    />
  );
}

function formatVolume(v: number) {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return String(v);
}

function formatAge(iso: string) {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Candidate card ────────────────────────────────────────────────────────────
function CandidateCard({
  c,
  onResearch,
}: {
  c: Candidate;
  onResearch: (c: Candidate) => void;
}) {
  const score = c.score ?? 0;
  const scoreColor =
    score >= 70 ? "var(--green)" : score >= 50 ? "var(--accent)" : "var(--text-dim)";

  return (
    <div
      className="flex flex-col"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: 6,
        overflow: "hidden",
        transition: "border-color 0.15s, box-shadow 0.15s",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--accent)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "0 4px 20px rgba(0,0,0,0.25)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLDivElement).style.borderColor = "var(--border)";
        (e.currentTarget as HTMLDivElement).style.boxShadow = "none";
      }}
    >
      {/* Score accent bar */}
      <div style={{ height: 2, background: scoreColor, width: `${score}%` }} />

      <div className="flex flex-col flex-1 p-3 gap-3">
        {/* Top row: symbol + badges */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <SymbolIcon symbol={c.symbol} />
            <div>
              <span className="font-mono font-bold text-base" style={{ color: "var(--text)" }}>
                {c.symbol}
              </span>
              {c.is_stale && (
                <span
                  className="ml-1.5 text-xs"
                  title="Data older than 24h"
                  style={{ color: "var(--accent)" }}
                >
                  ⚠
                </span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 flex-wrap justify-end">
            <span
              className="px-1.5 py-0.5 text-xs font-mono font-semibold rounded"
              style={{
                background: c.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                color: c.market === "US" ? "#93c5fd" : "var(--accent)",
              }}
            >
              {c.market}
            </span>
            {(c.applicable_workflows ?? ["technical-swing"]).map((wf) => (
              <span
                key={wf}
                className="px-1.5 py-0.5 text-xs font-mono rounded"
                style={{
                  background:
                    wf === "mean-reversion-bounce" ? "rgba(87,193,213,0.1)" : "rgba(59,130,246,0.1)",
                  color: wf === "mean-reversion-bounce" ? "var(--accent)" : "var(--blue)",
                  border: `1px solid ${wf === "mean-reversion-bounce" ? "rgba(87,193,213,0.3)" : "rgba(59,130,246,0.3)"}`,
                }}
                title={wf}
              >
                {wf === "mean-reversion-bounce" ? "MR" : "Swing"}
              </span>
            ))}
          </div>
        </div>

        {/* Price + volume */}
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-lg font-semibold" style={{ color: "var(--text)" }}>
            {c.price?.toFixed(2) ?? "—"}
          </span>
          {c.volume != null && (
            <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
              vol {formatVolume(c.volume)}
            </span>
          )}
        </div>

        {/* Score bar */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              Score
            </span>
            <span className="font-mono text-xs font-semibold" style={{ color: scoreColor }}>
              {score.toFixed(0)}
            </span>
          </div>
          <div
            className="rounded-full overflow-hidden"
            style={{ height: 3, background: "var(--surface-2)" }}
          >
            <div
              style={{
                width: `${score}%`,
                height: "100%",
                background: scoreColor,
                borderRadius: 9999,
                transition: "width 0.4s ease",
              }}
            />
          </div>
        </div>

        {/* Footer: age + research button */}
        <div className="flex items-center justify-between mt-auto pt-1">
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>
            {formatAge(c.screened_at)}
          </span>
          <button
            onClick={() => onResearch(c)}
            className="px-3 py-1.5 text-xs font-semibold font-mono uppercase tracking-wide transition-colors"
            style={{
              background: "var(--blue-dim)",
              border: "1px solid var(--blue)",
              borderRadius: 3,
              color: "var(--blue)",
              cursor: "pointer",
            }}
          >
            Research
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Banner ────────────────────────────────────────────────────────────────────
function Banner({ msg, onDismiss }: { msg: { text: string; ok: boolean }; onDismiss: () => void }) {
  return (
    <div
      className="flex items-center justify-between px-4 py-2.5 text-sm rounded"
      style={{
        background: msg.ok ? "var(--green-dim)" : "var(--red-dim)",
        border: `1px solid ${msg.ok ? "var(--green)" : "var(--red)"}`,
        color: msg.ok ? "var(--green)" : "var(--red)",
      }}
    >
      <span>{msg.text}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss"
        style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", fontSize: 16 }}
      >
        ×
      </button>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function CandidatesPage() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [banner, setBanner] = useState<{ text: string; ok: boolean } | null>(null);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");
  const [scanMarket, setScanMarket] = useState<Market>("US");
  const [scanHistory, setScanHistory] = useState<ScanHistoryItem[]>([]);
  const [historyExpanded, setHistoryExpanded] = useState(false);

  const [searchSymbol, setSearchSymbol] = useState("");
  const [searchMarket, setSearchMarket] = useState<Market>("US");
  const searchRef = useRef<HTMLInputElement>(null);

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
      // non-critical
    }
  }

  useEffect(() => {
    loadCandidates(filterMarket === "ALL" ? undefined : filterMarket);
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterMarket]);

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
        text: `Scan complete — ${result.total_passed} of ${result.total_in_watchlist} passed.`,
      });
    } catch (err) {
      setBanner({
        ok: false,
        text:
          err instanceof ApiError && typeof err.detail === "string"
            ? err.detail
            : "Scan failed. Check backend logs.",
      });
    } finally {
      setScanning(false);
    }
  }

  async function handleSymbolScan(e: React.FormEvent) {
    e.preventDefault();
    const sym = searchSymbol.trim().toUpperCase();
    if (!sym) return;

    setScanning(true);
    setBanner(null);
    try {
      const result = await runScan({ market: searchMarket, symbols: [sym], limit: 1 });
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
        text:
          err instanceof ApiError && typeof err.detail === "string"
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
        <h1 className="font-mono text-xl font-bold" style={{ color: "var(--text)" }}>
          Candidates
        </h1>
        <p className="text-sm mt-0.5" style={{ color: "var(--text-dim)" }}>
          {filtered.length} symbol{filtered.length !== 1 ? "s" : ""} passed screening
        </p>
      </div>

      {/* Controls */}
      <div
        className="p-4 space-y-4"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
        }}
      >
        {/* Single symbol */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Quick Scan — Single Symbol
          </p>
          <form onSubmit={handleSymbolScan} className="flex gap-2 flex-wrap">
            <div className="relative flex-1 min-w-40">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8"
                style={{ color: "var(--text-dim)" }}
              >
                <circle cx="5" cy="5" r="4" /><path d="M8.5 8.5L11 11" />
              </svg>
              <input
                ref={searchRef}
                value={searchSymbol}
                onChange={(e) => setSearchSymbol(e.target.value.toUpperCase())}
                placeholder="e.g. NVDA"
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
              className="px-3 py-2 text-sm rounded-sm"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", cursor: "pointer" }}
            >
              <option value="US">US</option>
              <option value="TASE">TASE</option>
            </select>
            <button
              type="submit"
              disabled={scanning || !searchSymbol.trim()}
              className="px-4 py-2 text-sm font-semibold rounded-sm transition-colors"
              style={{
                background: scanning || !searchSymbol.trim() ? "var(--surface-2)" : "var(--blue-dim)",
                border: "1px solid var(--blue)",
                color: scanning || !searchSymbol.trim() ? "var(--text-dim)" : "var(--blue)",
                cursor: scanning || !searchSymbol.trim() ? "not-allowed" : "pointer",
              }}
            >
              {scanning ? "Scanning…" : "Scan"}
            </button>
          </form>
        </div>

        <div style={{ borderTop: "1px solid var(--border-subtle)" }} />

        {/* Watchlist scan */}
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
            Watchlist Scan — Full Universe
          </p>
          <div className="flex items-center gap-2 flex-wrap">
            <select
              value={scanMarket}
              onChange={(e) => setScanMarket(e.target.value as Market)}
              className="px-3 py-2 text-sm rounded-sm"
              style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)", cursor: "pointer" }}
            >
              <option value="US">US Watchlist</option>
              <option value="TASE">TASE Watchlist</option>
            </select>
            <button
              onClick={handleWatchlistScan}
              disabled={scanning}
              className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-sm transition-colors"
              style={{
                background: scanning ? "var(--surface-2)" : "var(--accent-dim)",
                border: "1px solid var(--accent)",
                color: scanning ? "var(--text-dim)" : "var(--accent)",
                cursor: scanning ? "not-allowed" : "pointer",
              }}
            >
              {scanning ? (
                "Scanning…"
              ) : (
                <>
                  <svg width="11" height="11" viewBox="0 0 11 11" fill="currentColor">
                    <polygon points="2,1 9,5.5 2,10" />
                  </svg>
                  Run Scan
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Banner */}
      {banner && <Banner msg={banner} onDismiss={() => setBanner(null)} />}

      {/* Scan history */}
      {scanHistory.length > 0 && (
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            overflow: "hidden",
          }}
        >
          <button
            onClick={() => setHistoryExpanded((x) => !x)}
            className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-semibold uppercase tracking-widest"
            style={{
              color: "var(--text-dim)",
              background: "none",
              border: "none",
              cursor: "pointer",
              borderBottom: historyExpanded ? "1px solid var(--border)" : "none",
            }}
          >
            <span>Recent Scans</span>
            <span style={{ fontSize: 10 }}>{historyExpanded ? "▲" : "▼"}</span>
          </button>
          {historyExpanded &&
            scanHistory.slice(0, 10).map((h) => (
              <div
                key={h.id}
                className="grid items-center px-4 py-2 text-xs"
                style={{
                  gridTemplateColumns: "56px 1fr 80px 140px",
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
                <span className="text-right">
                  {new Date(h.ran_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </span>
              </div>
            ))}
        </div>
      )}

      {/* Market filter */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {(["ALL", "US", "TASE"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setFilterMarket(m)}
              className="px-3 py-1.5 text-xs font-semibold transition-colors rounded"
              style={{
                background: filterMarket === m ? "var(--surface-2)" : "transparent",
                border: "1px solid",
                borderColor: filterMarket === m ? "var(--border)" : "transparent",
                color: filterMarket === m ? "var(--text)" : "var(--text-dim)",
                cursor: "pointer",
              }}
            >
              {m}
            </button>
          ))}
        </div>
        {!loading && filtered.length > 0 && (
          <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
            {filtered.length} candidates
          </span>
        )}
      </div>

      {/* Cards grid */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="skeleton rounded-md" style={{ height: 160 }} />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div
          className="py-16 text-center"
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 6,
          }}
        >
          <p className="text-sm" style={{ color: "var(--text-dim)" }}>
            No candidates yet.
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--text-dim)" }}>
            Add symbols to your watchlist and run a scan, or search a single symbol above.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {filtered.map((c) => (
            <CandidateCard
              key={c.id}
              c={c}
              onResearch={(candidate) =>
                setResearchTarget({
                  symbol: candidate.symbol,
                  market: candidate.market,
                  applicable_workflows: candidate.applicable_workflows,
                })
              }
            />
          ))}
        </div>
      )}
    </div>
  );
}
