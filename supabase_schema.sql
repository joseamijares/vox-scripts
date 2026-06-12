-- VOX Database Schema for Supabase
-- Run this in Supabase SQL Editor: https://supabase.com/dashboard/project/msvcrlijclhuifdjjmyy/sql/new

-- 1. Positions (current state)
CREATE TABLE IF NOT EXISTS positions (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL UNIQUE,
    shares FLOAT,
    avg_cost FLOAT,
    live_price FLOAT,
    live_value FLOAT,
    grade INTEGER,
    council TEXT,
    brokers TEXT[],
    sector TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE positions ENABLE ROW LEVEL SECURITY;

-- Allow anon read
CREATE POLICY "Allow anon read" ON positions
    FOR SELECT USING (true);

-- Allow service role all access
CREATE POLICY "Allow service role all" ON positions
    FOR ALL USING (auth.role() = 'service_role');

-- 2. Position History (daily snapshots)
CREATE TABLE IF NOT EXISTS position_history (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    date DATE NOT NULL,
    shares FLOAT,
    price FLOAT,
    value FLOAT,
    grade INTEGER,
    council TEXT,
    UNIQUE(ticker, date)
);

ALTER TABLE position_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read" ON position_history FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON position_history FOR ALL USING (auth.role() = 'service_role');

-- 3. Plays (trade log)
CREATE TABLE IF NOT EXISTS plays (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
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
    closed BOOLEAN DEFAULT FALSE,
    exit_price FLOAT,
    exit_date TIMESTAMPTZ,
    pnl FLOAT,
    pnl_pct FLOAT
);

ALTER TABLE plays ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read" ON plays FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON plays FOR ALL USING (auth.role() = 'service_role');

-- 4. Alerts (alert history)
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    ticker TEXT,
    alert_type TEXT,
    message TEXT,
    grade INTEGER,
    council TEXT,
    sent BOOLEAN DEFAULT FALSE
);

ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow anon read" ON alerts FOR SELECT USING (true);
CREATE POLICY "Allow service role all" ON alerts FOR ALL USING (auth.role() = 'service_role');

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);
CREATE INDEX IF NOT EXISTS idx_history_ticker_date ON position_history(ticker, date);
CREATE INDEX IF NOT EXISTS idx_plays_ticker ON plays(ticker);
CREATE INDEX IF NOT EXISTS idx_plays_timestamp ON plays(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
