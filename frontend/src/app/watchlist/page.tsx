"use client";

import { useEffect, useState } from "react";
import { listWatchlist, addWatchlistItem, removeWatchlistItem } from "@/lib/api/watchlist";
import type { Market, WatchlistItem } from "@/lib/types";
import { ApiError } from "@/lib/types";

function MarketBadge({ market }: { market: Market }) {
  return (
    <span
      className="px-1.5 py-0.5 text-xs font-mono rounded"
      style={{
        background: market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
        color: market === "US" ? "#93c5fd" : "var(--accent)",
      }}
    >
      {market}
    </span>
  );
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");

  // Add form
  const [symbol, setSymbol] = useState("");
  const [market, setMarket] = useState<Market>("US");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Removing
  const [removingId, setRemovingId] = useState<string | null>(null);

  async function loadItems() {
    try {
      const data = await listWatchlist(filterMarket === "ALL" ? undefined : filterMarket);
      setItems(data);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setLoading(true);
    loadItems();
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
      setItems((prev) =>
        filterMarket === "ALL" || filterMarket === item.market ? [item, ...prev] : prev,
      );
      setSymbol("");
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = err.detail;
        setAddError(
          typeof detail === "string"
            ? detail
            : err.status === 409
              ? `${sym} (${market}) is already on your watchlist.`
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
    } catch {
      // silently ignore for now
    } finally {
      setRemovingId(null);
    }
  }

  const filtered = items; // already filtered by API

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-start justify-between">
        <div>
          <h1
            className="font-mono text-xl font-semibold tracking-wide"
            style={{ color: "var(--text)" }}
          >
            Watchlist
          </h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-dim)" }}>
            Symbols in your scan universe — {items.length} item{items.length !== 1 ? "s" : ""}
          </p>
        </div>

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
      </div>

      {/* Add form */}
      <div
        className="p-4"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
        }}
      >
        <p
          className="text-xs font-mono uppercase tracking-widest mb-3"
          style={{ color: "var(--text-dim)" }}
        >
          Add Symbol
        </p>
        <form onSubmit={handleAdd} className="flex gap-2 items-end flex-wrap">
          <div className="flex-1 min-w-40 space-y-1">
            <label className="text-xs" style={{ color: "var(--text-muted)" }}>
              Ticker
            </label>
            <input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="AAPL"
              maxLength={20}
              className="w-full px-3 py-2 text-sm font-mono uppercase"
              style={{
                background: "var(--surface-2)",
                border: "1px solid var(--border)",
                borderRadius: "2px",
                color: "var(--text)",
              }}
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs" style={{ color: "var(--text-muted)" }}>
              Market
            </label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as Market)}
              className="px-3 py-2 text-sm font-mono"
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
          </div>

          <button
            type="submit"
            disabled={adding || !symbol.trim()}
            className="px-4 py-2 text-xs font-mono font-semibold uppercase tracking-wide transition-colors"
            style={{
              background: adding || !symbol.trim() ? "var(--surface-2)" : "var(--blue-dim)",
              border: "1px solid var(--blue)",
              borderRadius: "2px",
              color: adding || !symbol.trim() ? "var(--text-dim)" : "#93c5fd",
              cursor: adding || !symbol.trim() ? "not-allowed" : "pointer",
            }}
          >
            {adding ? "Adding…" : "+ Add"}
          </button>
        </form>

        {addError && (
          <p className="text-xs mt-2" style={{ color: "#fca5a5" }}>
            {addError}
          </p>
        )}
      </div>

      {/* Items table */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "4px",
          overflow: "hidden",
        }}
      >
        {/* Table header */}
        <div
          className="grid grid-cols-[1fr_80px_120px_40px] px-4 py-2 text-xs font-mono uppercase tracking-widest"
          style={{
            borderBottom: "1px solid var(--border)",
            color: "var(--text-dim)",
          }}
        >
          <span>Symbol</span>
          <span>Market</span>
          <span>Added</span>
          <span />
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="skeleton h-10 rounded" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-10 text-center">
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              {filterMarket === "ALL"
                ? "Your watchlist is empty. Add symbols to start scanning."
                : `No ${filterMarket} symbols on your watchlist.`}
            </p>
          </div>
        ) : (
          filtered.map((item) => (
            <div
              key={item.id}
              className="grid grid-cols-[1fr_80px_120px_40px] items-center px-4 py-3 hover:bg-zinc-800 transition-colors"
              style={{ borderBottom: "1px solid var(--border-subtle)" }}
            >
              <span className="font-mono text-sm font-semibold" style={{ color: "var(--text)" }}>
                {item.symbol}
              </span>
              <MarketBadge market={item.market} />
              <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
                {formatDate(item.added_at)}
              </span>
              <button
                onClick={() => handleRemove(item.id)}
                disabled={removingId === item.id}
                className="text-xs font-mono transition-colors"
                style={{
                  color: removingId === item.id ? "var(--text-dim)" : "var(--red)",
                  cursor: removingId === item.id ? "not-allowed" : "pointer",
                  background: "none",
                  border: "none",
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
