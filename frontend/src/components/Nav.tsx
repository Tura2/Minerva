"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "@/lib/ThemeProvider";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/candidates", label: "Candidates" },
  { href: "/research", label: "Research" },
  { href: "/watchlist", label: "Watchlist" },
];

function SunIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
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

function MoonIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export default function Nav() {
  const pathname = usePathname();
  const { theme, toggle } = useTheme();

  return (
    <header
      style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
        boxShadow: "var(--shadow)",
      }}
      className="sticky top-0 z-50"
    >
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-6 h-12">
        {/* Wordmark */}
        <Link
          href="/"
          className="text-sm font-bold tracking-widest uppercase shrink-0"
          style={{ color: "var(--accent)", letterSpacing: "0.2em", fontFamily: "Assistant, sans-serif" }}
        >
          MINERVA
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-0.5">
          {NAV_LINKS.map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.href}
                href={link.href}
                className="px-3 py-1.5 text-xs font-semibold tracking-wide transition-colors rounded-sm"
                style={{
                  color: active ? "var(--text)" : "var(--text-dim)",
                  background: active ? "var(--surface-2)" : "transparent",
                }}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-3">
          {/* Live indicator */}
          <div className="hidden sm:flex items-center gap-1.5">
            <span
              className="inline-block w-1.5 h-1.5 rounded-full"
              style={{ background: "var(--green)" }}
            />
            <span className="text-xs" style={{ color: "var(--text-dim)" }}>
              LIVE
            </span>
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggle}
            className="flex items-center justify-center w-7 h-7 rounded transition-colors"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--text-muted)",
              cursor: "pointer",
            }}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </header>
  );
}
