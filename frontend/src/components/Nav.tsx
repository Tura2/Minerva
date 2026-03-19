"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/candidates", label: "Candidates" },
  { href: "/research", label: "Research" },
  { href: "/watchlist", label: "Watchlist" },
];

export default function Nav() {
  const pathname = usePathname();

  return (
    <header
      style={{
        background: "var(--surface)",
        borderBottom: "1px solid var(--border)",
      }}
      className="sticky top-0 z-50"
    >
      <div className="max-w-7xl mx-auto px-4 flex items-center gap-8 h-12">
        {/* Wordmark */}
        <Link
          href="/"
          className="font-mono text-sm font-semibold tracking-widest uppercase"
          style={{ color: "var(--accent)", letterSpacing: "0.2em" }}
        >
          MINERVA
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {NAV_LINKS.map((link) => {
            const active =
              link.href === "/"
                ? pathname === "/"
                : pathname === link.href || pathname.startsWith(link.href + "/");
            return (
              <Link
                key={link.href}
                href={link.href}
                className="px-3 py-1 text-xs font-medium tracking-wide uppercase transition-colors"
                style={{
                  color: active ? "var(--text)" : "var(--text-dim)",
                  background: active ? "var(--surface-2)" : "transparent",
                  borderRadius: "2px",
                  letterSpacing: "0.08em",
                }}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        {/* Right side: market status indicator */}
        <div className="ml-auto flex items-center gap-2">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{ background: "var(--green)" }}
          />
          <span className="text-xs font-mono" style={{ color: "var(--text-dim)" }}>
            LIVE
          </span>
        </div>
      </div>
    </header>
  );
}
