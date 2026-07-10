-- VOX AlphaModel / SignalContract migration
-- Adopts virattt/ai-hedge-fund Analyst -> Signal contract on top of existing VOX tables.
-- 2026-07-10

-- 1. Analyst registry (config-as-data)
CREATE TABLE IF NOT EXISTS analysts (
    analyst_id      TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    source_table    TEXT NOT NULL,          -- vox_grades | technical_signals | macro_signals | insider_trades | trader_calls | earnings_calendar | grade_alerts
    category        TEXT NOT NULL,          -- grade | insider | macro | technical | earnings | trader | alert
    version         TEXT NOT NULL,          -- semver e.g. 1.0.0
    params          JSONB DEFAULT '{}',
    active          BOOLEAN DEFAULT TRUE,
    backtest_sharpe NUMERIC(8,4),
    backtest_hit_rate NUMERIC(5,4),
    last_validated_at TIMESTAMPTZ,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- 2. Normalized Signal contract
CREATE TABLE IF NOT EXISTS signals_normalized (
    id              BIGSERIAL PRIMARY KEY,
    analyst_id      TEXT NOT NULL REFERENCES analysts(analyst_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    as_of_date      DATE NOT NULL,           -- point-in-time date the signal was valid for
    generated_at    TIMESTAMPTZ NOT NULL,    -- when it was actually computed (lookahead audit)
    signal          TEXT NOT NULL,           -- bullish | bearish | neutral
    score           NUMERIC(4,3),            -- -1.0 to +1.0
    confidence      NUMERIC(4,3),            -- 0 to 1
    rationale       TEXT,
    inputs_hash     TEXT NOT NULL,           -- dedupe / reproducibility
    source_table    TEXT NOT NULL,
    source_id       BIGINT,                  -- loose FK into originating row
    raw_inputs      JSONB,
    ingested_at     TIMESTAMPTZ DEFAULT now(),
    UNIQUE(analyst_id, ticker, as_of_date, inputs_hash)
);
CREATE INDEX IF NOT EXISTS idx_signals_norm_ticker_date ON signals_normalized(ticker, as_of_date);
CREATE INDEX IF NOT EXISTS idx_signals_norm_analyst_date ON signals_normalized(analyst_id, as_of_date);
CREATE INDEX IF NOT EXISTS idx_signals_norm_ingested ON signals_normalized(ingested_at);

-- 3. Backtest run registry
CREATE TABLE IF NOT EXISTS backtest_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analyst_id      TEXT REFERENCES analysts(analyst_id),
    strategy_config JSONB,
    start_date      DATE NOT NULL,
    end_date        DATE NOT NULL,
    universe        TEXT,                    -- 'all_positions' | 'sp500' | custom ticker list
    status          TEXT DEFAULT 'pending',  -- pending | running | complete | failed
    metrics         JSONB,
    error_log       TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_analyst ON backtest_runs(analyst_id, created_at);

-- 4. Synthetic backtest trades
CREATE TABLE IF NOT EXISTS backtest_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
    ticker          TEXT NOT NULL,
    signal_id       BIGINT REFERENCES signals_normalized(id),
    entry_date      DATE NOT NULL,
    entry_price     NUMERIC(12,4),
    exit_date       DATE,
    exit_price      NUMERIC(12,4),
    holding_days    INT,
    pnl_pct         NUMERIC(10,4),
    exit_reason     TEXT,                    -- horizon_hit | stop_loss | signal_reversal | end_of_backtest
    raw_return_bps  INT,                     -- basis points
    metadata        JSONB
);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(run_id, ticker);

-- 5. Bridge existing signal_performance to backtest runs
ALTER TABLE signal_performance
    ADD COLUMN IF NOT EXISTS backtest_run_id UUID REFERENCES backtest_runs(run_id),
    ADD COLUMN IF NOT EXISTS analyst_id TEXT REFERENCES analysts(analyst_id);

-- 6. Prepare positions for future mode-aware ledger
ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'live' CHECK (mode IN ('live', 'paper', 'backtest'));

-- 7. Ensure generated_at audit exists on source tables where missing
ALTER TABLE vox_grades         ADD COLUMN IF NOT EXISTS data_available_at TIMESTAMPTZ;
ALTER TABLE unified_grades     ADD COLUMN IF NOT EXISTS data_available_at TIMESTAMPTZ;
ALTER TABLE technical_signals  ADD COLUMN IF NOT EXISTS data_available_at TIMESTAMPTZ;
ALTER TABLE macro_signals      ADD COLUMN IF NOT EXISTS data_available_at TIMESTAMPTZ;
ALTER TABLE trader_calls       ADD COLUMN IF NOT EXISTS data_available_at TIMESTAMPTZ;
-- insider_trades already has transaction_date; filing_date is used in adapter

-- 8. Seed initial analysts
INSERT INTO analysts (analyst_id, display_name, source_table, category, version, params, notes)
VALUES
    ('vox_grade_v1', 'VOX Grade Signal', 'vox_grades', 'grade', '1.0.0', '{"action_map":{"BUY":1,"HOLD":0,"SELL":-1}}', 'Maps vox_grade and action to a directional signal'),
    ('unified_grade_v1', 'Unified Grade Signal', 'unified_grades', 'grade', '1.0.0', '{"action_map":{"BUY":1,"HOLD":0,"SELL":-1}}', 'Maps unified_grade and action to a directional signal'),
    ('technical_alpha_v1', 'Technical Signal Alpha', 'technical_signals', 'technical', '1.0.0', '{"score_threshold":60}', 'Maps technical score to bullish/bearish with regime conditioning'),
    ('macro_tilt_v1', 'Macro Tilt Filter', 'macro_signals', 'macro', '1.0.0', '{}', 'Portfolio-level macro regime filter'),
    ('insider_cluster_v1', 'Insider Cluster Buy', 'insider_trades', 'insider', '1.0.0', '{"window_days":30,"min_insiders":2,"min_value":100000}', 'Cluster insider buying over 30-day window'),
    ('trader_call_v1', 'Trader Call Signal', 'trader_calls', 'trader', '1.0.0', '{}', 'Maps trader calls to directional signal'),
    ('grade_alert_v1', 'Grade Swing Alert', 'grade_alerts', 'alert', '1.0.0', '{"min_delta":20}', 'Grade-swing alerts with magnitude threshold')
ON CONFLICT (analyst_id) DO NOTHING;
