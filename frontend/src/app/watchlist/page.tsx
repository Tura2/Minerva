"use client";

import dynamic from "next/dynamic";
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
import { getHistory, getQuotes, Quote } from "@/lib/api/market";
import { runScan } from "@/lib/api/scanner";
import type { Candle, Market, Watchlist, WatchlistItem } from "@/lib/types";
import { ApiError } from "@/lib/types";
import ResearchModal from "@/components/ResearchModal";

const CandlestickChart = dynamic(() => import("@/components/CandlestickChart"), {
  ssr: false,
  loading: () => <div className="skeleton" style={{ flex: 1, minHeight: 300 }} />,
});

// ── Symbol icon ────────────────────────────────────────────────────────────────

const SYMBOL_COLORS = [
  "#3b82f6", "#8b5cf6", "#57c1d5", "#10b981", "#06b6d4",
  "#6366f1", "#14b8a6", "#0ea5e9", "#22d3ee", "#a78bfa",
];
function symbolColor(s: string) {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = s.charCodeAt(i) + ((h << 5) - h);
  return SYMBOL_COLORS[Math.abs(h) % SYMBOL_COLORS.length];
}
function SymbolIcon({ symbol, size = 26 }: { symbol: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  if (failed) return (
    <span className="inline-flex items-center justify-center shrink-0 rounded-full font-bold"
      style={{ width: size, height: size, background: symbolColor(symbol), color: "#fff", fontSize: size * 0.38 }}>
      {symbol.slice(0, 2)}
    </span>
  );
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={`https://cdn.jsdelivr.net/gh/nvstly/icons@main/ticker_icons/${symbol}.png`}
      alt={symbol} width={size} height={size}
      className="rounded-full shrink-0 object-cover" onError={() => setFailed(true)} />
  );
}

// ── Price display ──────────────────────────────────────────────────────────────
function PriceDisplay({ quote, loading, size = "sm" }: { quote?: Quote; loading: boolean; size?: "sm" | "lg" }) {
  if (loading) return (
    <div className="flex flex-col items-end gap-1">
      <div className="skeleton rounded" style={{ width: 56, height: size === "lg" ? 20 : 14 }} />
      <div className="skeleton rounded" style={{ width: 40, height: 11 }} />
    </div>
  );
  if (!quote || quote.error) return <span className="font-mono text-xs" style={{ color: "var(--text-dim)" }}>—</span>;
  const up = quote.change_pct >= 0;
  return (
    <div className="flex flex-col items-end">
      <span className={`font-mono font-semibold ${size === "lg" ? "text-xl" : "text-sm"}`} style={{ color: "var(--text)" }}>
        {quote.price.toFixed(2)}
      </span>
      <span className="font-mono text-xs px-1 rounded"
        style={{ background: up ? "var(--green-dim)" : "var(--red-dim)", color: up ? "var(--green)" : "var(--red)" }}>
        {up ? "+" : ""}{quote.change_pct.toFixed(2)}%
      </span>
    </div>
  );
}

// ── Market badge ──────────────────────────────────────────────────────────────
function MarketBadge({ market }: { market: string }) {
  return (
    <span className="px-1.5 py-px font-semibold rounded shrink-0"
      style={{ fontSize: 10, background: market === "US" ? "var(--blue-dim)" : "var(--accent-dim)", color: market === "US" ? "var(--blue)" : "var(--accent)" }}>
      {market}
    </span>
  );
}

// ── Drawing toolbar ───────────────────────────────────────────────────────────
type DrawingMode = "cursor" | "hline";

function DrawingToolbar({
  mode, hlineCount, onMode, onClear,
}: { mode: DrawingMode; hlineCount: number; onMode: (m: DrawingMode) => void; onClear: () => void }) {
  const btn = (m: DrawingMode, label: React.ReactNode, title: string) => (
    <button
      key={String(m)}
      onClick={() => onMode(m)}
      title={title}
      className="flex items-center justify-center transition-colors"
      style={{
        width: 28, height: 28, borderRadius: 3,
        background: mode === m ? "var(--accent-dim)" : "transparent",
        border: `1px solid ${mode === m ? "var(--accent)" : "var(--border)"}`,
        color: mode === m ? "var(--accent)" : "var(--text-dim)",
        cursor: "pointer",
        fontSize: 13,
      }}
    >{label}</button>
  );

  return (
    <div className="flex items-center gap-1.5 px-3 py-2" style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)" }}>
      <span className="text-xs uppercase tracking-widest mr-1" style={{ color: "var(--text-dim)", fontSize: 9 }}>Draw</span>
      {btn("cursor",
        <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor"><path d="M4 1l11 7-5.5 1.5L8 15 4 1z"/></svg>,
        "Select / Pan"
      )}
      {btn("hline",
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2"><line x1="1" y1="8" x2="15" y2="8"/><circle cx="8" cy="8" r="2" fill="currentColor"/></svg>,
        "Horizontal line — click on chart to place"
      )}
      {hlineCount > 0 && (
        <button
          onClick={onClear}
          title="Clear all drawings"
          className="flex items-center gap-1 px-2 transition-colors"
          style={{ height: 28, borderRadius: 3, background: "transparent", border: "1px solid var(--border)", color: "var(--red)", cursor: "pointer", fontSize: 11, whiteSpace: "nowrap" }}
        >
          <svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2"><line x1="1" y1="1" x2="11" y2="11"/><line x1="11" y1="1" x2="1" y2="11"/></svg>
          Clear ({hlineCount})
        </button>
      )}
      {mode === "hline" && (
        <span className="text-xs ml-1" style={{ color: "var(--accent)", fontSize: 10 }}>
          Click chart to place line
        </span>
      )}
    </div>
  );
}

// ── Main page ──────────────────────────────────────────────────────────────────
export default function WatchlistPage() {
  const router = useRouter();

  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

  const [listsLoading, setListsLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [quotesLoading, setQuotesLoading] = useState(false);

  // Chart
  const [selectedItem, setSelectedItem] = useState<WatchlistItem | null>(null);
  const [chartCandles, setChartCandles] = useState<Candle[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const [chartHeight, setChartHeight] = useState(400);

  // Drawing
  const [drawingMode, setDrawingMode] = useState<DrawingMode>("cursor");
  const [hlines, setHlines] = useState<number[]>([]);

  // Research modal
  const [researchTarget, setResearchTarget] = useState<{ symbol: string; market: Market } | null>(null);

  // Watchlist dropdown
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Create form (in dropdown)
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Rename
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  // Add symbol
  const [addSymbol, setAddSymbol] = useState("");
  const [addMarket, setAddMarket] = useState<Market>("US");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Remove / move
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [movingItemId, setMovingItemId] = useState<string | null>(null);

  // Scan
  const [scanning, setScanning] = useState(false);
  const [quickScanningId, setQuickScanningId] = useState<string | null>(null);
  const [scanMsg, setScanMsg] = useState<string | null>(null);

  // ── Chart container height ─────────────────────────────────────────────────
  useEffect(() => {
    if (!chartContainerRef.current) return;
    const obs = new ResizeObserver(() => {
      if (chartContainerRef.current) setChartHeight(chartContainerRef.current.clientHeight);
    });
    obs.observe(chartContainerRef.current);
    return () => obs.disconnect();
  }, []);

  // ── Close dropdown on outside click ───────────────────────────────────────
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Load on mount ──────────────────────────────────────────────────────────
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { loadLists(); }, []);

  async function loadLists() {
    setListsLoading(true);
    try {
      const data = await listWatchlists();
      setWatchlists(data);
      if (data.length > 0) {
        setActiveId(data[0].id);
        await loadItems(data[0].id, true);
      }
    } finally {
      setListsLoading(false);
    }
  }

  async function loadItems(watchlistId: string, autoSelect = false) {
    setItemsLoading(true);
    setItems([]);
    setQuotes({});
    if (autoSelect) { setSelectedItem(null); setChartCandles([]); }
    try {
      const data = await listWatchlistItems(watchlistId);
      setItems(data);
      void fetchQuotes(data);
      if (autoSelect && data.length > 0) void selectSymbol(data[0]);
    } finally {
      setItemsLoading(false);
    }
  }

  async function fetchQuotes(itemList: WatchlistItem[]) {
    if (itemList.length === 0) return;
    setQuotesLoading(true);
    try {
      const usSyms = itemList.filter(i => i.market === "US").map(i => i.symbol);
      const taseSyms = itemList.filter(i => i.market === "TASE").map(i => i.symbol);
      const results: Quote[] = [];
      if (usSyms.length) results.push(...await getQuotes(usSyms, "US"));
      if (taseSyms.length) results.push(...await getQuotes(taseSyms, "TASE"));
      const map: Record<string, Quote> = {};
      results.forEach(q => { map[q.symbol] = q; });
      setQuotes(map);
    } catch { /* non-critical */ }
    finally { setQuotesLoading(false); }
  }

  async function selectSymbol(item: WatchlistItem) {
    setSelectedItem(item);
    setChartCandles([]);
    setHlines([]);
    setDrawingMode("cursor");
    setChartLoading(true);
    try {
      const h = await getHistory({ symbol: item.symbol, market: item.market, period: "6mo" });
      setChartCandles(h.candles);
    } catch { /* ignore */ }
    finally { setChartLoading(false); }
  }

  // ── Watchlist CRUD ─────────────────────────────────────────────────────────

  async function switchList(id: string) {
    if (id === activeId) { setDropdownOpen(false); return; }
    setActiveId(id);
    setDropdownOpen(false);
    setScanMsg(null);
    void loadItems(id, true);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    setCreating(true); setCreateError(null);
    try {
      const wl = await createWatchlist(name);
      setWatchlists(prev => [...prev, { ...wl, item_count: 0, us_count: 0, tase_count: 0 }]);
      setNewName(""); setShowCreate(false);
      await switchList(wl.id);
    } catch (err) {
      setCreateError(err instanceof ApiError ? String(err.detail) : "Failed.");
    } finally { setCreating(false); }
  }

  async function commitRename(id: string) {
    const name = renameValue.trim();
    if (!name) { setRenamingId(null); return; }
    try {
      const updated = await updateWatchlist(id, { name });
      setWatchlists(prev => prev.map(w => w.id === id ? { ...w, name: updated.name } : w));
    } catch { /* ignore */ }
    setRenamingId(null);
  }

  async function handleDelete(id: string) {
    try {
      await deleteWatchlist(id);
      const next = watchlists.filter(w => w.id !== id);
      setWatchlists(next);
      if (activeId === id) {
        const fallback = next[0]?.id ?? null;
        setActiveId(fallback);
        if (fallback) await loadItems(fallback, true);
        else { setItems([]); setQuotes({}); setSelectedItem(null); setChartCandles([]); }
      }
    } catch (err) {
      alert(err instanceof ApiError ? String(err.detail) : "Failed to delete.");
    }
  }

  // ── Symbol CRUD ────────────────────────────────────────────────────────────

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const sym = addSymbol.trim().toUpperCase();
    if (!sym || !activeId) return;
    setAdding(true); setAddError(null);
    try {
      const item = await addWatchlistItem(sym, addMarket, activeId);
      setItems(prev => [item, ...prev]);
      setWatchlists(prev => prev.map(w => w.id === activeId
        ? { ...w, item_count: w.item_count + 1, us_count: addMarket === "US" ? w.us_count + 1 : w.us_count, tase_count: addMarket === "TASE" ? w.tase_count + 1 : w.tase_count }
        : w));
      setAddSymbol("");
      const q = await getQuotes([item.symbol], item.market);
      if (q[0] && !q[0].error) setQuotes(prev => ({ ...prev, [item.symbol]: q[0] }));
    } catch (err) {
      setAddError(err instanceof ApiError
        ? (err.status === 409 ? `${sym} already in list.` : String(err.detail))
        : "Network error.");
    } finally { setAdding(false); }
  }

  async function handleRemove(item: WatchlistItem) {
    setRemovingId(item.id);
    try {
      await removeWatchlistItem(item.id);
      setItems(prev => prev.filter(i => i.id !== item.id));
      setWatchlists(prev => prev.map(w => w.id === item.watchlist_id
        ? { ...w, item_count: w.item_count - 1, us_count: item.market === "US" ? w.us_count - 1 : w.us_count, tase_count: item.market === "TASE" ? w.tase_count - 1 : w.tase_count }
        : w));
      if (selectedItem?.id === item.id) { setSelectedItem(null); setChartCandles([]); setHlines([]); }
    } finally { setRemovingId(null); }
  }

  async function handleMove(item: WatchlistItem, targetId: string) {
    setMovingItemId(item.id);
    try {
      await moveWatchlistItem(item.id, targetId);
      setItems(prev => prev.filter(i => i.id !== item.id));
      setWatchlists(prev => prev.map(w => {
        if (w.id === item.watchlist_id) return { ...w, item_count: w.item_count - 1, us_count: item.market === "US" ? w.us_count - 1 : w.us_count, tase_count: item.market === "TASE" ? w.tase_count - 1 : w.tase_count };
        if (w.id === targetId) return { ...w, item_count: w.item_count + 1, us_count: item.market === "US" ? w.us_count + 1 : w.us_count, tase_count: item.market === "TASE" ? w.tase_count + 1 : w.tase_count };
        return w;
      }));
    } catch { /* ignore */ }
    finally { setMovingItemId(null); }
  }

  // ── Scan ───────────────────────────────────────────────────────────────────

  async function handleQuickScan(item: WatchlistItem) {
    setQuickScanningId(item.id);
    setScanMsg(null);
    try {
      const result = await runScan({ market: item.market, symbols: [item.symbol], limit: 1 });
      if (result.total_passed > 0) {
        setScanMsg(`${item.symbol} passed!`);
        setTimeout(() => router.push("/candidates"), 900);
      } else {
        setScanMsg(`${item.symbol} did not pass.`);
      }
    } catch { setScanMsg("Scan failed."); }
    finally { setQuickScanningId(null); }
  }

  async function handleScanList() {
    if (!activeId || scanning) return;
    const markets = [...new Set(items.map(i => i.market))] as Market[];
    if (!markets.length) return;
    setScanning(true); setScanMsg(null);
    try {
      let total = 0;
      for (const mkt of markets) {
        const result = await runScan({ market: mkt, watchlist_id: activeId });
        total += result.total_passed;
      }
      setScanMsg(`${total} candidate${total !== 1 ? "s" : ""} found`);
      setTimeout(() => router.push("/candidates"), 1200);
    } catch (err) {
      setScanMsg(err instanceof ApiError ? String(err.detail) : "Scan failed.");
    } finally { setScanning(false); }
  }

  // ── Derived ────────────────────────────────────────────────────────────────
  const activeList = watchlists.find(w => w.id === activeId) ?? null;
  const otherLists = watchlists.filter(w => w.id !== activeId);
  const canDelete = watchlists.length > 1;
  const selectedQuote = selectedItem ? quotes[selectedItem.symbol] : undefined;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <>
      {researchTarget && (
        <ResearchModal
          symbol={researchTarget.symbol}
          market={researchTarget.market}
          onClose={() => setResearchTarget(null)}
        />
      )}

      <div
        className="flex flex-col"
        style={{
          height: "calc(100vh - 80px)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          overflow: "hidden",
          background: "var(--surface)",
        }}
      >
        {/* ── TOP BAR ──────────────────────────────────────────────────── */}
        <div
          className="flex items-center gap-2 px-3 py-2 shrink-0 flex-wrap"
          style={{ borderBottom: "1px solid var(--border)", background: "var(--surface-2)", minHeight: 48 }}
        >
          {/* Watchlist dropdown */}
          <div ref={dropdownRef} className="relative">
            <button
              onClick={() => setDropdownOpen(p => !p)}
              className="flex items-center gap-2 px-3 py-1.5 text-sm font-semibold rounded transition-colors"
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                color: "var(--text)",
                cursor: "pointer",
                minWidth: 140,
              }}
            >
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M2 4h12M4 8h8M6 12h4" />
              </svg>
              <span className="truncate flex-1 text-left">
                {listsLoading ? "Loading…" : (activeList?.name ?? "Select list")}
              </span>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" style={{ opacity: 0.5 }}>
                <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.5" fill="none" />
              </svg>
            </button>

            {dropdownOpen && (
              <div
                className="absolute left-0 top-full mt-1 z-50 py-1"
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: 6,
                  boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
                  minWidth: 200,
                }}
              >
                {watchlists.map(wl => (
                  <div
                    key={wl.id}
                    className="group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors hover:bg-[var(--surface-2)]"
                    onClick={() => switchList(wl.id)}
                    style={{ borderLeft: wl.id === activeId ? "2px solid var(--accent)" : "2px solid transparent" }}
                  >
                    {renamingId === wl.id ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={e => setRenameValue(e.target.value)}
                        onBlur={() => commitRename(wl.id)}
                        onKeyDown={e => { if (e.key === "Enter") commitRename(wl.id); if (e.key === "Escape") setRenamingId(null); }}
                        onClick={e => e.stopPropagation()}
                        className="flex-1 px-1 text-sm rounded"
                        style={{ background: "var(--surface-2)", border: "1px solid var(--accent)", color: "var(--text)", outline: "none" }}
                      />
                    ) : (
                      <>
                        <span className="flex-1 text-sm font-medium truncate" style={{ color: wl.id === activeId ? "var(--text)" : "var(--text-muted)" }}>
                          {wl.name}
                        </span>
                        <span className="text-xs shrink-0" style={{ color: "var(--text-dim)" }}>{wl.item_count}</span>
                        <div className="flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                          <button
                            onClick={e => { e.stopPropagation(); setRenamingId(wl.id); setRenameValue(wl.name); }}
                            style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-dim)", fontSize: 11, padding: "1px 3px" }}
                          >✎</button>
                          {canDelete && (
                            <button
                              onClick={e => { e.stopPropagation(); handleDelete(wl.id); setDropdownOpen(false); }}
                              style={{ background: "none", border: "none", cursor: "pointer", color: "var(--red)", fontSize: 11, padding: "1px 3px" }}
                            >✕</button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}

                <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 4 }}>
                  {showCreate ? (
                    <form onSubmit={handleCreate} className="px-3 py-2 space-y-2">
                      <input
                        autoFocus
                        value={newName}
                        onChange={e => setNewName(e.target.value)}
                        placeholder="New list name"
                        maxLength={80}
                        className="w-full px-2 py-1.5 text-sm rounded"
                        style={{ background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)" }}
                      />
                      {createError && <p className="text-xs" style={{ color: "var(--red)" }}>{createError}</p>}
                      <div className="flex gap-1.5">
                        <button type="submit" disabled={creating || !newName.trim()} className="flex-1 py-1 text-xs font-semibold rounded"
                          style={{ background: "var(--accent-dim)", border: "1px solid var(--accent)", color: "var(--accent)", cursor: "pointer" }}>
                          {creating ? "…" : "Create"}
                        </button>
                        <button type="button" onClick={() => setShowCreate(false)} className="px-3 py-1 text-xs rounded"
                          style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text-dim)", cursor: "pointer" }}>
                          ✕
                        </button>
                      </div>
                    </form>
                  ) : (
                    <button
                      onClick={e => { e.stopPropagation(); setShowCreate(true); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-[var(--surface-2)]"
                      style={{ background: "none", border: "none", color: "var(--accent)", cursor: "pointer", textAlign: "left" }}
                    >
                      <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> New list
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Divider */}
          <div style={{ width: 1, height: 24, background: "var(--border)" }} />

          {/* Add symbol inline form */}
          {activeList && (
            <form onSubmit={handleAdd} className="flex gap-1.5 items-center">
              <input
                value={addSymbol}
                onChange={e => setAddSymbol(e.target.value.toUpperCase())}
                placeholder="Add ticker…"
                maxLength={20}
                className="px-2 py-1.5 text-xs font-mono uppercase rounded-sm"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", width: 110 }}
              />
              <select
                value={addMarket}
                onChange={e => setAddMarket(e.target.value as Market)}
                className="px-1.5 py-1.5 text-xs rounded-sm"
                style={{ background: "var(--surface)", border: "1px solid var(--border)", color: "var(--text)", cursor: "pointer" }}
              >
                <option value="US">US</option>
                <option value="TASE">IL</option>
              </select>
              <button
                type="submit"
                disabled={adding || !addSymbol.trim()}
                className="px-2.5 py-1.5 text-xs font-semibold rounded-sm"
                style={{
                  background: adding || !addSymbol.trim() ? "transparent" : "var(--blue-dim)",
                  border: "1px solid var(--blue)",
                  color: adding || !addSymbol.trim() ? "var(--text-dim)" : "var(--blue)",
                  cursor: adding || !addSymbol.trim() ? "not-allowed" : "pointer",
                }}
              >
                {adding ? "…" : "+ Add"}
              </button>
              {addError && <span className="text-xs" style={{ color: "var(--red)" }}>{addError}</span>}
            </form>
          )}

          {/* Divider */}
          <div style={{ width: 1, height: 24, background: "var(--border)" }} />

          {/* Scan list button */}
          {activeList && items.length > 0 && (
            <button
              onClick={handleScanList}
              disabled={scanning}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded transition-colors"
              style={{
                background: scanning ? "transparent" : "var(--accent-dim)",
                border: "1px solid var(--accent)",
                color: scanning ? "var(--text-dim)" : "var(--accent)",
                cursor: scanning ? "not-allowed" : "pointer",
              }}
            >
              {scanning ? "Scanning…" : (
                <>
                  <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <circle cx="5" cy="5" r="4" /><path d="M8.5 8.5L11 11" />
                  </svg>
                  Scan List
                </>
              )}
            </button>
          )}

          {scanMsg && (
            <span className="text-xs font-mono" style={{ color: "var(--green)", marginLeft: 4 }}>{scanMsg}</span>
          )}
        </div>

        {/* ── BODY: symbol list + chart ─────────────────────────────────── */}
        <div className="flex flex-1 min-h-0">

          {/* ── Panel: Symbol list (180px) ──────────────────────────────── */}
          <div
            className="flex flex-col shrink-0"
            style={{ width: 200, borderRight: "1px solid var(--border)", background: "var(--surface)", overflowY: "auto" }}
          >
            {!activeList ? (
              <p className="p-3 text-xs text-center" style={{ color: "var(--text-dim)" }}>Select a list above.</p>
            ) : itemsLoading ? (
              <div className="p-3 space-y-2">
                {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-10 rounded" />)}
              </div>
            ) : items.length === 0 ? (
              <p className="p-4 text-xs text-center" style={{ color: "var(--text-dim)" }}>
                Empty. Add tickers in the bar above.
              </p>
            ) : (
              items.map(item => {
                const isSelected = selectedItem?.id === item.id;
                const q = quotes[item.symbol];
                const up = q && !q.error ? q.change_pct >= 0 : null;
                return (
                  <div
                    key={item.id}
                    onClick={() => selectSymbol(item)}
                    className="group flex items-center gap-2 px-3 py-2 cursor-pointer transition-colors hover:bg-[var(--surface-2)]"
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      borderLeft: isSelected ? "2px solid var(--accent)" : "2px solid transparent",
                      background: isSelected ? "var(--surface-2)" : "transparent",
                    }}
                  >
                    <SymbolIcon symbol={item.symbol} size={24} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-xs truncate" style={{ color: "var(--text)" }}>
                          {item.symbol}
                        </span>
                        <MarketBadge market={item.market} />
                      </div>
                      {q && !q.error && (
                        <div className="flex items-center gap-1 mt-0.5">
                          <span className="font-mono text-xs" style={{ color: "var(--text-muted)" }}>
                            {q.price.toFixed(2)}
                          </span>
                          <span className="font-mono text-xs"
                            style={{ color: up ? "var(--green)" : "var(--red)" }}>
                            {up ? "+" : ""}{q.change_pct.toFixed(1)}%
                          </span>
                        </div>
                      )}
                      {quotesLoading && !q && (
                        <div className="skeleton rounded mt-0.5" style={{ width: 60, height: 10 }} />
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* ── Panel: Chart area (flex-1) ──────────────────────────────── */}
          <div className="flex-1 flex flex-col min-w-0" style={{ background: "#18181b" }}>
            {!selectedItem ? (
              <div className="flex-1 flex items-center justify-center" style={{ color: "var(--text-dim)" }}>
                <div className="text-center">
                  <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" className="mx-auto mb-3" style={{ opacity: 0.2 }}>
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                  <p className="font-mono text-sm" style={{ opacity: 0.4 }}>Select a symbol</p>
                </div>
              </div>
            ) : (
              <>
                {/* Chart header */}
                <div
                  className="flex items-center justify-between px-4 py-2.5 shrink-0"
                  style={{ borderBottom: "1px solid #27272a", background: "#1c1c1f" }}
                >
                  <div className="flex items-center gap-3">
                    <SymbolIcon symbol={selectedItem.symbol} size={30} />
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-base" style={{ color: "#fafafa" }}>
                          {selectedItem.symbol}
                        </span>
                        <MarketBadge market={selectedItem.market} />
                      </div>
                      <p className="text-xs" style={{ color: "#71717a" }}>
                        {selectedItem.market === "TASE" ? "Tel Aviv Stock Exchange" : "US Market"} · 6 months
                      </p>
                    </div>
                  </div>
                  <PriceDisplay quote={selectedQuote} loading={quotesLoading && !selectedQuote} size="lg" />
                </div>

                {/* Drawing toolbar */}
                <DrawingToolbar
                  mode={drawingMode}
                  hlineCount={hlines.length}
                  onMode={m => setDrawingMode(m)}
                  onClear={() => { setHlines([]); setDrawingMode("cursor"); }}
                />

                {/* Chart */}
                <div ref={chartContainerRef} className="flex-1 min-h-0">
                  {chartLoading ? (
                    <div className="skeleton" style={{ height: chartHeight || 300, margin: 8, borderRadius: 4 }} />
                  ) : (
                    <CandlestickChart
                      candles={chartCandles}
                      height={chartHeight || 300}
                      hlines={hlines}
                      drawingMode={drawingMode}
                      onChartClick={price => {
                        if (drawingMode === "hline") setHlines(prev => [...prev, price]);
                      }}
                    />
                  )}
                </div>

                {/* Chart footer: actions */}
                <div
                  className="flex items-center gap-2 px-4 py-2.5 shrink-0 flex-wrap"
                  style={{ borderTop: "1px solid #27272a", background: "#1c1c1f" }}
                >
                  <button
                    onClick={() => handleQuickScan(selectedItem)}
                    disabled={quickScanningId === selectedItem.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded transition-colors"
                    style={{
                      background: quickScanningId === selectedItem.id ? "transparent" : "rgba(87,193,213,0.1)",
                      border: "1px solid var(--accent)",
                      color: quickScanningId === selectedItem.id ? "#52525b" : "var(--accent)",
                      cursor: quickScanningId === selectedItem.id ? "not-allowed" : "pointer",
                    }}
                  >
                    {quickScanningId === selectedItem.id ? "Scanning…" : (
                      <>
                        <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                          <circle cx="5" cy="5" r="4" /><path d="M8.5 8.5L11 11" />
                        </svg>
                        Scan
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => setResearchTarget({ symbol: selectedItem.symbol, market: selectedItem.market as Market })}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded transition-colors"
                    style={{ background: "rgba(59,130,246,0.1)", border: "1px solid #3b82f6", color: "#93c5fd", cursor: "pointer" }}
                  >
                    <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M2 6h8M6 2l4 4-4 4" />
                    </svg>
                    Research
                  </button>

                  <div className="flex-1" />

                  {otherLists.length > 0 && (
                    <select
                      value=""
                      disabled={movingItemId === selectedItem.id}
                      onChange={e => { if (e.target.value) handleMove(selectedItem, e.target.value); }}
                      className="text-xs px-2 py-1.5 rounded cursor-pointer"
                      style={{ background: "#27272a", border: "1px solid #3f3f46", color: "#71717a" }}
                    >
                      <option value="">Move to list →</option>
                      {otherLists.map(wl => <option key={wl.id} value={wl.id}>{wl.name}</option>)}
                    </select>
                  )}

                  <button
                    onClick={() => handleRemove(selectedItem)}
                    disabled={removingId === selectedItem.id}
                    className="px-3 py-1.5 text-xs rounded transition-colors"
                    style={{ background: "transparent", border: "1px solid #3f3f46", color: "#71717a", cursor: removingId === selectedItem.id ? "not-allowed" : "pointer" }}
                  >
                    {removingId === selectedItem.id ? "…" : "Remove"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
