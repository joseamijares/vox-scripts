-- Migration 002: OpenRouter LLM cost indexes and budget table

-- Indexes for vox_llm_costs dashboard queries
CREATE INDEX IF NOT EXISTS idx_vox_llm_costs_run_at ON vox_llm_costs (run_at DESC);
CREATE INDEX IF NOT EXISTS idx_vox_llm_costs_model ON vox_llm_costs (model);
CREATE INDEX IF NOT EXISTS idx_vox_llm_costs_script ON vox_llm_costs (script_name);

-- Monthly budget configuration table
CREATE TABLE IF NOT EXISTS vox_llm_budget (
    month DATE NOT NULL PRIMARY KEY, -- first day of month
    cap_usd NUMERIC(10,2) NOT NULL DEFAULT 20.00,
    alert_threshold_usd NUMERIC(10,2) NOT NULL DEFAULT 15.00,
    pause_threshold_usd NUMERIC(10,2) NOT NULL DEFAULT 18.00,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Seed current month's budget row if absent
INSERT INTO vox_llm_budget (month, cap_usd, alert_threshold_usd, pause_threshold_usd)
VALUES (DATE_TRUNC('month', NOW())::DATE, 20.00, 15.00, 18.00)
ON CONFLICT (month) DO NOTHING;
