-- VOX Supabase Schema Setup
-- Run this in Supabase SQL Editor

-- ============================================================
-- WATCHLIST GRADES
-- Stores graded watchlist tickers with entry/exit targets
-- ============================================================
CREATE TABLE IF NOT EXISTS watchlist_grades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    price NUMERIC,
    grade INTEGER CHECK (grade >= 0 AND grade <= 100),
    signal TEXT CHECK (signal IN ('STRONG_BUY', 'BUY', 'HOLD', 'WEAK', 'AVOID')),
    rsi NUMERIC,
    ema21 NUMERIC,
    ema50 NUMERIC,
    atr NUMERIC,
    buy_zone NUMERIC,
    stop_loss NUMERIC,
    target_1 NUMERIC,
    target_2 NUMERIC,
    risk_reward NUMERIC,
    position_size TEXT,
    graded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, graded_at)
);

CREATE INDEX idx_watchlist_grades_ticker ON watchlist_grades(ticker);
CREATE INDEX idx_watchlist_grades_signal ON watchlist_grades(signal);
CREATE INDEX idx_watchlist_grades_grade ON watchlist_grades(grade DESC);

-- ============================================================
-- PORTFOLIO GRADES
-- Stores graded portfolio positions with management targets
-- ============================================================
CREATE TABLE IF NOT EXISTS portfolio_grades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker TEXT NOT NULL,
    price NUMERIC,
    entry_price NUMERIC,
    shares NUMERIC,
    live_value NUMERIC,
    live_pnl NUMERIC,
    pnl_pct NUMERIC,
    grade INTEGER CHECK (grade >= 0 AND grade <= 100),
    signal TEXT CHECK (signal IN ('STRONG_HOLD', 'HOLD', 'WEAK', 'TRIM', 'CUT_LOSS')),
    add_on_zone NUMERIC,
    trailing_stop NUMERIC,
    take_profit_1 NUMERIC,
    take_profit_2 NUMERIC,
    brokers TEXT[],
    graded_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, graded_at)
);

CREATE INDEX idx_portfolio_grades_ticker ON portfolio_grades(ticker);
CREATE INDEX idx_portfolio_grades_signal ON portfolio_grades(signal);
CREATE INDEX idx_portfolio_grades_value ON portfolio_grades(live_value DESC);

-- ============================================================
-- INTELLIGENCE SNAPSHOTS
-- Daily aggregation of all intelligence data
-- ============================================================
CREATE TABLE IF NOT EXISTS intelligence_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    watchlist_count INTEGER,
    portfolio_count INTEGER,
    strong_buy INTEGER,
    buy INTEGER,
    hold INTEGER,
    weak INTEGER,
    trim INTEGER,
    avoid INTEGER,
    avg_grade NUMERIC,
    macro_regime TEXT,
    vix NUMERIC,
    dxy NUMERIC,
    yield_10y NUMERIC,
    top_movers JSONB,
    volume_spikes JSONB,
    news_headlines JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_intelligence_date ON intelligence_snapshots(date DESC);

-- ============================================================
-- BROKER SYNC LOG
-- Tracks when each broker was last synced
-- ============================================================
CREATE TABLE IF NOT EXISTS broker_sync_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    broker TEXT NOT NULL,
    status TEXT,
    position_count INTEGER,
    total_value NUMERIC,
    currency TEXT,
    last_updated TIMESTAMPTZ,
    stale BOOLEAN DEFAULT FALSE,
    error_message TEXT,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(broker, synced_at)
);

CREATE INDEX idx_broker_sync_broker ON broker_sync_log(broker);
CREATE INDEX idx_broker_sync_stale ON broker_sync_log(stale);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- Enable RLS for security
-- ============================================================
ALTER TABLE watchlist_grades ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_grades ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE broker_sync_log ENABLE ROW LEVEL SECURITY;

-- Allow anon read access (for dashboard)
CREATE POLICY "Allow anon read" ON watchlist_grades FOR SELECT TO anon USING (true);
CREATE POLICY "Allow anon read" ON portfolio_grades FOR SELECT TO anon USING (true);
CREATE POLICY "Allow anon read" ON intelligence_snapshots FOR SELECT TO anon USING (true);
CREATE POLICY "Allow anon read" ON broker_sync_log FOR SELECT TO anon USING (true);

-- Allow service role full access
CREATE POLICY "Allow service write" ON watchlist_grades FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow service write" ON portfolio_grades FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow service write" ON intelligence_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Allow service write" ON broker_sync_log FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================
-- CLEANUP OLD DATA (keep 30 days)
-- ============================================================
CREATE OR REPLACE FUNCTION cleanup_old_grades()
RETURNS void AS $$
BEGIN
    DELETE FROM watchlist_grades WHERE graded_at < NOW() - INTERVAL '30 days';
    DELETE FROM portfolio_grades WHERE graded_at < NOW() - INTERVAL '30 days';
    DELETE FROM broker_sync_log WHERE synced_at < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;
