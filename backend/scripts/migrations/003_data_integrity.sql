-- Migration 003: Data integrity improvements
-- Applied: 2026-03-19

-- Add total_in_watchlist to scan_history
ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS total_in_watchlist integer NOT NULL DEFAULT 0;

-- Auto-update updated_at on research_tickets when status changes
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_research_tickets_updated_at ON research_tickets;
CREATE TRIGGER trg_research_tickets_updated_at
  BEFORE UPDATE ON research_tickets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
