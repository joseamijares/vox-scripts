-- Add watchlist table to Supabase
-- Run this in SQL Editor: https://supabase.com/dashboard/project/msvcrlijclhuifdjjmyy/sql/new

CREATE TABLE IF NOT EXISTS watchlist (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    name TEXT,
    sector TEXT,
    thesis TEXT,
    entry_price FLOAT,
    target_price FLOAT,
    stop_loss FLOAT,
    grade INTEGER,
    council TEXT,
    status TEXT DEFAULT 'watching',
    added_at TIMESTAMPTZ DEFAULT NOW(),
    triggered_at TIMESTAMPTZ,
    notes TEXT
);

ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read" ON watchlist FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON watchlist FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_watchlist_ticker ON watchlist(ticker);
CREATE INDEX IF NOT EXISTS idx_watchlist_status ON watchlist(status);
