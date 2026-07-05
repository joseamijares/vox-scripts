-- Migration 001: reliable price history tables

-- Adapt to existing legacy schema if present; otherwise create new canonical schema.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'price_history'
    ) THEN
        CREATE TABLE price_history (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            date DATE NOT NULL,
            open NUMERIC(12,4),
            high NUMERIC(12,4),
            low NUMERIC(12,4),
            close NUMERIC(12,4) NOT NULL,
            volume BIGINT,
            adj_close NUMERIC(12,4),
            source VARCHAR(20) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (ticker, date, source)
        );
    ELSE
        -- Ensure legacy columns match canonical names if they differ
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'date'
        ) THEN
            ALTER TABLE price_history RENAME COLUMN price_date TO date;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'open'
        ) THEN
            ALTER TABLE price_history RENAME COLUMN open_price TO open;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'high'
        ) THEN
            ALTER TABLE price_history RENAME COLUMN high_price TO high;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'low'
        ) THEN
            ALTER TABLE price_history RENAME COLUMN low_price TO low;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'close'
        ) THEN
            ALTER TABLE price_history RENAME COLUMN close_price TO close;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'price_history' AND column_name = 'source'
        ) THEN
            ALTER TABLE price_history ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'yahoo';
        END IF;
        -- Ensure unique constraint matches (ticker, date)
        IF NOT EXISTS (
            SELECT 1 FROM pg_indexes
            WHERE tablename = 'price_history' AND indexdef LIKE '%(ticker, date)%'
        ) THEN
            ALTER TABLE price_history ADD CONSTRAINT price_history_ticker_date_key UNIQUE (ticker, date);
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_price_history_ticker_date ON price_history (ticker, date DESC);

CREATE TABLE IF NOT EXISTS price_unavailable (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    reason TEXT,
    last_failed_at TIMESTAMP DEFAULT NOW(),
    created_at TIMESTAMP DEFAULT NOW()
);

ALTER TABLE signal_performance
ADD COLUMN IF NOT EXISTS return_1d NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS return_5d NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS return_20d NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS return_60d NUMERIC(10,4),
ADD COLUMN IF NOT EXISTS return_method VARCHAR(20) DEFAULT 'live_price';
