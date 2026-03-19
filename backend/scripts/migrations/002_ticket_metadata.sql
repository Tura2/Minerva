-- Migration 002: Add metadata, key_triggers, and research_model to research_tickets
-- Run after 001_initial_schema.sql

-- JSONB blob for all extra analysis fields (rationale, breadth context, sizing detail, etc.)
ALTER TABLE research_tickets
  ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Array of key triggers from LLM output
ALTER TABLE research_tickets
  ADD COLUMN IF NOT EXISTS key_triggers TEXT[] DEFAULT '{}';

-- Index for fast status-based queries
CREATE INDEX IF NOT EXISTS idx_research_tickets_created_at
  ON research_tickets(created_at DESC);

-- Index for symbol + market compound lookup
CREATE INDEX IF NOT EXISTS idx_research_tickets_symbol_market
  ON research_tickets(symbol, market);
