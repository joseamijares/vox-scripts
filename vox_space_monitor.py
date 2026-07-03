#!/usr/bin/env python3
"""
VOX Space Sector Monitor Script
Generates space sector snapshot and saves to vox_space_monitor.json
Called by cron job vox-space-sector-monitor
"""
import yfinance as yf
import json
from datetime import datetime, timezone
from pathlib import Path

space_tickers = ["RKLB", "ASTS", "SPCE", "SPIR", "MNTS", "SIDU", "BKSY", "PL", "SATL", "LUNR", "RDW"]

results = []
errors = []

for ticker in space_tickers:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="30d")
        
        if hist.empty:
            errors.append(ticker)
            continue
        
        current = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
        change = (current - prev) / prev * 100 if prev else 0
        
        high_52 = info.get("fiftyTwoWeekHigh", 0)
        low_52 = info.get("fiftyTwoWeekLow", 0)
        pct_from_high = (current - high_52) / high_52 * 100 if high_52 else 0
        
        vol = float(hist["Volume"].iloc[-1]) if len(hist) > 0 else 0
        avg_vol = float(hist["Volume"].mean()) if len(hist) > 0 else 0
        vol_ratio = vol / avg_vol if avg_vol else 1
        
        mcap = info.get("marketCap", 0)
        
        # Load grade from watchlist graded
        graded_path = Path.home() / ".hermes" / "scripts" / "vox_watchlist_graded.json"
        grade = None
        if graded_path.exists():
            with open(graded_path) as f:
                graded = json.load(f)
            for r in graded.get("results", []):
                if r["ticker"] == ticker:
                    grade = r["grade"]
                    break
        
        results.append({
            "ticker": ticker,
            "price": round(current, 2),
            "change_pct": round(change, 2),
            "grade": grade,
            "mcap_b": round(mcap / 1e9, 2) if mcap else None,
            "pct_from_high": round(pct_from_high, 1),
            "vol_ratio": round(vol_ratio, 2)
        })
    except Exception as e:
        errors.append(f"{ticker}: {e}")

# Save
monitor_path = Path.home() / ".hermes" / "scripts" / "vox_space_monitor.json"
with open(monitor_path, "w") as f:
    json.dump({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sector": "Space",
        "tickers": results,
        "errors": errors
    }, f, indent=2)

print(f"Space monitor updated: {len(results)} tickers, {len(errors)} errors")
if errors:
    print(f"Errors: {errors}")
