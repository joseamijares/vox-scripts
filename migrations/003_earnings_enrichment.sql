-- VOX Earnings enrichment migration
-- Idempotent: adds columns to existing earnings_calendar and creates new tables.

ALTER TABLE earnings_calendar
ADD COLUMN IF NOT EXISTS eps_actual NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS revenue_actual NUMERIC(15,2),
ADD COLUMN IF NOT EXISTS surprise_pct NUMERIC(8,4),
ADD COLUMN IF NOT EXISTS data_source VARCHAR(20) DEFAULT 'yfinance',
ADD COLUMN IF NOT EXISTS importance_score INT DEFAULT 0,
ADD COLUMN IF NOT EXISTS analyst_revision VARCHAR(20);

CREATE INDEX IF NOT EXISTS idx_earnings_report_date ON earnings_calendar (report_date);
CREATE INDEX IF NOT EXISTS idx_earnings_status ON earnings_calendar (status);

CREATE TABLE IF NOT EXISTS earnings_surprises (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    report_date DATE NOT NULL,
    eps_estimate NUMERIC(10,4),
    eps_actual NUMERIC(10,4),
    surprise_pct NUMERIC(8,4),
    revenue_estimate NUMERIC(15,2),
    revenue_actual NUMERIC(15,2),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (ticker, report_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_surprises_ticker ON earnings_surprises (ticker, report_date);

CREATE TABLE IF NOT EXISTS earnings_analyst_sentiment (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    report_date DATE NOT NULL,
    strong_buy INT DEFAULT 0,
    buy INT DEFAULT 0,
    hold INT DEFAULT 0,
    sell INT DEFAULT 0,
    strong_sell INT DEFAULT 0,
    mean_rating NUMERIC(4,2),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (ticker, report_date)
);

CREATE INDEX IF NOT EXISTS idx_earnings_sentiment_ticker ON earnings_analyst_sentiment (ticker, report_date);
