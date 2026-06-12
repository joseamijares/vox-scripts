-- Add journal table to Supabase
-- Run this in SQL Editor: https://supabase.com/dashboard/project/msvcrlijclhuifdjjmyy/sql/new

CREATE TABLE IF NOT EXISTS journal (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    date DATE DEFAULT CURRENT_DATE,
    ticker TEXT NOT NULL,
    action TEXT NOT NULL,
    shares FLOAT,
    price FLOAT,
    notional FLOAT,
    broker TEXT,
    reason TEXT,
    grade_at_entry INTEGER,
    council_at_entry TEXT,
    notes TEXT,
    pnl FLOAT,
    pnl_pct FLOAT,
    tags TEXT[]
);

ALTER TABLE journal ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read" ON journal FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON journal FOR ALL USING (auth.role() = 'service_role');

CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date);
CREATE INDEX IF NOT EXISTS idx_journal_ticker ON journal(ticker);
CREATE INDEX IF NOT EXISTS idx_journal_timestamp ON journal(timestamp);
