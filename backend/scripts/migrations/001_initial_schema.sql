-- Migration 001: Initial schema
-- Applied: 2026-03-19

-- Watchlist items: user-tracked symbols, also the scan universe
CREATE TABLE watchlist_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('US', 'TASE')),
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT,
    UNIQUE (symbol, market)
);

-- Scan history: one row per scan run
CREATE TABLE scan_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market TEXT NOT NULL CHECK (market IN ('US', 'TASE')),
    ran_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    candidate_count INTEGER NOT NULL DEFAULT 0,
    filters JSONB,
    status TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('running', 'completed', 'failed'))
);

-- Candidates: symbols that passed the screener filter in a scan run
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id UUID NOT NULL REFERENCES scan_history(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('US', 'TASE')),
    price NUMERIC(12, 4),
    volume BIGINT,
    score NUMERIC(6, 4),
    screened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB
);

-- Research tickets: structured LLM output per symbol
CREATE TABLE research_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('US', 'TASE')),
    workflow_type TEXT NOT NULL DEFAULT 'technical-swing',
    source_skill TEXT,
    research_model TEXT,
    entry_price NUMERIC(12, 4),
    stop_loss NUMERIC(12, 4),
    target NUMERIC(12, 4),
    position_size INTEGER,
    max_risk NUMERIC(12, 4),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK (currency IN ('USD', 'ILS')),
    bullish_probability NUMERIC(4, 3),
    entry_rationale TEXT,
    key_triggers JSONB,
    caveats JSONB,
    raw_response JSONB,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Auto-update updated_at on research_tickets
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_tickets_updated_at
    BEFORE UPDATE ON research_tickets
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Indexes for common query patterns
CREATE INDEX idx_watchlist_market ON watchlist_items(market);
CREATE INDEX idx_candidates_scan_id ON candidates(scan_id);
CREATE INDEX idx_candidates_market ON candidates(market);
CREATE INDEX idx_research_tickets_symbol ON research_tickets(symbol, market);
CREATE INDEX idx_research_tickets_status ON research_tickets(status);
