#!/usr/bin/env python3
"""
VOX TRADER DAILY v1.0
3x daily trader intelligence: Morning, Midday, Evening

Usage:
  python3 vox_trader_daily.py morning    # 6:30 AM pre-market
  python3 vox_trader_daily.py midday     # 12:00 PM intraday
  python3 vox_trader_daily.py evening    # 4:30 PM post-market
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta

DB_PASSWORD=os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD=''

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )

def get_recent_calls(hours=24):
    """Get calls from last N hours"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT DISTINCT ON (tc.trader_name, tc.ticker)
            tc.trader_name,
            tc.ticker,
            tc.call_type,
            tc.price_at_call,
            tc.target_price,
            tc.stop_price,
            tc.thesis,
            tc.source,
            tc.call_date,
            tp.weight as trader_weight,
            vg.vox_grade,
            vg.action as vox_action
        FROM trader_calls tc
        JOIN trader_profiles tp ON tc.trader_name = tp.name
        LEFT JOIN vox_grades vg ON tc.ticker = vg.ticker
        WHERE tc.call_date > NOW() - INTERVAL '%s hours'
        ORDER BY tc.trader_name, tc.ticker, tc.call_date DESC
    """, (hours,))
    
    calls = cur.fetchall()
    conn.close()
    return calls

def get_consensus(hours=24, min_traders=2):
    """Find consensus in last N hours"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tc.ticker,
            COUNT(DISTINCT tc.trader_name) as trader_count,
            ARRAY_AGG(DISTINCT tc.trader_name) as traders,
            AVG(tp.weight) as avg_weight,
            MAX(tc.call_date) as latest_call
        FROM trader_calls tc
        JOIN trader_profiles tp ON tc.trader_name = tp.name
        WHERE tc.call_date > NOW() - INTERVAL '%s hours'
        GROUP BY tc.ticker
        HAVING COUNT(DISTINCT tc.trader_name) >= %s
        ORDER BY avg_weight DESC, trader_count DESC
        LIMIT 10
    """, (hours, min_traders))
    
    consensus = cur.fetchall()
    conn.close()
    return consensus

def get_high_conviction(hours=24, min_weight=0.8):
    """Get high-conviction calls from top traders"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tc.trader_name,
            tc.ticker,
            tc.call_type,
            tc.price_at_call,
            tc.target_price,
            tc.stop_price,
            tc.thesis,
            tc.call_date,
            tp.weight,
            vg.vox_grade
        FROM trader_calls tc
        JOIN trader_profiles tp ON tc.trader_name = tp.name
        LEFT JOIN vox_grades vg ON tc.ticker = vg.ticker
        WHERE tc.call_date > NOW() - INTERVAL '%s hours'
          AND tp.weight >= %s
        ORDER BY tp.weight DESC, tc.call_date DESC
        LIMIT 15
    """, (hours, min_weight))
    
    calls = cur.fetchall()
    conn.close()
    return calls

def format_morning_digest():
    """Pre-market morning briefing"""
    calls = get_recent_calls(12)  # Overnight calls
    consensus = get_consensus(24, 2)
    high_conviction = get_high_conviction(24, 0.8)
    
    lines = [
        "🌅 VOX TRADER MORNING DIGEST",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Market: PRE-OPEN",
        "",
        "🔥 OVERNIGHT HIGH-CONVICTION CALLS",
        "-" * 60,
    ]
    
    if high_conviction:
        for call in high_conviction[:8]:
            trader, ticker, ctype, price, target, stop, thesis, date, weight, vox_grade = call
            lines.append(f"• {trader} (weight: {weight:.0%}): {ctype.upper()} {ticker}")
            lines.append(f"  Entry: ${price or 'N/A'} | Target: ${target or 'N/A'} | Stop: ${stop or 'N/A'}")
            lines.append(f"  VOX: {vox_grade or 'N/A'} | {thesis[:80] if thesis else 'No thesis'}")
    else:
        lines.append("No new high-conviction calls overnight.")
    
    lines.extend([
        "",
        "🤝 CONSENSUS TRADES FORMING",
        "-" * 60,
    ])
    
    if consensus:
        for cons in consensus[:5]:
            ticker, count, traders, avg_weight, latest = cons
            lines.append(f"• {ticker}: {count} traders (avg weight: {avg_weight:.2f})")
            lines.append(f"  Traders: {', '.join(traders[:3])}")
    else:
        lines.append("No consensus trades forming.")
    
    lines.extend([
        "",
        "📊 ALL OVERNIGHT CALLS",
        "-" * 60,
    ])
    
    if calls:
        for call in calls[:10]:
            trader, ticker, ctype, price, target, stop, thesis, source, date, weight, vox_grade, vox_action = call
            lines.append(f"• {trader}: {ctype.upper()} {ticker} @ ${price or 'N/A'} (VOX: {vox_grade or 'N/A'})")
    else:
        lines.append("No overnight calls recorded.")
    
    lines.extend([
        "",
        "-" * 60,
        "💡 PRE-MARKET SETUP:",
        "   • Review consensus trades for entry",
        "   • Check VOX grade alignment",
        "   • Set alerts for high-conviction mentions",
    ])
    
    return "\n".join(lines)

def format_midday_update():
    """Midday intraday update"""
    calls = get_recent_calls(6)  # Last 6 hours
    consensus = get_consensus(6, 2)
    
    lines = [
        "📈 VOX TRADER MIDDAY UPDATE",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Market: INTRADAY",
        "",
        "🔥 NEW CALLS SINCE MORNING",
        "-" * 60,
    ]
    
    if calls:
        for call in calls[:8]:
            trader, ticker, ctype, price, target, stop, thesis, source, date, weight, vox_grade, vox_action = call
            lines.append(f"• {trader}: {ctype.upper()} {ticker} @ ${price or 'N/A'} (VOX: {vox_grade or 'N/A'})")
    else:
        lines.append("No new calls since morning.")
    
    lines.extend([
        "",
        "🤝 INTRADAY CONSENSUS",
        "-" * 60,
    ])
    
    if consensus:
        for cons in consensus[:3]:
            ticker, count, traders, avg_weight, latest = cons
            lines.append(f"• {ticker}: {count} traders | {avg_weight:.2f} avg weight")
    else:
        lines.append("No new consensus forming.")
    
    lines.extend([
        "",
        "-" * 60,
        "💡 MIDDAY NOTE: Watch for momentum shifts and position changes.",
    ])
    
    return "\n".join(lines)

def format_evening_wrap():
    """Post-market evening summary"""
    calls = get_recent_calls(24)  # Full day
    consensus = get_consensus(24, 2)
    high_conviction = get_high_conviction(24, 0.8)
    
    lines = [
        "🌙 VOX TRADER EVENING WRAP",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Market: CLOSED",
        "",
        "📊 FULL DAY SUMMARY",
        "-" * 60,
        f"Total calls today: {len(calls)}",
        f"High-conviction calls: {len(high_conviction)}",
        f"Consensus trades: {len(consensus)}",
        "",
        "🏆 BEST CALLS OF THE DAY",
        "-" * 60,
    ]
    
    if high_conviction:
        for call in high_conviction[:5]:
            trader, ticker, ctype, price, target, stop, thesis, date, weight, vox_grade = call
            lines.append(f"• {trader}: {ctype.upper()} {ticker}")
            lines.append(f"  VOX Grade: {vox_grade or 'N/A'} | Weight: {weight:.0%}")
            if thesis:
                lines.append(f"  Thesis: {thesis[:100]}...")
    else:
        lines.append("No high-conviction calls today.")
    
    lines.extend([
        "",
        "🤝 END-OF-DAY CONSENSUS",
        "-" * 60,
    ])
    
    if consensus:
        for cons in consensus[:5]:
            ticker, count, traders, avg_weight, latest = cons
            lines.append(f"• {ticker}: {count} traders | {avg_weight:.2f} avg weight")
            lines.append(f"  Traders: {', '.join(traders[:3])}")
    else:
        lines.append("No consensus trades today.")
    
    lines.extend([
        "",
        "📋 TOMORROW'S WATCHLIST",
        "-" * 60,
    ])
    
    # Get tickers with most mentions today
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, COUNT(*) as mentions
        FROM trader_calls
        WHERE call_date > NOW() - INTERVAL '24 hours'
        GROUP BY ticker
        ORDER BY mentions DESC
        LIMIT 5
    """)
    watchlist = cur.fetchall()
    conn.close()
    
    if watchlist:
        for ticker, mentions in watchlist:
            lines.append(f"• {ticker}: {mentions} mentions today")
    else:
        lines.append("No standout tickers for tomorrow.")
    
    lines.extend([
        "",
        "-" * 60,
        "💡 OVERNIGHT HOLD:",
        "   • Monitor after-hours news",
        "   • Check Asian market reaction",
        "   • Set alerts for gap moves",
    ])
    
    return "\n".join(lines)

def main():
    edition = sys.argv[1] if len(sys.argv) > 1 else 'morning'
    
    if edition == 'morning':
        print(format_morning_digest())
    elif edition == 'midday':
        print(format_midday_update())
    elif edition == 'evening':
        print(format_evening_wrap())
    else:
        print("Usage: morning, midday, evening")

if __name__ == '__main__':
    main()
