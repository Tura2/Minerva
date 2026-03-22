"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { executeResearch } from "./api/research";
import { ApiError, type ExecuteResearchRequest, type PreScreenError } from "./types";

type JobStatus = "running" | "done" | "prescreen_failed" | "error";

export interface ResearchJob {
  symbol: string;
  market: string;
  status: JobStatus;
  ticketId?: string;
  error?: string;
  preScreenError?: PreScreenError;
  req: ExecuteResearchRequest;
}

interface ResearchCtx {
  job: ResearchJob | null;
  startResearch: (req: ExecuteResearchRequest) => void;
  clearJob: () => void;
}

const Ctx = createContext<ResearchCtx | null>(null);

export function ResearchProvider({ children }: { children: ReactNode }) {
  const [job, setJob] = useState<ResearchJob | null>(null);

  const startResearch = useCallback((req: ExecuteResearchRequest) => {
    setJob({ symbol: req.symbol, market: req.market as string, status: "running", req });

    executeResearch(req)
      .then((ticket) => {
        setJob((prev) =>
          prev ? { ...prev, status: "done", ticketId: ticket.id } : null,
        );
      })
      .catch((err) => {
        if (err instanceof ApiError && err.isPreScreenFailed()) {
          setJob((prev) =>
            prev
              ? { ...prev, status: "prescreen_failed", preScreenError: err.detail as PreScreenError }
              : null,
          );
        } else {
          const msg =
            err instanceof ApiError
              ? typeof err.detail === "string"
                ? err.detail
                : "Research failed."
              : "Network error.";
          setJob((prev) => (prev ? { ...prev, status: "error", error: msg } : null));
        }
      });
  }, []);

  const clearJob = useCallback(() => setJob(null), []);

  return (
    <Ctx.Provider value={{ job, startResearch, clearJob }}>{children}</Ctx.Provider>
  );
}

export function useResearch() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useResearch must be used within ResearchProvider");
  return ctx;
}
