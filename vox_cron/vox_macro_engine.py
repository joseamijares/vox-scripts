#!/usr/bin/env python3
"""
VOX Macro Engine

Merges two legacy active crons into a single self-contained entrypoint:
  1. vox_macro_snapshot: FRED API -> macro_signals + market_regime
  2. vox_macro_correlation: yfinance market proxies -> macro_indicators

Usage:
    python /Users/jos/.hermes/scripts/vox_cron/vox_macro_engine.py

Design goals:
  - Single main() that prints a concise summary.
  - Idempotent (UNIQUE constraints + upserts).
  - Environment loaded via hermes_secrets_bootstrap with fallbacks to env vars.
"""
import sys
from pathlib import Path

HERMES_SCRIPTS = str(Path.home() / ".hermes" / "scripts")
if HERMES_SCRIPTS not in sys.path:
    sys.path.insert(0, HERMES_SCRIPTS)
import hermes_secrets_bootstrap  # noqa: E402, F401

import os
import json
from datetime import datetime, date
from typing import Dict, List, Optional

import requests
import psycopg2

try:
    import yfinance as yf
except Exception as import_err:  # pragma: no cover
    yf = None
    print(f"WARNING: yfinance unavailable: {import_err}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
FRED_API_KEY = os.environ.get("FRED_API_KEY")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = int(os.environ.get("DB_PORT", "35577"))
DB_USER = os.environ.get("DB_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "railway")
DB_PASSWORD = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD")
DATABASE_URL = os.environ.get("DATABASE_URL")

# Allow hermes_secrets_bootstrap FRED_API_KEY_KEY pattern used by 1Password loader
if not FRED_API_KEY and hasattr(hermes_secrets_bootstrap, "_load_from_1password"):
    try:
        FRED_API_KEY = hermes_secrets_bootstrap._load_from_1password("FRED_API_KEY")
        if FRED_API_KEY:
            os.environ["FRED_API_KEY"] = FRED_API_KEY
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FRED workflow configuration
# ---------------------------------------------------------------------------
FRED_SERIES = {
    "fed_rate": "DFF",
    "yield_10y": "DGS10",
    "yield_2y": "DGS2",
    "dxy": "DTWEXBGS",
    "vix": "VIXCLS",
    "oil_wti": "DCOILWTICO",
    "copper": "PCOPPUSDM",
}

# Indicator display metadata for signals
FRED_META = {
    "fed_rate": {"sector": "All", "confidence": 50, "source": "FRED"},
    "yield_10y": {"sector": "Fixed Income", "confidence": 50, "source": "FRED"},
    "yield_2y": {"sector": "Fixed Income", "confidence": 50, "source": "FRED"},
    "dxy": {"sector": "FX/Emerging Markets", "confidence": 50, "source": "FRED"},
    "vix": {"sector": "Equities", "confidence": 50, "source": "FRED"},
    "oil_wti": {"sector": "Energy", "confidence": 50, "source": "FRED"},
    "copper": {"sector": "Materials", "confidence": 50, "source": "FRED"},
}


# ---------------------------------------------------------------------------
# Market-based macro indicator configuration
# ---------------------------------------------------------------------------
MACRO_INDICATORS = {
    "DXY": "UUP",
    "VIX": "^VIX",
    "T10Y": "^TNX",
    "T2Y": "^IRX",
    "GOLD": "GLD",
    "OIL": "USO",
    "HYG": "HYG",
    "LQD": "LQD",
}


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    """Return a psycopg2 connection using env vars or DATABASE_URL."""
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    if not DB_PASSWORD:
        raise RuntimeError("DB_PASSWORD or PGPASSWORD not set")
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


def ensure_tables(conn):
    """Idempotent table creation for macro_signals, market_regime, macro_indicators."""
    cur = conn.cursor()
    cur.execute(
        """
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
        """
    )
    cur.execute(
        """
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
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS macro_indicators (
            id SERIAL PRIMARY KEY,
            indicator_name VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            snapshot_date DATE NOT NULL,
            price NUMERIC(10,4),
            change_1d NUMERIC(8,4),
            change_1w NUMERIC(8,4),
            change_1m NUMERIC(8,4),
            level VARCHAR(20),
            signal VARCHAR(50),
            impact_score NUMERIC(5,2),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(indicator_name, snapshot_date)
        )
        """
    )
    conn.commit()
    cur.close()


# ---------------------------------------------------------------------------
# FRED workflow
# ---------------------------------------------------------------------------
def fetch_fred_api(series_id: str) -> Dict:
    """Fetch latest FRED observation via API."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not set")

    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}"
        f"&api_key={FRED_API_KEY}"
        "&file_type=json"
        "&sort_order=desc"
        "&limit=30"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    observations = data.get("observations", [])
    if not observations:
        raise ValueError(f"No observations for {series_id}")

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


def signal_from_change(change_1m: float) -> str:
    if change_1m > 5:
        return "BEARISH"
    if change_1m < -5:
        return "BULLISH"
    return "NEUTRAL"


def run_fred_workflow(conn) -> Dict:
    """Fetch FRED series and upsert into macro_signals + market_regime."""
    cur = conn.cursor()
    results: Dict[str, Dict] = {}

    for signal_name, series_id in FRED_SERIES.items():
        try:
            data = fetch_fred_api(series_id)
            value = data["value"]
            change_1m = data["change_1m_pct"]
            signal = signal_from_change(change_1m)
            meta = FRED_META.get(signal_name, {"sector": "All", "confidence": 50, "source": "FRED"})

            cur.execute(
                """
                INSERT INTO macro_signals
                    (signal_name, signal_value, signal_direction, impact_sector, confidence, source, computed_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (signal_name) DO UPDATE SET
                    signal_value = EXCLUDED.signal_value,
                    signal_direction = EXCLUDED.signal_direction,
                    impact_sector = EXCLUDED.impact_sector,
                    confidence = EXCLUDED.confidence,
                    source = EXCLUDED.source,
                    computed_at = EXCLUDED.computed_at
                """,
                (signal_name, value, signal, meta["sector"], meta["confidence"], meta["source"]),
            )
            results[signal_name] = {
                "value": round(value, 3),
                "change_1m_pct": round(change_1m, 3),
                "signal": signal,
            }
        except Exception as e:
            results[signal_name] = {"error": str(e)}
            print(f"WARNING: FRED {signal_name} ({series_id}) failed: {e}", file=sys.stderr)

    # Regime classification from signals updated today
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

    vix_val = results.get("vix", {}).get("value", 0)
    yield_10y = results.get("yield_10y", {}).get("value", 0)
    yield_2y = results.get("yield_2y", {}).get("value", 0)
    yield_spread = yield_10y - yield_2y

    cur.execute(
        """
        INSERT INTO market_regime
            (regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """,
        (
            regime,
            score,
            float(vix_val),
            "Sideways",
            float(yield_spread),
            "Holding",
            "Mixed signals across macro indicators",
        ),
    )

    conn.commit()
    cur.close()

    return {
        "signals": results,
        "regime": regime,
        "regime_score": score,
        "recorded_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Market-based macro indicator workflow
# ---------------------------------------------------------------------------
def fetch_yfinance_data(ticker: str, name: str) -> Optional[Dict]:
    """Fetch 1m price history and compute changes."""
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist.empty:
            return None

        current = float(hist["Close"].iloc[-1])
        prev_1d = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current
        prev_1w = float(hist["Close"].iloc[-5]) if len(hist) >= 5 else current
        prev_1m = float(hist["Close"].iloc[0]) if len(hist) >= 1 else current

        return {
            "price": current,
            "change_1d": ((current - prev_1d) / prev_1d) * 100 if prev_1d > 0 else 0,
            "change_1w": ((current - prev_1w) / prev_1w) * 100 if prev_1w > 0 else 0,
            "change_1m": ((current - prev_1m) / prev_1m) * 100 if prev_1m > 0 else 0,
        }
    except Exception as e:
        print(f"WARNING: yfinance {name} ({ticker}) failed: {e}", file=sys.stderr)
        return None


def calculate_level(name: str, price: float, change_1m: float) -> str:
    levels = {
        "VIX": [("extreme", 30), ("high", 20), ("normal", 15)],
        "DXY": [("extreme", 105), ("high", 100), ("normal", 95)],
        "T10Y": [("extreme", 5.0), ("high", 4.5), ("normal", 3.5)],
    }
    if name in levels:
        for level, threshold in levels[name]:
            if price > threshold:
                return level
        return "low"
    if abs(change_1m) > 10:
        return "extreme"
    if abs(change_1m) > 5:
        return "high" if change_1m > 0 else "low"
    return "normal"


def calculate_signal(name: str, price: float, change_1d: float, change_1w: float, change_1m: float) -> str:
    signals: List[str] = []
    if name == "VIX":
        if price > 25:
            signals.append("High fear — defensive positioning")
        elif price < 15:
            signals.append("Complacency — consider hedges")
        elif change_1w > 10:
            signals.append("Fear accelerating")
    elif name == "DXY":
        if change_1w > 1:
            signals.append("Dollar strengthening — headwinds for EM/intl")
        elif change_1w < -1:
            signals.append("Dollar weakening — tailwinds for EM/intl")
    elif name == "T10Y":
        if change_1w > 0.2:
            signals.append("Rates rising — pressure on growth stocks")
        elif change_1w < -0.2:
            signals.append("Rates falling — tailwinds for growth")
    elif name == "GOLD":
        if change_1w > 2:
            signals.append("Safe haven demand — risk-off signal")
    elif name == "HYG":
        if change_1w < -1:
            signals.append("Credit stress — risk-off signal")
    return "; ".join(signals) if signals else "Neutral"


def calculate_impact_score(name: str, change_1w: float, level: str) -> float:
    score = 0.0
    if name == "VIX":
        score = -5 if change_1w > 10 else -2 if change_1w > 5 else 0
    elif name == "DXY":
        score = -3 if change_1w > 1 else 2 if change_1w < -1 else 0
    elif name == "T10Y":
        score = -4 if change_1w > 0.3 else 2 if change_1w < -0.2 else 0
    elif name == "GOLD":
        score = -3 if change_1w > 2 else 0
    elif name == "HYG":
        score = -4 if change_1w < -1 else 0
    if level == "extreme":
        score *= 1.5
    return max(-10.0, min(10.0, score))


def run_market_macro_workflow(conn) -> Dict:
    """Fetch market proxies and upsert into macro_indicators."""
    cur = conn.cursor()
    today = date.today()
    results: Dict[str, Dict] = {}

    for name, ticker in MACRO_INDICATORS.items():
        data = fetch_yfinance_data(ticker, name)
        if not data:
            continue

        level = calculate_level(name, data["price"], data["change_1m"])
        signal = calculate_signal(name, data["price"], data["change_1d"], data["change_1w"], data["change_1m"])
        impact = calculate_impact_score(name, data["change_1w"], level)

        cur.execute(
            """
            INSERT INTO macro_indicators
                (indicator_name, ticker, snapshot_date, price, change_1d, change_1w, change_1m,
                 level, signal, impact_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (indicator_name, snapshot_date) DO UPDATE SET
                price = EXCLUDED.price,
                change_1d = EXCLUDED.change_1d,
                change_1w = EXCLUDED.change_1w,
                change_1m = EXCLUDED.change_1m,
                level = EXCLUDED.level,
                signal = EXCLUDED.signal,
                impact_score = EXCLUDED.impact_score,
                created_at = NOW()
            """,
            (
                name,
                ticker,
                today,
                data["price"],
                data["change_1d"],
                data["change_1w"],
                data["change_1m"],
                level,
                signal,
                impact,
            ),
        )
        results[name] = {
            "ticker": ticker,
            "price": round(data["price"], 4),
            "change_1d": round(data["change_1d"], 4),
            "change_1w": round(data["change_1w"], 4),
            "change_1m": round(data["change_1m"], 4),
            "level": level,
            "signal": signal,
            "impact": round(impact, 2),
        }

    conn.commit()
    cur.close()

    # Aggregate macro composite score from today's indicators
    total_impact = round(sum(d["impact"] for d in results.values()), 1)
    risk_off_signals = sum(1 for d in results.values() if d["impact"] < -3)

    return {
        "indicators": results,
        "total_impact": total_impact,
        "risk_off_signals": risk_off_signals,
        "recorded_at": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def main() -> int:
    """Run both macro workflows and print a concise summary."""
    start = datetime.utcnow()
    fred_report = {}
    market_report = {}
    errors: List[str] = []

    try:
        conn = get_db()
    except Exception as e:
        print(f"ERROR: Failed to connect to DB: {e}", file=sys.stderr)
        return 1

    ensure_tables(conn)

    # Workflow 1: FRED
    try:
        fred_report = run_fred_workflow(conn)
    except Exception as e:
        errors.append(f"FRED workflow: {e}")
        print(f"ERROR: FRED workflow failed: {e}", file=sys.stderr)

    # Workflow 2: Market-based indicators
    try:
        market_report = run_market_macro_workflow(conn)
    except Exception as e:
        errors.append(f"Market macro workflow: {e}")
        print(f"ERROR: Market macro workflow failed: {e}", file=sys.stderr)

    conn.close()

    duration = (datetime.utcnow() - start).total_seconds()
    fred_ok = sum(1 for v in fred_report.get("signals", {}).values() if "error" not in v)
    fred_total = len(FRED_SERIES)
    market_total = len(market_report.get("indicators", {}))
    total_impact = market_report.get("total_impact", 0)
    risk_off = market_report.get("risk_off_signals", 0)
    regime = fred_report.get("regime", "UNKNOWN")

    # Concise summary lines
    print("=" * 70)
    print(f"VOX Macro Engine — {start.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print("=" * 70)
    print(f"FRED signals: {fred_ok}/{fred_total} updated | Regime: {regime}")
    print(f"Market indicators: {market_total}/{len(MACRO_INDICATORS)} updated | Impact: {total_impact:+.1f} | Risk-off: {risk_off}")
    if errors:
        print(f"Errors: {len(errors)}")
    print(f"Duration: {duration:.1f}s")
    print("=" * 70)

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
