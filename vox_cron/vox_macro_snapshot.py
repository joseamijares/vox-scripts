#!/usr/bin/env python3
"""
VOX Macro Snapshot v2
Fetches FRED data via API (not CSV scraping) and populates macro_signals + market_regime tables.
Run daily at 6 AM CT via cron.
"""
import os
import json
import sys
from datetime import datetime

import requests
import psycopg2

# Load env from ~/.hermes/.env (cron jobs don't inherit shell env)
ENV_PATH = os.path.expanduser("~/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

# Fallback to ~/.hermes/.env
HERMES_ENV = os.path.expanduser("~/.hermes/.env")
if os.path.exists(HERMES_ENV):
    with open(HERMES_ENV) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")
FRED_API_KEY = os.environ.get("FRED_API_KEY")

FRED_SERIES = {
    "fed_rate": "DFF",
    "yield_10y": "DGS10",
    "yield_2y": "DGS2",
    "dxy": "DTWEXBGS",
    "vix": "VIXCLS",
    "oil_wti": "DCOILWTICO",
    "copper": "PCOPPUSDM",
}


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def fetch_fred_api(series_id):
    """Fetch latest observation from FRED API using API key."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not found in environment")

    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_API_KEY}"
        f"&file_type=json"
        f"&sort_order=desc"
        f"&limit=30"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    observations = data.get("observations", [])
    if not observations:
        raise ValueError(f"No observations for {series_id}")

    # Filter out missing values
    valid = [obs for obs in observations if obs["value"] != "."]
    if len(valid) < 2:
        raise ValueError(f"Not enough valid observations for {series_id}")

    latest = valid[0]
    prev_day = valid[1]
    prev_month = valid[min(22, len(valid) - 1)]

    value = float(latest["value"])
    prev_day_val = float(prev_day["value"])
    prev_month_val = float(prev_month["value"])

    change_1d = ((value - prev_day_val) / prev_day_val) * 100 if prev_day_val != 0 else 0
    change_1m = ((value - prev_month_val) / prev_month_val) * 100 if prev_month_val != 0 else 0

    return {
        "value": value,
        "change_1d_pct": change_1d,
        "change_1m_pct": change_1m,
        "date": latest["date"],
    }


def signal_from_change(change_1m):
    if change_1m > 5:
        return "BEARISH"
    if change_1m < -5:
        return "BULLISH"
    return "NEUTRAL"


def ensure_tables(conn):
    cur = conn.cursor()
    # Use the schema that matches the dashboard API
    cur.execute("""
        CREATE TABLE IF NOT EXISTS macro_signals (
            id SERIAL PRIMARY KEY,
            signal_name TEXT UNIQUE,
            signal_value NUMERIC,
            signal_direction TEXT,
            impact_sector TEXT DEFAULT 'All',
            confidence INTEGER DEFAULT 50,
            source TEXT DEFAULT 'FRED',
            computed_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS market_regime (
            id SERIAL PRIMARY KEY,
            regime TEXT,
            confidence NUMERIC,
            vix_level NUMERIC,
            spy_trend TEXT,
            yield_curve NUMERIC,
            fed_stance TEXT,
            description TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()


def run_macro_snapshot():
    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    conn = get_db()
    ensure_tables(conn)
    cur = conn.cursor()
    results = {}

    for signal_name, series_id in FRED_SERIES.items():
        try:
            data = fetch_fred_api(series_id)
            value = data["value"]
            change_1d = data["change_1d_pct"]
            change_1m = data["change_1m_pct"]
            signal = signal_from_change(change_1m)

            cur.execute("""
                INSERT INTO macro_signals (signal_name, signal_value, signal_direction, impact_sector, confidence, source, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (signal_name) DO UPDATE SET
                    signal_value = EXCLUDED.signal_value,
                    signal_direction = EXCLUDED.signal_direction,
                    impact_sector = EXCLUDED.impact_sector,
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    computed_at = EXCLUDED.computed_at
            """, (signal_name, value, signal, "All", 50, "FRED"))

            results[signal_name] = {
                "value": round(value, 3),
                "change_1d_pct": round(change_1d, 3),
                "change_1m_pct": round(change_1m, 3),
                "signal": signal,
            }
        except Exception as e:
            results[signal_name] = {"error": str(e)}
            print(f"WARNING: Failed to fetch {signal_name} ({series_id}): {e}", file=sys.stderr)

    # Determine regime
    cur.execute(
        "SELECT signal_name, signal_direction FROM macro_signals WHERE computed_at > NOW() - INTERVAL '1 day'"
    )
    signals = dict(cur.fetchall())

    bearish = sum(1 for s in signals.values() if s == "BEARISH")
    bullish = sum(1 for s in signals.values() if s == "BULLISH")

    if bearish >= 4:
        regime, score = "RISK_OFF", 75
    elif bullish >= 4:
        regime, score = "RISK_ON", 75
    else:
        regime, score = "NEUTRAL", 50

    # Get VIX and yield spread for regime record
    vix_val = results.get("vix", {}).get("value", 0)
    if isinstance(vix_val, dict):
        vix_val = 0
    yield_10y = results.get("yield_10y", {}).get("value", 0)
    if isinstance(yield_10y, dict):
        yield_10y = 0
    yield_2y = results.get("yield_2y", {}).get("value", 0)
    if isinstance(yield_2y, dict):
        yield_2y = 0
    yield_spread = yield_10y - yield_2y

    cur.execute("""
        INSERT INTO market_regime (regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    """, (regime, score, float(vix_val), "Sideways", float(yield_spread), "Holding", "Mixed signals across macro indicators"))

    conn.commit()
    cur.close()
    conn.close()

    return {
        "signals": results,
        "regime": regime,
        "regime_score": score,
        "recorded_at": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    report = run_macro_snapshot()
    print(json.dumps(report, indent=2))
    sys.exit(0)
