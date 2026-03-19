"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listTickets } from "@/lib/api/research";
import { getCandidates } from "@/lib/api/scanner";
import { listWatchlist } from "@/lib/api/watchlist";
import type { ResearchTicket } from "@/lib/types";

function StatCard({
  label,
  value,
  href,
  accent,
}: {
  label: string;
  value: number | string;
  href: string;
  accent?: string;
}) {
  return (
    <Link
      href={href}
      className="block p-4 transition-colors"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
        borderRadius: "4px",
      }}
    >
      <p className="text-xs uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
        {label}
      </p>
      <p
        className="text-3xl font-mono font-semibold"
        style={{ color: accent ?? "var(--text)" }}
      >
        {value}
      </p>
    </Link>
  );
}

function TicketRow({ ticket }: { ticket: ResearchTicket }) {
  const statusColor =
    ticket.status === "approved"
      ? "var(--green)"
      : ticket.status === "rejected"
        ? "var(--red)"
        : "var(--accent)";

  const prob = Math.round(ticket.bullish_probability * 100);

  return (
    <Link
      href={`/research/${ticket.id}`}
      className="flex items-center gap-4 px-4 py-3 transition-colors hover:bg-[var(--surface-2)]"
      style={{ borderBottom: "1px solid var(--border-subtle)" }}
    >
      <span className="font-mono text-sm font-semibold w-20" style={{ color: "var(--text)" }}>
        {ticket.symbol}
      </span>
      <span
        className="text-xs px-1.5 py-0.5 font-mono rounded w-14 text-center"
        style={{
          background: ticket.market === "US" ? "var(--blue-dim)" : "var(--accent-dim)",
          color: ticket.market === "US" ? "#93c5fd" : "var(--accent)",
        }}
      >
        {ticket.market}
      </span>
      <span className="font-mono text-sm w-20" style={{ color: "var(--text)" }}>
        {ticket.currency === "ILS" ? "₪" : "$"}
        {ticket.entry_price.toFixed(2)}
      </span>
      <div className="flex-1">
        <div
          className="h-1 rounded-full overflow-hidden"
          style={{ background: "var(--surface-2)" }}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${prob}%`,
              background: prob >= 65 ? "var(--green)" : prob >= 50 ? "var(--accent)" : "var(--red)",
            }}
          />
        </div>
      </div>
      <span className="font-mono text-xs w-12 text-right" style={{ color: "var(--text-muted)" }}>
        {prob}%
      </span>
      <span
        className="text-xs font-mono w-16 text-right"
        style={{ color: statusColor }}
      >
        {ticket.status}
      </span>
    </Link>
  );
}

export default function HomePage() {
  const [ticketCount, setTicketCount] = useState<number>(0);
  const [pendingCount, setPendingCount] = useState<number>(0);
  const [approvedCount, setApprovedCount] = useState<number>(0);
  const [candidateCount, setCandidateCount] = useState<number>(0);
  const [watchlistCount, setWatchlistCount] = useState<number>(0);
  const [recentTickets, setRecentTickets] = useState<ResearchTicket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadDashboard() {
      try {
        const [tickets, candidates, watchlist] = await Promise.allSettled([
          listTickets({ limit: 10 }),
          getCandidates(undefined, 50),
          listWatchlist(),
        ]);

        if (tickets.status === "fulfilled") {
          const t = tickets.value;
          setRecentTickets(t.slice(0, 5));
          setTicketCount(t.length);
          setPendingCount(t.filter((x) => x.status === "pending").length);
          setApprovedCount(t.filter((x) => x.status === "approved").length);
        }
        if (candidates.status === "fulfilled") {
          setCandidateCount(candidates.value.length);
        }
        if (watchlist.status === "fulfilled") {
          setWatchlistCount(watchlist.value.length);
        }
      } finally {
        setLoading(false);
      }
    }
    loadDashboard();
  }, []);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1
          className="font-mono text-xl font-semibold tracking-wide"
          style={{ color: "var(--text)" }}
        >
          Dashboard
        </h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-dim)" }}>
          Swing-trading research copilot — US &amp; TASE markets
        </p>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="skeleton h-20 rounded" />
          ))
        ) : (
          <>
            <StatCard label="Watchlist" value={watchlistCount} href="/watchlist" />
            <StatCard
              label="Candidates"
              value={candidateCount}
              href="/candidates"
              accent="var(--accent)"
            />
            <StatCard label="Tickets" value={ticketCount} href="/research" />
            <StatCard
              label="Pending"
              value={pendingCount}
              href="/research?status=pending"
              accent="var(--accent)"
            />
            <StatCard
              label="Approved"
              value={approvedCount}
              href="/research?status=approved"
              accent="var(--green)"
            />
          </>
        )}
      </div>

      {/* Recent tickets */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-mono uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>
            Recent Research
          </h2>
          <Link
            href="/research"
            className="text-xs font-mono"
            style={{ color: "var(--accent)" }}
          >
            View all →
          </Link>
        </div>

        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "4px",
            overflow: "hidden",
          }}
        >
          {loading ? (
            <div className="p-4 space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="skeleton h-8 rounded" />
              ))}
            </div>
          ) : recentTickets.length === 0 ? (
            <div className="p-8 text-center">
              <p className="text-sm" style={{ color: "var(--text-dim)" }}>
                No research tickets yet.
              </p>
              <Link
                href="/candidates"
                className="text-xs font-mono mt-2 inline-block"
                style={{ color: "var(--accent)" }}
              >
                Run a scan to get started →
              </Link>
            </div>
          ) : (
            recentTickets.map((ticket) => <TicketRow key={ticket.id} ticket={ticket} />)
          )}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[
          {
            href: "/watchlist",
            title: "Manage Watchlist",
            desc: "Add or remove symbols from your scan universe",
          },
          {
            href: "/candidates",
            title: "Run Scanner",
            desc: "Screen watchlist symbols with Minervini Stage 2 filters",
          },
          {
            href: "/research",
            title: "Review Tickets",
            desc: "Approve or reject pending research results",
          },
        ].map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="p-4 transition-colors hover:border-zinc-500"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "4px",
              display: "block",
            }}
          >
            <p className="text-sm font-semibold mb-1" style={{ color: "var(--text)" }}>
              {card.title}
            </p>
            <p className="text-xs" style={{ color: "var(--text-dim)" }}>
              {card.desc}
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
