"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { useTheme } from "@/lib/ThemeProvider";

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconDashboard() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="1" width="6" height="6" rx="1" />
      <rect x="9" y="1" width="6" height="6" rx="1" />
      <rect x="1" y="9" width="6" height="6" rx="1" />
      <rect x="9" y="9" width="6" height="6" rx="1" />
    </svg>
  );
}

function IconCandidates() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4h12M4 8h8M6 12h4" />
    </svg>
  );
}

function IconResearch() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 2H3a1 1 0 00-1 1v10a1 1 0 001 1h10a1 1 0 001-1V7" />
      <path d="M9 2l4 4M9 2v4h4" />
      <path d="M5 9h6M5 11.5h4" />
    </svg>
  );
}

function IconWatchlist() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 3h12M2 7h12M2 11h8" />
      <circle cx="13" cy="11.5" r="2" />
    </svg>
  );
}

function IconSun() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" />
      <line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" />
      <line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  );
}

function IconMoon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function IconMenu() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <path d="M2 4h14M2 9h14M2 14h14" />
    </svg>
  );
}

// ── Nav links config ──────────────────────────────────────────────────────────

const NAV_LINKS = [
  { href: "/", label: "Dashboard", Icon: IconDashboard },
  { href: "/candidates", label: "Candidates", Icon: IconCandidates },
  { href: "/research", label: "Research", Icon: IconResearch },
  { href: "/watchlist", label: "Watchlist", Icon: IconWatchlist },
];

// ── Sidebar inner content ─────────────────────────────────────────────────────

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <div className="flex flex-col h-full">
      {/* Logo + Wordmark */}
      <div
        className="px-4 py-4 shrink-0"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <Link
          href="/"
          onClick={onNavigate}
          className="flex items-center gap-2.5"
          style={{ textDecoration: "none" }}
        >
          <Image
            src="/logo.png"
            alt="Minerva"
            width={32}
            height={32}
            className="rounded-md shrink-0"
            style={{ objectFit: "contain" }}
            onError={() => {}}
          />
          <div>
            <p className="font-mono font-bold text-sm tracking-wider uppercase"
              style={{ color: "var(--accent)", letterSpacing: "0.15em", lineHeight: 1.2 }}>
              MINERVA
            </p>
            <p className="text-xs" style={{ color: "var(--text-dim)", lineHeight: 1.2 }}>
              Research Copilot
            </p>
          </div>
        </Link>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {NAV_LINKS.map(({ href, label, Icon }) => {
          const active =
            href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              onClick={onNavigate}
              className="flex items-center gap-3 px-3 py-2.5 rounded-sm transition-all"
              style={{
                color: active ? "var(--text)" : "var(--text-dim)",
                background: active ? "var(--surface-2)" : "transparent",
                borderLeft: `2px solid ${active ? "var(--accent)" : "transparent"}`,
                textDecoration: "none",
              }}
            >
              <span style={{ color: active ? "var(--accent)" : "var(--text-dim)" }}>
                <Icon />
              </span>
              <span className="text-sm font-medium">{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Bottom section */}
      <div
        className="px-3 py-4 space-y-3 shrink-0"
        style={{ borderTop: "1px solid var(--border)" }}
      >
        {/* Live indicator */}
        <div className="flex items-center gap-2 px-3">
          <span
            className="live-dot inline-block w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--green)", boxShadow: "0 0 6px var(--green)" }}
          />
          <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
            LIVE
          </span>
        </div>

        {/* Theme toggle */}
        <button
          onClick={toggle}
          className="flex items-center gap-2.5 w-full px-3 py-2 rounded-sm transition-colors"
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-dim)",
            cursor: "pointer",
            textAlign: "left",
          }}
          aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? <IconSun /> : <IconMoon />}
          <span className="text-sm">{theme === "dark" ? "Light mode" : "Dark mode"}</span>
        </button>
      </div>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────

export default function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      {/* ── Desktop sidebar ──────────────────────────────────────────── */}
      <aside
        className="hidden md:flex flex-col shrink-0"
        style={{
          width: 220,
          minHeight: "100vh",
          position: "sticky",
          top: 0,
          height: "100vh",
          background: "var(--surface)",
          borderRight: "1px solid var(--border)",
          boxShadow: "1px 0 0 var(--border)",
        }}
      >
        <SidebarContent />
      </aside>

      {/* ── Mobile top bar ────────────────────────────────────────────── */}
      <header
        className="md:hidden sticky top-0 z-40 flex items-center gap-3 px-4"
        style={{
          height: 48,
          background: "var(--surface)",
          borderBottom: "1px solid var(--border)",
          boxShadow: "var(--shadow)",
        }}
      >
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
          style={{
            background: "none",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            padding: 4,
          }}
        >
          <IconMenu />
        </button>
        <Link
          href="/"
          className="font-mono font-bold tracking-widest uppercase text-sm"
          style={{ color: "var(--accent)" }}
        >
          MINERVA
        </Link>
      </header>

      {/* ── Mobile drawer ─────────────────────────────────────────────── */}
      {mobileOpen && (
        <>
          {/* Backdrop */}
          <div
            className="md:hidden fixed inset-0 z-50"
            style={{ background: "rgba(0,0,0,0.6)" }}
            onClick={() => setMobileOpen(false)}
          />
          {/* Drawer */}
          <div
            className="md:hidden fixed top-0 left-0 z-50 flex flex-col"
            style={{
              width: 240,
              height: "100vh",
              background: "var(--surface)",
              borderRight: "1px solid var(--border)",
              boxShadow: "4px 0 24px rgba(0,0,0,0.4)",
            }}
          >
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </div>
        </>
      )}
    </>
  );
}
