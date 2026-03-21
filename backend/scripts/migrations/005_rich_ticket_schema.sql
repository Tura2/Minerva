-- Migration 005: Rich Ticket Schema
-- Applied: 2026-03-21
-- Adds flat columns for RS rank, setup score, verdict, and entry type
-- to research_tickets. These enable sorting/filtering on the candidates page.
-- All rich analytical data (scenarios, synthesized_score, scale_out_targets,
-- execution_checklist, final_recommendation) lives in the existing metadata JSONB.

ALTER TABLE research_tickets
    ADD COLUMN IF NOT EXISTS rs_rank_pct    FLOAT,      -- RS percentile vs watchlist universe (0–100)
    ADD COLUMN IF NOT EXISTS setup_score    SMALLINT,   -- synthesized_score.total (0–60)
    ADD COLUMN IF NOT EXISTS verdict        TEXT,       -- final_recommendation.verdict
    ADD COLUMN IF NOT EXISTS entry_type     TEXT;       -- 'current' | 'breakout'

-- Index for sorting candidates by setup quality
CREATE INDEX IF NOT EXISTS idx_research_tickets_setup_score
    ON research_tickets(setup_score DESC NULLS LAST);

-- Index for sorting by RS rank
CREATE INDEX IF NOT EXISTS idx_research_tickets_rs_rank
    ON research_tickets(rs_rank_pct DESC NULLS LAST);

-- Check constraint for verdict values
ALTER TABLE research_tickets
    ADD CONSTRAINT research_tickets_verdict_check
    CHECK (verdict IS NULL OR verdict IN ('Strong Buy', 'Buy', 'Watch', 'Avoid'));

-- Check constraint for entry_type values
ALTER TABLE research_tickets
    ADD CONSTRAINT research_tickets_entry_type_check
    CHECK (entry_type IS NULL OR entry_type IN ('current', 'breakout'));
