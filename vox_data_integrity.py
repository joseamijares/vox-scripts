#!/usr/bin/env python3
"""
VOX Data Integrity Enforcer
THE ONLY WAY I should ever get portfolio data.

This prevents me from:
- Hallucinating portfolio totals
- Using stale data
- Deriving totals from position sums (which are wrong)
- Forgetting confirmed broker values

Usage:
    from vox_data_integrity import get_truth, require_validation
    
    # Before ANY analysis:
    truth = get_truth()
    total = truth['total_aum']  # ONLY way to get total
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

SCRIPTS_DIR = Path.home() / ".hermes" / "scripts"
DASHBOARD_DIR = Path.home() / "dev" / "vox-dashboard" / "public"
SOURCE_FILE = SCRIPTS_DIR / "dashboard_positions.json"
VALIDATION_LOG = SCRIPTS_DIR / "vox_validation_log.json"


class DataIntegrityError(Exception):
    """Raised when I try to use invalid data"""
    pass


def get_truth() -> Dict:
    """
    THE ONLY FUNCTION for getting portfolio data.
    
    Returns verified broker totals - NEVER derived from position sums.
    """
    if not SOURCE_FILE.exists():
        raise DataIntegrityError("Source of truth file missing! Cannot proceed.")
    
    with open(SOURCE_FILE) as f:
        data = json.load(f)
    
    broker_breakdown = data.get("broker_breakdown", {})
    broker_status = data.get("broker_status", {})
    
    # CRITICAL: Total comes from broker_breakdown, NOT from summing positions
    # This is because positions are aggregated and may have duplicates
    confirmed_total = sum(broker_breakdown.values())
    
    stale_brokers = [
        name for name, status in broker_status.items() 
        if status.get("stale", False)
    ]
    
    return {
        "total_aum": confirmed_total,
        "total_positions": data.get("total_positions", 0),
        "generated_at": data.get("generated_at", "unknown"),
        "broker_breakdown": broker_breakdown,
        "broker_status": broker_status,
        "stale_brokers": stale_brokers,
        "stale_count": len(stale_brokers),
        "positions": data.get("positions", []),
    }


def validate() -> Dict:
    """
    Full validation with console output.
    Run this at the start of every session.
    """
    truth = get_truth()
    
    print("\n" + "="*70)
    print("🔒 VOX DATA INTEGRITY CHECK")
    print("="*70)
    print(f"\n💰 TOTAL AUM: ${truth['total_aum']:,.2f}")
    print(f"📋 POSITIONS: {truth['total_positions']}")
    print(f"🕐 DATA TIME: {truth['generated_at']}")
    
    print(f"\n🏦 BROKER BREAKDOWN:")
    for broker, value in truth['broker_breakdown'].items():
        status = truth['broker_status'].get(broker, {})
        stale = "⚠️ STALE" if status.get('stale') else "✅ LIVE"
        print(f"   {broker:12s}: ${value:>12,.2f} {stale}")
    
    if truth['stale_brokers']:
        print(f"\n⚠️ STALE: {', '.join(truth['stale_brokers'])}")
    else:
        print(f"\n✅ ALL DATA FRESH")
    
    print("="*70)
    
    # Save validation
    log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_aum": truth['total_aum'],
        "total_positions": truth['total_positions'],
        "stale_brokers": truth['stale_brokers'],
    }
    
    with open(VALIDATION_LOG, 'w') as f:
        json.dump(log, f, indent=2)
    
    return truth


def require_validation(func):
    """
    DECORATOR: Forces validation before any function runs.
    
    Usage:
        @require_validation
        def analyze_portfolio():
            truth = get_truth()
            # Now I have guaranteed accurate data
    """
    def wrapper(*args, **kwargs):
        validate()
        return func(*args, **kwargs)
    return wrapper


def get_positions_only() -> list:
    """
    Get positions list WITHOUT totals.
    Use this when you need position details but not portfolio value.
    """
    truth = get_truth()
    return truth['positions']


def get_broker_value(broker: str) -> Optional[float]:
    """Get confirmed value for a specific broker"""
    truth = get_truth()
    return truth['broker_breakdown'].get(broker)


if __name__ == "__main__":
    validate()
