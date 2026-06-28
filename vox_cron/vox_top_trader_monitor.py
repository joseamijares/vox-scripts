#!/usr/bin/env python3
"""
VOX TOP TRADER DAILY MONITOR v1.0
Monitors elite traders (weight >= 0.9) daily:
- New calls/mentions in last 24h
- Consensus detection (2+ traders on same ticker)
- Cross-reference with VOX grades
- Alert on high-conviction opportunities

Elite traders tracked:
- Shay Boloor (@StockSavvyShay) — weight 1.0, tech_growth, AI/semiconductors
- Leopold Aschenbrenner (@leopoldasch) — weight 0.95, AI researcher, AGI/compute
- Stanley Druckenmiller — weight 0.95, macro
- Paul Tudor Jones — weight 0.95, macro
- Renaissance Technologies — weight 0.95, quant
- Ray Dalio — weight 0.90, macro
- Cathie Wood — weight 0.90, disruptive
- Kobeissi Signal — weight 0.90, macro signals
- Unusual Whales — weight 0.90, options flow
- Howard Marks — weight 0.90, value
- Bill Ackman — weight 0.85, activist
- ARK Invest — weight 0.90, disruptive
- Meb Faber — weight 0.70, quant (expanded)

Run: python3 vox_top_trader_monitor.py
"""

import os
import sys
import psycopg2
from datetime import datetime, timedelta

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = 'hEJeasaJlhzFSVCIAgQqLDzqKCsUmqAS'

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )

ELITE_TRADERS = [
    # Tier 1: Weight 0.95+
    'shay boloor', 'leopold aschenbrenner', 'stanley druckenmiller',
    'paul tudor jones', 'renaissance technologies',
    # Tier 2: Weight 0.90
    'ark invest', 'cathie wood', 'dr kathy wood', 'citadel',
    'dan ives', 'howard marks', 'kobeissi signal', 'raoul pal',
    'ray dalio', 'unusual whales',
    # Tier 3: Weight 0.85
    'adam mancini', 'bill ackman', 'brett steenbarger', 'elon musk',
    'gary black', 'gene munster', 'goldman sachs', 'goldman sachs research',
    'james bianco', 'jeff gundlach', 'jpmorgan', 'katy huberty',
    'lyn alden', 'marko kolanovic', 'michael saylor', 'mike wilson',
    'morgan stanley tech', 'nick timiraos', 'options hawk',
    'peter brandt', 'pierre ferragu', 'tom lee', 'toni sacconaghi',
    'vitalik buterin',
    # Tier 4: Weight 0.80
    'ark genomics', 'bank of america', 'berstein research', 'brian shannon',
    'carson block', 'credit suisse', 'david rosenberg', 'deltaone',
    'gordon johnson', 'jc parets', 'jim chanos', 'joseph politano',
    'julian brigden', 'julius baer macro', 'lawrence mcdonald',
    'lisa shallet', 'lookonchain', 'mark sebastian', 'ming-chi kuo',
    'mohnish pabrai', 'morgan stanley mike', 'nathan michaud',
    'neel kashkari', 'puru saxena', 'ross gerber', 'scott redler',
    'ubs research', 'willy woo'
]

def get_latest_vox_grade(ticker, cur):
    """Get latest VOX grade for a ticker."""
    cur.execute("""
        SELECT vox_grade, action, current_price, generated_at
        FROM vox_grades
        WHERE ticker = %s
        ORDER BY generated_at DESC
        LIMIT 1
    """, (ticker,))
    row = cur.fetchone()
    if row:
        return {'grade': row[0], 'action': row[1], 'price': row[2], 'date': row[3]}
    return None

def get_recent_elite_activity(hours=24):
    """Get all activity from elite traders in last N hours."""
    conn = connect()
    cur = conn.cursor()
    
    # Recent calls
    cur.execute("""
        SELECT tc.trader_name, tc.ticker, tc.call_type, tc.price_at_call, 
               tc.target_price, tc.stop_price, tc.thesis, tc.source, tc.call_date,
               tp.weight, tp.style
        FROM trader_calls tc
        JOIN trader_profiles tp ON tc.trader_name = tp.name
        WHERE tc.trader_name = ANY(%s)
          AND tc.call_date > NOW() - INTERVAL '%s hours'
        ORDER BY tc.call_date DESC
    """, (ELITE_TRADERS, hours))
    calls = cur.fetchall()
    
    # Recent mentions
    cur.execute("""
        SELECT tm.trader_name, tm.ticker, tm.sentiment, tm.context, tm.mention_date,
               tp.weight, tp.style
        FROM trader_mentions tm
        JOIN trader_profiles tp ON tm.trader_name = tp.name
        WHERE tm.trader_name = ANY(%s)
          AND tm.mention_date > NOW() - INTERVAL '%s hours'
        ORDER BY tm.mention_date DESC
    """, (ELITE_TRADERS, hours))
    mentions = cur.fetchall()
    
    conn.close()
    return calls, mentions

def find_consensus():
    """Find tickers with 2+ elite traders in last 30 days."""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tc.ticker,
            COUNT(DISTINCT tc.trader_name) as trader_count,
            ARRAY_AGG(DISTINCT tc.trader_name) as traders,
            AVG(CASE WHEN tc.call_type = 'buy' THEN 1 ELSE 0 END) as buy_ratio,
            MAX(tc.call_date) as latest_call,
            STRING_AGG(DISTINCT tc.thesis, ' | ') as theses
        FROM trader_calls tc
        WHERE tc.trader_name = ANY(%s)
          AND tc.call_date > NOW() - INTERVAL '30 days'
          AND tc.resolved = FALSE
        GROUP BY tc.ticker
        HAVING COUNT(DISTINCT tc.trader_name) >= 2
        ORDER BY trader_count DESC, latest_call DESC
    """, (ELITE_TRADERS,))
    
    consensus = cur.fetchall()
    conn.close()
    return consensus

def generate_daily_report():
    """Generate daily elite trader monitor report."""
    calls, mentions = get_recent_elite_activity(hours=24)
    consensus = find_consensus()
    
    lines = [
        "🎯 VOX TOP TRADER DAILY MONITOR",
        "=" * 70,
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Monitoring: {len(ELITE_TRADERS)} elite traders (weight >= 0.85)",
        "",
    ]
    
    # Section 1: New Calls (last 24h)
    if calls:
        lines.extend([
            "🔥 NEW CALLS (last 24 hours)",
            "-" * 70,
        ])
        conn = connect()
        cur = conn.cursor()
        for call in calls:
            trader, ticker, ctype, price, target, stop, thesis, source, date, weight, style = call
            vox = get_latest_vox_grade(ticker, cur)
            
            grade_str = f"VOX {vox['grade']} → {vox['action']}" if vox else "NO VOX GRADE"
            price_str = f"@${price}" if price else "N/A"
            target_str = f"→ ${target}" if target else ""
            
            lines.append(f"• {trader.title()} ({weight}): {ctype.upper()} {ticker} @ {price_str} {target_str}")
            lines.append(f"  {grade_str} | Style: {style}")
            if thesis:
                lines.append(f"  Thesis: {thesis[:100]}...")
            lines.append("")
        conn.close()
    else:
        lines.extend([
            "🔥 NEW CALLS (last 24 hours)",
            "-" * 70,
            "No new elite trader calls in last 24h.",
            "",
        ])
    
    # Section 2: New Mentions (last 24h)
    if mentions:
        lines.extend([
            "📢 NEW MENTIONS (last 24 hours)",
            "-" * 70,
        ])
        conn = connect()
        cur = conn.cursor()
        for m in mentions:
            trader, ticker, sentiment, context, date, weight, style = m
            vox = get_latest_vox_grade(ticker, cur)
            grade_str = f"VOX {vox['grade']} → {vox['action']}" if vox else "NO VOX GRADE"
            lines.append(f"• {trader.title()} ({weight}): {sentiment.upper()} {ticker}")
            lines.append(f"  {grade_str} | Context: {context[:80]}...")
            lines.append("")
        conn.close()
    
    # Section 3: Consensus Trades
    if consensus:
        lines.extend([
            "🤝 ELITE CONSENSUS (2+ traders, 30 days)",
            "-" * 70,
        ])
        conn = connect()
        cur = conn.cursor()
        for c in consensus:
            ticker, count, traders, buy_ratio, latest, theses = c
            vox = get_latest_vox_grade(ticker, cur)
            
            sentiment = "BULLISH" if buy_ratio > 0.6 else "BEARISH" if buy_ratio < 0.4 else "MIXED"
            conv = "🔥 HIGH CONVICTION" if count >= 3 else "⚡ CONSENSUS"
            
            lines.append(f"{conv}: {ticker}")
            lines.append(f"  {count} traders ({sentiment}) | Latest: {latest.strftime('%m/%d')}")
            lines.append(f"  Traders: {', '.join(traders[:4])}")
            if vox:
                lines.append(f"  VOX Grade: {vox['grade']} → {vox['action']} | Price: ${vox['price']}")
                if vox['grade'] >= 70 and buy_ratio > 0.5:
                    lines.append(f"  ✅ MAX CONVICTION: VOX 70+ + Elite consensus")
                elif vox['grade'] >= 60 and buy_ratio > 0.5:
                    lines.append(f"  ✅ HIGH CONVICTION: VOX 60+ + Elite consensus")
                elif vox['grade'] < 50 and buy_ratio > 0.5:
                    lines.append(f"  ⚠️ CONTRADICTION: Elite bullish but VOX SELL")
            else:
                lines.append(f"  ❌ NO VOX GRADE — needs grading")
            lines.append("")
        conn.close()
    else:
        lines.extend([
            "🤝 ELITE CONSENSUS (2+ traders, 30 days)",
            "-" * 70,
            "No consensus trades among elite traders.",
            "",
        ])
    
    # Section 4: Summary stats
    lines.extend([
        "-" * 70,
        f"📊 Summary: {len(calls)} calls, {len(mentions)} mentions, {len(consensus)} consensus trades",
        "",
        "💡 TIP: When 2+ elite traders agree on a ticker with VOX grade 65+, consider it.",
        "💡 TIP: When 3+ elite traders agree on a ticker with VOX grade 75+, it's MAX CONVICTION.",
    ])
    
    return "\n".join(lines)

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'report'
    
    if action == 'report':
        print(generate_daily_report())
    elif action == 'consensus':
        consensus = find_consensus()
        print(f"Found {len(consensus)} consensus trades")
        for c in consensus:
            print(f"  {c[0]}: {c[1]} traders, {c[3]:.0%} bullish")
    else:
        print("Usage: report | consensus")

if __name__ == '__main__':
    main()
