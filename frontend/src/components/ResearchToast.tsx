"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useResearch } from "@/lib/ResearchContext";

function Spinner() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      style={{ animation: "spin 0.8s linear infinite", flexShrink: 0 }}
    >
      <circle cx="7" cy="7" r="5.5" stroke="currentColor" strokeWidth="1.5" strokeDasharray="22" strokeDashoffset="8" strokeLinecap="round" />
    </svg>
  );
}

export default function ResearchToast() {
  const { job, startResearch, clearJob } = useResearch();
  const router = useRouter();
  const autoNavTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-navigate when done
  useEffect(() => {
    if (job?.status === "done" && job.ticketId) {
      autoNavTimer.current = setTimeout(() => {
        router.push(`/research/${job.ticketId}`);
        clearJob();
      }, 3000);
    }
    return () => {
      if (autoNavTimer.current) clearTimeout(autoNavTimer.current);
    };
  }, [job?.status, job?.ticketId, router, clearJob]);

  if (!job) return null;

  const marketColor = job.market === "TASE" ? "var(--accent)" : "#93c5fd";

  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } } @keyframes slideUp { from { transform: translateY(16px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }`}</style>
      <div
        role="status"
        aria-live="polite"
        style={{
          position: "fixed",
          bottom: 24,
          right: 24,
          zIndex: 9999,
          width: 320,
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: 6,
          boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
          overflow: "hidden",
          animation: "slideUp 0.2s ease",
        }}
      >
        {/* Accent strip */}
        <div
          style={{
            height: 2,
            background:
              job.status === "done"
                ? "var(--green)"
                : job.status === "error"
                  ? "var(--red)"
                  : job.status === "prescreen_failed"
                    ? "#f97316"
                    : "var(--accent)",
          }}
        />

        <div className="p-4 space-y-3">
          {/* Header row */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              {job.status === "running" && (
                <span style={{ color: "var(--accent)" }}>
                  <Spinner />
                </span>
              )}
              {job.status === "done" && (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ color: "var(--green)", flexShrink: 0 }}>
                  <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M4.5 7l2 2 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
              {(job.status === "error" || job.status === "prescreen_failed") && (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" style={{ color: job.status === "prescreen_failed" ? "#f97316" : "var(--red)", flexShrink: 0 }}>
                  <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M7 4v3.5M7 9.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              )}

              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="font-mono font-bold text-sm" style={{ color: "var(--text)" }}>
                    {job.symbol}
                  </span>
                  <span
                    className="font-mono text-xs px-1 rounded"
                    style={{
                      background: job.market === "TASE" ? "var(--accent-dim)" : "var(--blue-dim)",
                      color: marketColor,
                    }}
                  >
                    {job.market}
                  </span>
                </div>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-dim)" }}>
                  {job.status === "running" && "Analyzing — this can take a minute..."}
                  {job.status === "done" && "Research complete — navigating in 3s"}
                  {job.status === "prescreen_failed" && "Pre-screen failed"}
                  {job.status === "error" && (job.error ?? "Research failed")}
                </p>
              </div>
            </div>

            <button
              onClick={clearJob}
              aria-label="Dismiss"
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "var(--text-dim)",
                fontSize: 16,
                lineHeight: 1,
                padding: "2px 4px",
                flexShrink: 0,
              }}
            >
              ×
            </button>
          </div>

          {/* Action buttons */}
          {job.status === "done" && job.ticketId && (
            <button
              onClick={() => {
                if (autoNavTimer.current) clearTimeout(autoNavTimer.current);
                router.push(`/research/${job.ticketId}`);
                clearJob();
              }}
              className="w-full py-2 text-xs font-semibold font-mono uppercase tracking-wide"
              style={{
                background: "var(--green-dim)",
                border: "1px solid var(--green)",
                borderRadius: 3,
                color: "var(--green)",
                cursor: "pointer",
              }}
            >
              View Research →
            </button>
          )}

          {job.status === "prescreen_failed" && (
            <div className="flex gap-2">
              <button
                onClick={() => {
                  startResearch({ ...job.req, force: true });
                }}
                className="flex-1 py-2 text-xs font-semibold font-mono uppercase tracking-wide"
                style={{
                  background: "#78350f",
                  border: "1px solid #f97316",
                  borderRadius: 3,
                  color: "#fdba74",
                  cursor: "pointer",
                }}
              >
                Force Research
              </button>
              <button
                onClick={clearJob}
                className="px-3 py-2 text-xs font-semibold font-mono uppercase tracking-wide"
                style={{
                  background: "var(--surface-2)",
                  border: "1px solid var(--border)",
                  borderRadius: 3,
                  color: "var(--text-dim)",
                  cursor: "pointer",
                }}
              >
                Dismiss
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
