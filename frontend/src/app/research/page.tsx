"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listTickets } from "@/lib/api/research";
import type { Market, ResearchTicket, TicketStatus } from "@/lib/types";

function StatusBadge({ status }: { status: TicketStatus }) {
  const styles: Record<TicketStatus, { bg: string; color: string }> = {
    pending: { bg: "var(--accent-dim)", color: "var(--accent)" },
    approved: { bg: "var(--green-dim)", color: "var(--green)" },
    rejected: { bg: "var(--red-dim)", color: "var(--red)" },
  };
  const s = styles[status];
  return (
    <span
      className="px-1.5 py-0.5 text-xs font-mono rounded"
      style={{ background: s.bg, color: s.color }}
    >
      {status}
    </span>
  );
}

function QualityBadge({ q }: { q?: string }) {
  if (!q) return <span style={{ color: "var(--text-dim)" }}>—</span>;
  const colors: Record<string, string> = {
    A: "var(--green)",
    B: "var(--accent)",
    C: "#f97316",
  };
  return (
    <span className="font-mono font-bold text-sm" style={{ color: colors[q] ?? "var(--text-muted)" }}>
      {q}
    </span>
  );
}

export default function ResearchPage() {
  const [tickets, setTickets] = useState<ResearchTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterMarket, setFilterMarket] = useState<Market | "ALL">("ALL");
  const [filterStatus, setFilterStatus] = useState<TicketStatus | "ALL">("ALL");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await listTickets({
          market: filterMarket === "ALL" ? undefined : filterMarket,
          status: filterStatus === "ALL" ? undefined : filterStatus,
          limit: 100,
        });
        setTickets(data);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filterMarket, filterStatus]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1
          className="font-mono text-xl font-semibold tracking-wide"
          style={{ color: "var(--text)" }}
        >
          Research Tickets
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-dim)" }}>
          {tickets.length} ticket{tickets.length !== 1 ? "s" : ""}
          {filterStatus !== "ALL" ? ` — ${filterStatus}` : ""}
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex gap-1">
          <span className="text-xs font-mono mr-1 self-center" style={{ color: "var(--text-dim)" }}>
            Market:
          </span>
          {(["ALL", "US", "TASE"] as const).map((m) => (
            <button
              key={m}
              onClick={() => setFilterMarket(m)}
              className="px-2.5 py-1 text-xs font-mono uppercase tracking-wide transition-colors"
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

        <div className="flex gap-1">
          <span className="text-xs font-mono mr-1 self-center" style={{ color: "var(--text-dim)" }}>
            Status:
          </span>
          {(["ALL", "pending", "approved", "rejected"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilterStatus(s)}
              className="px-2.5 py-1 text-xs font-mono uppercase tracking-wide transition-colors"
              style={{
                background: filterStatus === s ? "var(--surface-2)" : "transparent",
                border: "1px solid",
                borderColor: filterStatus === s ? "var(--border)" : "transparent",
                borderRadius: "2px",
                color: filterStatus === s ? "var(--text)" : "var(--text-dim)",
                cursor: "pointer",
              }}
            >
              {s}
            </button>
          ))}
        </div>
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
        <div
          className="grid px-4 py-2 text-xs font-mono uppercase tracking-widest"
          style={{
            gridTemplateColumns: "80px 70px 90px 90px 90px 60px 70px 80px 100px",
            borderBottom: "1px solid var(--border)",
            color: "var(--text-dim)",
          }}
        >
          <span>Symbol</span>
          <span>Mkt</span>
          <span className="text-right">Entry</span>
          <span className="text-right">Stop</span>
          <span className="text-right">Target</span>
          <span className="text-right">Size</span>
          <span className="text-right">Prob</span>
          <span className="text-center">Quality</span>
          <span className="text-right">Status</span>
        </div>

        {loading ? (
          <div className="p-4 space-y-3">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="skeleton h-10 rounded" />
            ))}
          </div>
        ) : tickets.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="text-sm" style={{ color: "var(--text-dim)" }}>
              No research tickets found.
            </p>
            <Link
              href="/candidates"
              className="text-xs font-mono mt-2 inline-block"
              style={{ color: "var(--accent)" }}
            >
              Run research on a candidate →
            </Link>
          </div>
        ) : (
          tickets.map((t) => {
            const sym = t.currency === "ILS" ? "₪" : "$";
            const prob = Math.round(t.bullish_probability * 100);
            return (
              <Link
                key={t.id}
                href={`/research/${t.id}`}
                className="grid items-center px-4 py-3 hover:bg-zinc-800 transition-colors"
                style={{
                  gridTemplateColumns: "80px 70px 90px 90px 90px 60px 70px 80px 100px",
                  borderBottom: "1px solid var(--border-subtle)",
                  textDecoration: "none",
                }}
              >
                <span
                  className="font-mono text-sm font-semibold"
                  style={{ color: "var(--text)" }}
                >
                  {t.symbol}
                </span>

                <span
                  className="px-1.5 py-0.5 text-xs font-mono rounded w-fit"
                  style={{
                    background: t.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
                    color: t.market === "US" ? "#93c5fd" : "var(--accent)",
                  }}
                >
                  {t.market}
                </span>

                <span
                  className="font-mono text-xs text-right"
                  style={{ color: "var(--text)" }}
                >
                  {sym}{t.entry_price.toFixed(2)}
                </span>
                <span
                  className="font-mono text-xs text-right"
                  style={{ color: "var(--red)" }}
                >
                  {sym}{t.stop_loss.toFixed(2)}
                </span>
                <span
                  className="font-mono text-xs text-right"
                  style={{ color: "var(--green)" }}
                >
                  {sym}{t.target.toFixed(2)}
                </span>

                <span
                  className="font-mono text-xs text-right"
                  style={{ color: "var(--text-muted)" }}
                >
                  {t.position_size}
                </span>

                <span
                  className="font-mono text-xs text-right"
                  style={{
                    color:
                      prob >= 65
                        ? "var(--green)"
                        : prob >= 50
                          ? "var(--accent)"
                          : "var(--red)",
                  }}
                >
                  {prob}%
                </span>

                <div className="flex justify-center">
                  <QualityBadge q={t.metadata?.setup_quality} />
                </div>

                <div className="flex justify-end">
                  <StatusBadge status={t.status} />
                </div>
              </Link>
            );
          })
        )}
      </div>
    </div>
  );
}
