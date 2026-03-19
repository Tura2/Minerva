"use client";

import { useEffect, useState } from "react";
import { listWatchlist, addWatchlistItem, removeWatchlistItem } from "@/lib/api/watchlist";
import { getQuotes, Quote } from "@/lib/api/market";
import type { Market, WatchlistItem } from "@/lib/types";
import { ApiError } from "@/lib/types";

// ── Symbol icon ──────────────────────────────────────────────────────────────

const SYMBOL_COLORS = [
  "#3b82f6", "#8b5cf6", "#57c1d5", "#10b981", "#06b6d4",
  "#6366f1", "#14b8a6", "#0ea5e9", "#22d3ee", "#a78bfa",
  "#34d399", "#38bdf8", "#7c3aed", "#0891b2", "#84cc16",
];

function symbolColor(symbol: string): string {
  let hash = 0;
  for (let i = 0; i < symbol.length; i++) {
    hash = symbol.charCodeAt(i) + ((hash << 5) - hash);
  }
  return SYMBOL_COLORS[Math.abs(hash) % SYMBOL_COLORS.length];
}

function SymbolIcon({ symbol }: { symbol: string }) {
  const [failed, setFailed] = useState(false);
  const src = `https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/${symbol}.png`;

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
      src={src}
      alt={symbol}
      width={26}
      height={26}
      className="rounded-full shrink-0 object-cover"
      onError={() => setFailed(true)}
    />
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function PriceInline({ quote, loading }: { quote?: Quote; loading: boolean }) {
  if (loading) return <span className="skeleton inline-block w-14 h-3 align-middle" />;
  if (!quote || quote.error) return null;

  const up = quote.change_pct >= 0;
  const sign = up ? "+" : "";
  const color = up ? "var(--green)" : "var(--red)";

  return (
    <>
      <span className="font-mono" style={{ color: "var(--text-muted)", fontSize: 12 }}>
        {quote.price.toFixed(2)}
      </span>
      <span className="font-mono" style={{ color, fontSize: 11 }}>
        {sign}{quote.change_pct.toFixed(2)}%
      </span>
    </>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(true);
  const [quotesLoading, setQuotesLoading] = useState(false);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");

  // Add form
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("US");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Remove
  const [removingId, setRemovingId] = useState<string | null>(null);

  async function loadItems(market?: Market) {
    try {
      const data = await listWatchlist(market);
      setItems(data);
      return data;
    } finally {
      setLoading(false);
    }
  }

  async function fetchQuotes(itemList: WatchlistItem[]) {
    if (itemList.length === 0) return;
    setQuotesLoading(true);
    try {
      // Batch by market
      const usSymbols = itemList.filter((i) => i.market === "US").map((i) => i.symbol);
      const taseSymbols = itemList.filter((i) => i.market === "TASE").map((i) => i.symbol);

      const results: Quote[] = [];
      if (usSymbols.length > 0) {
        const q = await getQuotes(usSymbols, "US");
        results.push(...q);
      }
      if (taseSymbols.length > 0) {
        const q = await getQuotes(taseSymbols, "TASE");
        results.push(...q);
      }

      const map: Record<string, Quote> = {};
      results.forEach((q) => {
        map[q.symbol] = q;
      });
      setQuotes(map);
    } catch {
      // quotes are non-critical — silently ignore
    } finally {
      setQuotesLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    const mkt = filterMarket === "ALL" ? undefined : filterMarket;
    loadItems(mkt).then((data) => {
      if (data) fetchQuotes(data);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterMarket]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;

    setAdding(true);
    setAddError(null);
    try {
      const item = await addWatchlistItem(sym, market);
      const shouldShow = filterMarket === "ALL" || filterMarket === item.market;
      if (shouldShow) {
        const next = [item, ...items];
        setItems(next);
        // Refresh quote for new symbol
        const q = await getQuotes([item.symbol], item.market);
        if (q[0] && !q[0].error) {
          setQuotes((prev) => ({ ...prev, [item.symbol]: q[0] }));
        }
      }
      setSymbol("");
    } catch (err) {
      if (err instanceof ApiError) {
        setAddError(
          err.status === 409
            ? `${sym} (${market}) is already on your watchlist.`
            : typeof err.detail === "string"
              ? err.detail
              : "Failed to add symbol.",
        );
      } else {
        setAddError("Network error. Is the backend running?");
      }
    } finally {
      setAdding(false);
    }
  }

  async function handleRemove(id: string) {
    setRemovingId(id);
    try {
      await removeWatchlistItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } finally {
      setRemovingId(null);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "var(--text)" }}>
            Watchlist
          </h1>
          <p className="text-sm mt-0.5" style={{ color: "var(--text-dim)" }}>
            {items.length} symbol{items.length !== 1 ? "s" : ""} · scan universe
          </p>
        </div>

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
      </div>

      {/* Add form */}
      <div
        className="p-4"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "6px",
          boxShadow: "var(--shadow)",
        }}
      >
        <p className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-dim)" }}>
          Add Symbol
        </p>
        <form onSubmit={handleAdd} className="flex gap-2 items-end flex-wrap">
          <div className="flex-1 min-w-36 space-y-1">
            <label className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
              Ticker
            </label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              maxLength={20}
              className="w-full px-3 py-2 text-sm font-mono uppercase rounded-sm"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
              Market
            </label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as Market)}
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
          </div>

          <button
            type="submit"
            disabled={adding || !symbol.trim()}
            className="px-4 py-2 text-sm font-semibold transition-colors rounded-sm"
            style={{
              background: adding || !symbol.trim() ? "var(--surface-2)" : "var(--blue-dim)",
              border: "1px solid var(--blue)",
              color: adding || !symbol.trim() ? "var(--text-dim)" : "var(--blue)",
              cursor: adding || !symbol.trim() ? "not-allowed" : "pointer",
            }}
          >
            {adding ? "Adding…" : "+ Add"}
          </button>
        </form>

        {addError && (
          <p className="text-xs mt-2" style={{ color: "var(--red)" }}>
            {addError}
          </p>
        )}
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
          className="grid items-center px-4 py-2 text-xs font-semibold uppercase tracking-widest"
          style={{
            gridTemplateColumns: "40px 1fr 110px 32px",
            gap: "0 8px",
            borderBottom: "1px solid var(--border)",
            color: "var(--text-dim)",
          }}
        >
          <span />
          <span>Symbol</span>
          <span>Added</span>
          <span />
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton h-9 rounded" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              {filterMarket === "ALL"
                ? "Your watchlist is empty. Add symbols above to start scanning."
                : `No ${filterMarket} symbols on your watchlist.`}
            </p>
          </div>
        ) : (
          items.map((item) => (
            <div
              key={item.id}
              className="grid items-center px-4 py-1.5 transition-colors hover:bg-[var(--surface-2)]"
              style={{
                gridTemplateColumns: "40px 1fr 110px 32px",
                gap: "0 8px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              {/* Icon */}
              <div className="flex items-center justify-center">
                <SymbolIcon symbol={item.symbol} />
              </div>

              {/* Symbol + market + price all inline */}
              <div className="flex items-center gap-2 flex-wrap min-w-0">
                <span className="font-bold text-sm shrink-0" style={{ color: "var(--text)" }}>
                  {item.symbol}
                </span>
                <span
                  className="px-1.5 py-px font-semibold rounded shrink-0"
                  style={{
                    fontSize: 10,
                    background: item.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                    color: item.market === "US" ? "var(--blue)" : "var(--accent)",
                  }}
                >
                  {item.market}
                </span>
                <PriceInline quote={quotes[item.symbol]} loading={quotesLoading && !quotes[item.symbol]} />
              </div>

              {/* Added date */}
              <span style={{ color: "var(--text-dim)", fontSize: 11 }}>
                {formatDate(item.added_at)}
              </span>

              {/* Remove */}
              <button
                onClick={() => handleRemove(item.id)}
                disabled={removingId === item.id}
                style={{
                  fontSize: 11,
                  color: removingId === item.id ? "var(--text-dim)" : "var(--red)",
                  cursor: removingId === item.id ? "not-allowed" : "pointer",
                  background: "none",
                  border: "none",
                  padding: 0,
                }}
                aria-label={`Remove ${item.symbol}`}
              >
                {removingId === item.id ? "…" : "✕"}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
