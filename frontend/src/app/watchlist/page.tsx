"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  listWatchlists,
  createWatchlist,
  updateWatchlist,
  deleteWatchlist,
  listWatchlistItems,
  addWatchlistItem,
  removeWatchlistItem,
  moveWatchlistItem,
} from "@/lib/api/watchlist";
import { getQuotes, Quote } from "@/lib/api/market";
import { runScan } from "@/lib/api/scanner";
import type { Market, Watchlist, WatchlistItem } from "@/lib/types";
import { ApiError } from "@/lib/types";

// ── Symbol icon ───────────────────────────────────────────────────────────────

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

// ── Price inline ─────────────────────────────────────────────────────────────

function PriceInline({ quote, loading }: { quote?: Quote; loading: boolean }) {
  if (loading) return <span className="skeleton inline-block w-14 h-3 align-middle" />;
  if (!quote || quote.error) return null;
  const up = quote.change_pct >= 0;
  return (
    <>
      <span className="font-mono" style={{ color: "var(--text-muted)", fontSize: 12 }}>
        {quote.price.toFixed(2)}
      </span>
      <span className="font-mono" style={{ color: up ? "var(--green)" : "var(--red)", fontSize: 11 }}>
        {up ? "+" : ""}{quote.change_pct.toFixed(2)}%
      </span>
    </>
  );
}

// ── Market badge ─────────────────────────────────────────────────────────────

function MarketBadge({ market }: { market: Market }) {
  return (
    <span
      className="px-1.5 py-px font-semibold rounded shrink-0"
      style={{
        fontSize: 10,
        background: market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
        color: market === "US" ? "var(--blue)" : "var(--accent)",
      }}
    >
      {market}
    </span>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const router = useRouter();

  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

  const [listsLoading, setListsLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [quotesLoading, setQuotesLoading] = useState(false);

  // Create list form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Rename list
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const renameRef = useRef<HTMLInputElement>(null);

  // Delete list
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Add symbol form
  const [addSymbol, setAddSymbol] = useState("");
  const [addMarket, setAddMarket] = useState<Market>("US");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Remove item
  const [removingId, setRemovingId] = useState<string | null>(null);

  // Move item
  const [movingItemId, setMovingItemId] = useState<string | null>(null);

  // Scan
  const [scanning, setScanning] = useState(false);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  // ── Load watchlists on mount ───────────────────────────────────────────────

  useEffect(() => {
    loadLists();
  }, []);

  async function loadLists() {
    setListsLoading(true);
    try {
      const data = await listWatchlists();
      setWatchlists(data);
      if (data.length > 0) {
        const first = data[0].id;
        setActiveId(first);
        await loadItems(first, data);
      }
    } finally {
      setListsLoading(false);
    }
  }

  async function loadItems(watchlistId: string, lists?: Watchlist[]) {
    setItemsLoading(true);
    setItems([]);
    setQuotes({});
    try {
      const data = await listWatchlistItems(watchlistId);
      setItems(data);
      void fetchQuotes(data);
    } finally {
      setItemsLoading(false);
    }
  }

  async function fetchQuotes(itemList: WatchlistItem[]) {
    if (itemList.length === 0) return;
    setQuotesLoading(true);
    try {
      const usSymbols = itemList.filter((i) => i.market === "US").map((i) => i.symbol);
      const taseSymbols = itemList.filter((i) => i.market === "TASE").map((i) => i.symbol);
      const results: Quote[] = [];
      if (usSymbols.length) results.push(...await getQuotes(usSymbols, "US"));
      if (taseSymbols.length) results.push(...await getQuotes(taseSymbols, "TASE"));
      const map: Record<string, Quote> = {};
      results.forEach((q) => { map[q.symbol] = q; });
      setQuotes(map);
    } catch { /* non-critical */ }
    finally { setQuotesLoading(false); }
  }

  // ── Select a watchlist ────────────────────────────────────────────────────

  function selectList(id: string) {
    if (id === activeId) return;
    setActiveId(id);
    setScanMsg(null);
    setAddError(null);
    void loadItems(id);
  }

  // ── Create watchlist ──────────────────────────────────────────────────────

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setCreating(true);
    setCreateError(null);
    try {
      const wl = await createWatchlist(name, newDesc.trim() || undefined);
      setWatchlists((prev) => [...prev, { ...wl, item_count: 0, us_count: 0, tase_count: 0 }]);
      setNewName("");
      setNewDesc("");
      setShowCreate(false);
      setActiveId(wl.id);
      setItems([]);
      setQuotes({});
    } catch (err) {
      setCreateError(err instanceof ApiError ? String(err.detail) : "Failed to create list.");
    } finally {
      setCreating(false);
    }
  }

  // ── Rename watchlist ──────────────────────────────────────────────────────

  function startRename(wl: Watchlist) {
    setRenamingId(wl.id);
    setRenameValue(wl.name);
    setTimeout(() => renameRef.current?.focus(), 0);
  }

  async function commitRename(id: string) {
    const name = renameValue.trim();
    if (!name) { setRenamingId(null); return; }
    try {
      const updated = await updateWatchlist(id, { name });
      setWatchlists((prev) => prev.map((w) => w.id === id ? { ...w, name: updated.name } : w));
    } catch { /* ignore */ }
    setRenamingId(null);
  }

  // ── Delete watchlist ──────────────────────────────────────────────────────

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await deleteWatchlist(id);
      const next = watchlists.filter((w) => w.id !== id);
      setWatchlists(next);
      if (activeId === id) {
        const fallback = next[0]?.id ?? null;
        setActiveId(fallback);
        if (fallback) await loadItems(fallback);
        else { setItems([]); setQuotes({}); }
      }
    } catch (err) {
      alert(err instanceof ApiError ? String(err.detail) : "Failed to delete list.");
    } finally {
      setDeletingId(null);
    }
  }

  // ── Add symbol ────────────────────────────────────────────────────────────

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = addSymbol.trim().toUpperCase();
    if (!sym || !activeId) return;
    setAdding(true);
    setAddError(null);
    try {
      const item = await addWatchlistItem(sym, addMarket, activeId);
      setItems((prev) => [item, ...prev]);
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === activeId
            ? {
                ...w,
                item_count: w.item_count + 1,
                us_count: addMarket === "US" ? w.us_count + 1 : w.us_count,
                tase_count: addMarket === "TASE" ? w.tase_count + 1 : w.tase_count,
              }
            : w,
        ),
      );
      setAddSymbol("");
      const q = await getQuotes([item.symbol], item.market);
      if (q[0] && !q[0].error) setQuotes((prev) => ({ ...prev, [item.symbol]: q[0] }));
    } catch (err) {
      setAddError(
        err instanceof ApiError
          ? (err.status === 409
              ? `${sym} (${addMarket}) is already in this list.`
              : String(err.detail))
          : "Network error.",
      );
    } finally {
      setAdding(false);
    }
  }

  // ── Remove symbol ─────────────────────────────────────────────────────────

  async function handleRemove(item: WatchlistItem) {
    setRemovingId(item.id);
    try {
      await removeWatchlistItem(item.id);
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      setWatchlists((prev) =>
        prev.map((w) =>
          w.id === item.watchlist_id
            ? {
                ...w,
                item_count: w.item_count - 1,
                us_count: item.market === "US" ? w.us_count - 1 : w.us_count,
                tase_count: item.market === "TASE" ? w.tase_count - 1 : w.tase_count,
              }
            : w,
        ),
      );
    } finally {
      setRemovingId(null);
    }
  }

  // ── Move symbol to another list ───────────────────────────────────────────

  async function handleMove(item: WatchlistItem, targetId: string) {
    setMovingItemId(item.id);
    try {
      await moveWatchlistItem(item.id, targetId);
      // Remove from current view
      setItems((prev) => prev.filter((i) => i.id !== item.id));
      // Update counts
      setWatchlists((prev) =>
        prev.map((w) => {
          if (w.id === item.watchlist_id) {
            return {
              ...w,
              item_count: w.item_count - 1,
              us_count: item.market === "US" ? w.us_count - 1 : w.us_count,
              tase_count: item.market === "TASE" ? w.tase_count - 1 : w.tase_count,
            };
          }
          if (w.id === targetId) {
            return {
              ...w,
              item_count: w.item_count + 1,
              us_count: item.market === "US" ? w.us_count + 1 : w.us_count,
              tase_count: item.market === "TASE" ? w.tase_count + 1 : w.tase_count,
            };
          }
          return w;
        }),
      );
    } catch { /* ignore */ }
    finally { setMovingItemId(null); }
  }

  // ── Scan this list ────────────────────────────────────────────────────────

  async function handleScan() {
    if (!activeId || scanning) return;
    const markets = [...new Set(items.map((i) => i.market))] as Market[];
    if (markets.length === 0) return;
    setScanning(true);
    setScanMsg(null);
    try {
      let totalCandidates = 0;
      for (const mkt of markets) {
        const result = await runScan({ market: mkt, watchlist_id: activeId });
        totalCandidates += result.total_passed;
      }
      setScanMsg(`Scan complete — ${totalCandidates} candidate${totalCandidates !== 1 ? "s" : ""} found.`);
      setTimeout(() => router.push("/candidates"), 1200);
    } catch (err) {
      setScanMsg(err instanceof ApiError ? String(err.detail) : "Scan failed.");
    } finally {
      setScanning(false);
    }
  }

  // ── Derived ───────────────────────────────────────────────────────────────

  const activeList = watchlists.find((w) => w.id === activeId) ?? null;
  const otherLists = watchlists.filter((w) => w.id !== activeId);
  const canDelete = watchlists.length > 1;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex gap-0 min-h-[60vh]" style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden", boxShadow: "var(--shadow)" }}>

      {/* ── Left sidebar: list of watchlists ─────────────────────────────── */}
      <div
        className="flex flex-col"
        style={{
          width: 220,
          minWidth: 180,
          flexShrink: 0,
          borderRight: "1px solid var(--border)",
          background: "var(--surface)",
        }}
      >
        {/* Sidebar header */}
        <div
          className="flex items-center justify-between px-3 py-2.5"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
        >
          <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            Lists
          </span>
          <button
            onClick={() => { setShowCreate(true); setCreateError(null); }}
            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--accent)", fontSize: 18, lineHeight: 1, padding: "0 2px" }}
            title="New watchlist"
          >
            +
          </button>
        </div>

        {/* List items */}
        <div className="flex-1 overflow-y-auto">
          {listsLoading ? (
            <div className="p-3 space-y-2">
              {Array.from({ length: 3 }).map((_, i) => <div key={i} className="skeleton h-8 rounded" />)}
            </div>
          ) : watchlists.length === 0 ? (
            <p className="p-3 text-xs" style={{ color: "var(--text-dim)" }}>No lists yet.</p>
          ) : (
            watchlists.map((wl) => (
              <div
                key={wl.id}
                onClick={() => selectList(wl.id)}
                className="group flex items-center justify-between px-3 py-2 cursor-pointer transition-colors"
                style={{
                  background: activeId === wl.id ? "var(--surface-2)" : "transparent",
                  borderLeft: activeId === wl.id ? "2px solid var(--accent)" : "2px solid transparent",
                }}
              >
                {/* Name / rename input */}
                <div className="flex-1 min-w-0 mr-1">
                  {renamingId === wl.id ? (
                    <input
                      ref={renameRef}
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onBlur={() => commitRename(wl.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename(wl.id);
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full px-1 text-sm font-medium rounded"
                      style={{
                        background: "var(--surface)",
                        border: "1px solid var(--accent)",
                        color: "var(--text)",
                        outline: "none",
                      }}
                    />
                  ) : (
                    <div>
                      <p className="text-sm font-medium truncate" style={{ color: activeId === wl.id ? "var(--text)" : "var(--text-muted)" }}>
                        {wl.name}
                      </p>
                      <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                        {wl.item_count} symbol{wl.item_count !== 1 ? "s" : ""}
                        {wl.us_count > 0 && wl.tase_count > 0 && ` · ${wl.us_count}US ${wl.tase_count}IL`}
                      </p>
                    </div>
                  )}
                </div>

                {/* Actions (visible on hover) */}
                {renamingId !== wl.id && (
                  <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    <button
                      onClick={(e) => { e.stopPropagation(); startRename(wl); }}
                      style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-dim)", fontSize: 11, padding: "1px 3px" }}
                      title="Rename"
                    >
                      ✎
                    </button>
                    {canDelete && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDelete(wl.id); }}
                        disabled={deletingId === wl.id}
                        style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", fontSize: 11, padding: "1px 3px" }}
                        title="Delete list"
                      >
                        {deletingId === wl.id ? "…" : "✕"}
                      </button>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Create list form (inline) */}
        {showCreate && (
          <div
            className="p-3 space-y-2"
            style={{ borderTop: "1px solid var(--border)", background: "var(--surface-2)" }}
          >
            <form onSubmit={handleCreate} className="space-y-2">
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="List name"
                maxLength={80}
                className="w-full px-2 py-1.5 text-sm rounded"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                }}
              />
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Description (optional)"
                maxLength={200}
                className="w-full px-2 py-1.5 text-xs rounded"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  color: "var(--text-muted)",
                }}
              />
              {createError && <p className="text-xs" style={{ color: "var(--red)" }}>{createError}</p>}
              <div className="flex gap-1.5">
                <button
                  type="submit"
                  disabled={creating || !newName.trim()}
                  className="flex-1 py-1.5 text-xs font-semibold rounded"
                  style={{
                    background: "var(--accent-dim)",
                    border: "1px solid var(--accent)",
                    color: "var(--accent)",
                    cursor: creating || !newName.trim() ? "not-allowed" : "pointer",
                  }}
                >
                  {creating ? "Creating…" : "Create"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCreate(false); setNewName(""); setNewDesc(""); }}
                  className="px-3 py-1.5 text-xs rounded"
                  style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text-dim)", cursor: "pointer" }}
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {/* ── Right panel: items in active list ────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0" style={{ background: "var(--surface)" }}>

        {/* Panel header */}
        <div
          className="flex items-center justify-between px-4 py-2.5 flex-wrap gap-2"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}
        >
          <div>
            <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
              {activeList?.name ?? "Select a list"}
            </h2>
            {activeList?.description && (
              <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>{activeList.description}</p>
            )}
          </div>

          {/* Scan this list */}
          {activeList && items.length > 0 && (
            <div className="flex items-center gap-2">
              {scanMsg && (
                <span className="text-xs font-mono" style={{ color: scanning ? "var(--text-dim)" : "var(--green)" }}>
                  {scanMsg}
                </span>
              )}
              <button
                onClick={handleScan}
                disabled={scanning}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition-colors"
                style={{
                  background: scanning ? "var(--surface)" : "var(--accent-dim)",
                  border: "1px solid var(--accent)",
                  borderRadius: 3,
                  color: scanning ? "var(--text-dim)" : "var(--accent)",
                  cursor: scanning ? "not-allowed" : "pointer",
                }}
              >
                {scanning ? (
                  "Scanning…"
                ) : (
                  <>
                    <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <circle cx="5" cy="5" r="4" /><path d="M8.5 8.5L11 11" />
                    </svg>
                    Scan this list
                  </>
                )}
              </button>
            </div>
          )}
        </div>

        {/* Add symbol form */}
        {activeList && (
          <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            <form onSubmit={handleAdd} className="flex gap-2 items-center flex-wrap">
              <input
                value={addSymbol}
                onChange={(e) => setAddSymbol(e.target.value.toUpperCase())}
                placeholder="Ticker, e.g. AAPL"
                maxLength={20}
                className="px-3 py-1.5 text-sm font-mono uppercase rounded-sm"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  color: "var(--text)",
                  width: 140,
                }}
              />
              <select
                value={addMarket}
                onChange={(e) => setAddMarket(e.target.value as Market)}
                className="px-2 py-1.5 text-sm rounded-sm"
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
                disabled={adding || !addSymbol.trim()}
                className="px-3 py-1.5 text-sm font-semibold rounded-sm transition-colors"
                style={{
                  background: adding || !addSymbol.trim() ? "var(--surface-2)" : "var(--blue-dim)",
                  border: "1px solid var(--blue)",
                  color: adding || !addSymbol.trim() ? "var(--text-dim)" : "var(--blue)",
                  cursor: adding || !addSymbol.trim() ? "not-allowed" : "pointer",
                }}
              >
                {adding ? "Adding…" : "+ Add"}
              </button>
              {addError && <span className="text-xs" style={{ color: "var(--red)" }}>{addError}</span>}
            </form>
          </div>
        )}

        {/* Items table */}
        <div className="flex-1 overflow-y-auto">
          {!activeList ? (
            <div className="px-4 py-12 text-center">
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>Select a list from the sidebar, or create a new one.</p>
            </div>
          ) : itemsLoading ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton h-9 rounded" />)}
            </div>
          ) : items.length === 0 ? (
            <div className="px-4 py-12 text-center">
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                This list is empty. Add symbols above to start scanning.
              </p>
            </div>
          ) : (
            <>
              {/* Column headers */}
              <div
                className="grid items-center px-4 py-1.5 text-xs font-semibold uppercase tracking-widest"
                style={{
                  gridTemplateColumns: "36px 1fr 90px 32px",
                  gap: "0 8px",
                  borderBottom: "1px solid var(--border-subtle)",
                  color: "var(--text-dim)",
                }}
              >
                <span />
                <span>Symbol</span>
                <span>Added</span>
                <span />
              </div>

              {items.map((item) => (
                <div
                  key={item.id}
                  className="group grid items-center px-4 py-1.5 transition-colors hover:bg-[var(--surface-2)]"
                  style={{
                    gridTemplateColumns: "36px 1fr 90px 32px",
                    gap: "0 8px",
                    borderBottom: "1px solid var(--border-subtle)",
                  }}
                >
                  {/* Icon */}
                  <div className="flex items-center justify-center">
                    <SymbolIcon symbol={item.symbol} />
                  </div>

                  {/* Symbol + market + price */}
                  <div className="flex items-center gap-2 flex-wrap min-w-0">
                    <span className="font-bold text-sm shrink-0" style={{ color: "var(--text)" }}>
                      {item.symbol}
                    </span>
                    <MarketBadge market={item.market as Market} />
                    <PriceInline quote={quotes[item.symbol]} loading={quotesLoading && !quotes[item.symbol]} />

                    {/* Move to list — shown on hover */}
                    {otherLists.length > 0 && (
                      <div className="relative opacity-0 group-hover:opacity-100 transition-opacity">
                        <select
                          value=""
                          disabled={movingItemId === item.id}
                          onChange={(e) => {
                            if (e.target.value) handleMove(item, e.target.value);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="text-xs px-1.5 py-0.5 rounded cursor-pointer"
                          style={{
                            background: "var(--surface)",
                            border: "1px solid var(--border)",
                            color: "var(--text-dim)",
                            maxWidth: 100,
                          }}
                          title="Move to list"
                        >
                          <option value="">Move →</option>
                          {otherLists.map((wl) => (
                            <option key={wl.id} value={wl.id}>{wl.name}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>

                  {/* Date added */}
                  <span style={{ color: "var(--text-dim)", fontSize: 11 }}>
                    {new Date(item.added_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>

                  {/* Remove */}
                  <button
                    onClick={() => handleRemove(item)}
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
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
