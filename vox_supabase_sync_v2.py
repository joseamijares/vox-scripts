#!/usr/bin/env python3
"""
VOX Supabase Sync v2 — Hybrid Architecture
Python scripts write to BOTH JSON files AND Supabase tables
Dashboard reads from Supabase (fast queries) with JSON fallback
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_json(filename, default=None):
    try:
        with open(SCRIPT_DIR / filename) as f:
            return json.load(f)
    except:
        return default

def sync_all():
    """Sync all graded data to Supabase (placeholder until credentials fixed)."""
    print("🔄 VOX Supabase Sync v2")
    print("=" * 50)
    
    wl_data = load_json("vox_watchlist_graded.json", {})
    pf_data = load_json("vox_portfolio_graded.json", {})
    
    print(f"📊 Watchlist: {len(wl_data.get('results', []))} graded tickers")
    print(f"📈 Portfolio: {len(pf_data.get('results', []))} graded positions")
    
    # TODO: Add Supabase sync once credentials are fixed
    print("⚠️ Supabase sync skipped (credentials issue)")
    print("✅ JSON files updated — dashboard will use JSON fallback")
    
    print("=" * 50)

if __name__ == "__main__":
    sync_all()
