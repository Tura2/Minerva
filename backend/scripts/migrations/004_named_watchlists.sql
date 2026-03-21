-- Migration 004: Named Watchlists
-- Applied: 2026-03-21
-- Introduces a `watchlists` table so items can be organised into named lists.
-- Existing items are migrated to a default "Main" list.

-- 1. Watchlists table
CREATE TABLE watchlists (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT watchlists_name_nonempty CHECK (char_length(trim(name)) > 0)
);

CREATE INDEX idx_watchlists_created_at ON watchlists(created_at);

-- 2. Add watchlist_id FK to items (nullable while we seed the default list)
ALTER TABLE watchlist_items
    ADD COLUMN watchlist_id UUID REFERENCES watchlists(id) ON DELETE CASCADE;

-- 3. Insert the default "Main" list and stamp every existing item with its id
WITH default_wl AS (
    INSERT INTO watchlists (name, description)
    VALUES ('Main', 'Default watchlist')
    RETURNING id
)
UPDATE watchlist_items
SET watchlist_id = (SELECT id FROM default_wl);

-- 4. Enforce NOT NULL now that every row has a value
ALTER TABLE watchlist_items
    ALTER COLUMN watchlist_id SET NOT NULL;

-- 5. Drop old (symbol, market) uniqueness — same stock can live in multiple lists
ALTER TABLE watchlist_items
    DROP CONSTRAINT IF EXISTS watchlist_items_symbol_market_key;

-- 6. New uniqueness: one entry per (symbol, market, list)
ALTER TABLE watchlist_items
    ADD CONSTRAINT watchlist_items_symbol_market_watchlist_key
    UNIQUE (symbol, market, watchlist_id);

-- 7. Fast lookup of items belonging to a watchlist
CREATE INDEX idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);
