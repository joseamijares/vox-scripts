#!/usr/bin/env python3
"""
VOX Supabase Sync Module
Handles all Supabase read/write operations.
Scripts import this instead of direct JSON writes.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from supabase import create_client

# Load credentials from .env
SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

ENV = load_env()
SUPABASE_URL = ENV.get("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")

# Fallback to hardcoded (for now, will be removed after .env update)
if not SUPABASE_URL:
    SUPABASE_URL = "https://msvcrlijclhuifdjjmyy.supabase.co"
if not SUPABASE_KEY:
    SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1zdmNybGlqY2xodWlmZGpqbXl5Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3OTc5OTk2NiwiZXhwIjoyMDk1Mzc1OTY2fQ.RVGnYGVr88ZXNddPaiBJrRGg9knoVNKVeq8QqT5o7G8"

_supabase = None

def get_client():
    global _supabase
    if _supabase is None:
        _supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase


def sync_positions(positions_data):
    """Sync positions to Supabase (upsert)."""
    sb = get_client()
    
    records = []
    for p in positions_data:
        if p.get("ticker") == "TOTAL":
            continue
        
        records.append({
            "ticker": p.get("ticker", ""),
            "shares": p.get("shares", 0) or p.get("quantity", 0),
            "avg_cost": p.get("cost_basis", 0) or p.get("avg_cost", 0),
            "live_price": p.get("live_price", 0),
            "live_value": p.get("live_value", p.get("value", 0)),
            "grade": p.get("grade", 0),
            "council": p.get("council", ""),
            "brokers": p.get("brokers", []),
            "sector": p.get("sector", ""),
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Upsert in batches
    batch_size = 50
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            sb.table("positions").upsert(batch, on_conflict="ticker").execute()
        except Exception as e:
            print(f"   ⚠️ Batch upsert failed: {e}")
            # Fallback: upsert one by one
            for rec in batch:
                try:
                    sb.table("positions").upsert(rec, on_conflict="ticker").execute()
                except Exception as e2:
                    print(f"   ⚠️ Failed to upsert {rec.get('ticker')}: {e2}")
    
    return len(records)


def sync_play(play_dict):
    """Sync a single play to Supabase."""
    sb = get_client()
    
    record = {
        "ticker": play_dict["ticker"],
        "action": play_dict["action"],
        "shares": play_dict["shares"],
        "price": play_dict["price"],
        "notional": play_dict.get("notional", play_dict["shares"] * play_dict["price"]),
        "broker": play_dict.get("broker", ""),
        "reason": play_dict.get("reason", ""),
        "grade_at_entry": play_dict.get("grade_at_entry", 0),
        "council_at_entry": play_dict.get("council_at_entry", ""),
        "notes": play_dict.get("notes", ""),
        "closed": play_dict.get("closed", False),
        "exit_price": play_dict.get("exit_price"),
        "exit_date": play_dict.get("exit_date"),
        "pnl": play_dict.get("pnl"),
        "pnl_pct": play_dict.get("pnl_pct")
    }
    
    sb.table("plays").insert(record).execute()
    return record


def sync_watchlist(watchlist_data):
    """Sync watchlist to Supabase (upsert). Matches existing schema."""
    sb = get_client()
    
    records = []
    for w in watchlist_data:
        # Extract sources as string for notes
        sources = w.get("sources", [])
        notes = " | ".join(sources) if sources else ""
        
        records.append({
            "ticker": w.get("ticker", ""),
            "name": w.get("ticker", ""),  # Use ticker as name fallback
            "sector": w.get("sector", ""),  # Now populated from thematic sectors
            "thesis": notes[:200],
            "entry_price": w.get("buy_zone", 0),
            "target_price": w.get("target_1", 0),
            "stop_loss": w.get("stop_loss", 0),
            "grade": w.get("grade", 0),
            "council": w.get("signal", ""),
            "status": "watching",  # Use 'watching' to match dashboard filter
            "added_at": w.get("added_at", datetime.now(timezone.utc).isoformat()),
            "notes": notes[:500]
        })
    
    # Upsert in batches — use on_conflict to handle duplicates
    batch_size = 50
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        try:
            sb.table("watchlist").upsert(batch, on_conflict="ticker").execute()
        except Exception as e:
            # Fallback: update existing records one by one
            for rec in batch:
                try:
                    sb.table("watchlist").upsert(rec, on_conflict="ticker").execute()
                except:
                    pass
    
    return len(records)


def get_watchlist():
    """Get all watchlist entries from Supabase."""
    sb = get_client()
    response = sb.table("watchlist").select("*").execute()
    return response.data


def get_positions():
    """Get all positions from Supabase."""
    sb = get_client()
    response = sb.table("positions").select("*").execute()
    return response.data


def get_plays():
    """Get all plays from Supabase."""
    sb = get_client()
    response = sb.table("plays").select("*").execute()
    return response.data


def snapshot_to_history(date_str=None):
    """Copy current positions to history table."""
    sb = get_client()
    
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    positions = get_positions()
    
    records = []
    for p in positions:
        records.append({
            "ticker": p["ticker"],
            "date": date_str,
            "shares": p.get("shares", 0),
            "price": p.get("live_price", 0),
            "value": p.get("live_value", 0),
            "grade": p.get("grade", 0),
            "council": p.get("council", "")
        })
    
    # Upsert to avoid duplicates
    sb.table("position_history").upsert(records).execute()
    return len(records)


if __name__ == "__main__":
    # Test
    print("Testing Supabase sync...")
    positions = get_positions()
    print(f"Loaded {len(positions)} positions from Supabase")
    plays = get_plays()
    print(f"Loaded {len(plays)} plays from Supabase")
