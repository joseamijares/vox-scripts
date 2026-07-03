#!/usr/bin/env python3
"""
VOX Trade Idea Scorer v2
Ranks opportunities by signal strength across all 6 VOX layers.
Fetches live data from Railway Postgres, writes trade_signals table.
"""

import json
import urllib.request
import os
from datetime import datetime, timedelta
import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_unified_grades():
    """Load unified grades from single source of truth"""
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)

def get_unified_grade(ticker, unified_grades):
    """Get grade from unified source"""
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0)
    return 0


DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"


def fetch_positions():
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/positions")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("positions", [])
    except Exception as e:
        print(f"Failed to fetch positions: {e}")
        return []


def fetch_watchlist():
    try:
        req = urllib.request.Request(f"{DASHBOARD_API}/watchlist")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("watchlist", [])
    except Exception as e:
        print(f"Failed to fetch watchlist: {e}")
        return []


def record_cron_run(job_name, status, output, error=None):
    try:
        body = json.dumps({
            "job_name": job_name,
            "status": status,
            "output": output,
            "error": error
        }).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_API}/admin/cron-runs",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Failed to record cron run: {e}")


def write_signals(signals):
    """Write trade signals to Railway Postgres via API."""
    try:
        body = json.dumps({"signals": signals}).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_API}/signals",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"Wrote {result.get('count', 0)} signals to DB")
            return result
    except Exception as e:
        print(f"Failed to write signals: {e}")
        return None


def calculate_composite_score(ticker_data):
    score = 0
    grade = ticker_data.get("grade", 0) or 0
    pnl_pct = ticker_data.get("pnl_pct", 0) or 0
    
    score += min(grade / 100 * 25, 25)
    
    if pnl_pct < -30:
        score += 20
    elif pnl_pct < -15:
        score += 15
    elif pnl_pct < 0:
        score += 10
    elif pnl_pct < 50:
        score += 8
    else:
        score += 3
    
    macro_score = 10 if grade >= 55 else 5
    score += macro_score
    
    sector_score = 10 if grade >= 55 else 5
    score += sector_score
    
    weather_score = 5
    score += weather_score
    
    sentiment_score = 10 if pnl_pct < -20 else 5
    score += sentiment_score
    
    return min(int(score), 100)


def generate_trade_signals():
    positions = fetch_positions()
    watchlist = fetch_watchlist()
    
    signals = []
    
    for p in positions:
        ticker = p.get("ticker", "")
        grade = p.get("grade", 0) or 0
        pnl_pct = p.get("pnl_pct", 0) or 0
        live_price = p.get("live_price", 0) or 0
        
        composite = calculate_composite_score(p)
        
        if grade >= 65 and pnl_pct < 0:
            signal_type = "ADD"
            rationale = f"Grade {grade} but down {pnl_pct:.1f}% — oversold quality"
        elif grade < 45:
            signal_type = "SELL"
            rationale = f"Grade {grade} — below SELL threshold"
        elif pnl_pct > 200:
            signal_type = "TRIM"
            rationale = f"Up {pnl_pct:.0f}% — consider taking profits"
        elif grade >= 55:
            signal_type = "HOLD"
            rationale = f"Grade {grade} — solid position"
        else:
            signal_type = "WATCH"
            rationale = f"Grade {grade} — monitor for improvement"
        
        signals.append({
            "ticker": ticker,
            "signal_type": signal_type,
            "composite_score": composite,
            "technical_score": min(int((pnl_pct + 50) / 100 * 20), 20),
            "fundamental_score": min(int(grade / 100 * 25), 25),
            "macro_score": 10 if grade >= 55 else 5,
            "sector_score": 10 if grade >= 55 else 5,
            "weather_score": 5,
            "sentiment_score": 10 if pnl_pct < -20 else 5,
            "rsi": 0,
            "grade": grade,
            "target_price": live_price * 1.15 if signal_type == "ADD" else live_price * 1.05,
            "stop_price": live_price * 0.85 if signal_type == "ADD" else live_price * 0.90,
            "rationale": rationale
        })
    
    for w in watchlist:
        ticker = w.get("ticker", "")
        grade = w.get("grade", 0) or 0
        entry = w.get("entry_price", 0) or 0
        target = w.get("target_price", 0) or 0
        stop = w.get("stop_loss", 0) or 0
        
        if grade >= 60 and entry > 0:
            composite = calculate_composite_score(w)
            signals.append({
                "ticker": ticker,
                "signal_type": "BUY",
                "composite_score": composite,
                "technical_score": min(int((grade) / 100 * 20), 20),
                "fundamental_score": min(int(grade / 100 * 25), 25),
                "macro_score": 10 if grade >= 55 else 5,
                "sector_score": 10 if grade >= 55 else 5,
                "weather_score": 5,
                "sentiment_score": 5,
                "rsi": 0,
                "grade": grade,
                "target_price": target,
                "stop_price": stop,
                "rationale": f"Watchlist grade {grade} — setup triggered"
            })
    
    signals.sort(key=lambda x: x["composite_score"], reverse=True)
    return signals


if __name__ == "__main__":
    job_name = "vox-trade-scorer"
    try:
        signals = generate_trade_signals()
        
        output_lines = [f"Generated {len(signals)} trade signals"]
        for s in signals[:10]:
            output_lines.append(f"   {s['signal_type']:4} {s['ticker']:6} Score:{s['composite_score']:3}/100 — {s['rationale']}")
        
        output = "\n".join(output_lines)
        print(output)
        
        write_signals(signals)
        record_cron_run(job_name, "ok", output)
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        print(f"{error_msg}")
        record_cron_run(job_name, "error", "", error_msg)
        raise
