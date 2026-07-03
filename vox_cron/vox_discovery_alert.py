#!/usr/bin/env python3
"""
VOX DISCOVERY ALERT v1.0
Weekly alert for best new discoveries (grade 80+, not in portfolio, aggressive themes).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = ''

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )

def get_best_discoveries(limit=5):
    """Get top new discoveries"""
    conn = connect()
    cur = conn.cursor()
    
    # Find tickers grade 80+ not in portfolio, from aggressive themes
    cur.execute("""
        SELECT 
            vg.ticker,
            vg.vox_grade,
            vg.action,
            vg.technical_score,
            vg.fundamental_score,
            ut.theme,
            ut.source,
            vg.catalysts
        FROM vox_grades vg
        JOIN universe_tiers ut ON vg.ticker = ut.ticker
        LEFT JOIN positions p ON vg.ticker = p.ticker
        WHERE vg.vox_grade >= 80
          AND vg.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
          AND p.ticker IS NULL
          AND ut.active = TRUE
          AND (vg.generated_at > NOW() - INTERVAL '7 days' OR ut.discovery_date > NOW() - INTERVAL '30 days')
        ORDER BY vg.vox_grade DESC, ut.priority DESC
        LIMIT %s
    """, (limit,))
    
    discoveries = cur.fetchall()
    conn.close()
    return discoveries

def format_alert(discoveries):
    """Format discoveries into alert message"""
    if not discoveries:
        return "🎯 No new grade 80+ discoveries this week. Your current portfolio is well-positioned."
    
    lines = [
        "🚀 VOX WEEKLY DISCOVERY ALERT",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        f"Market Regime: RISK_ON",
        "",
        f"📊 TOP {len(discoveries)} NEW DISCOVERIES",
        "-" * 60,
    ]
    
    for i, disc in enumerate(discoveries, 1):
        ticker, grade, action, tech, fund, theme, source, catalysts = disc
        
        lines.append(f"\n#{i} {ticker}")
        lines.append(f"   Grade: {grade} | Action: {action}")
        lines.append(f"   Tech: {tech} | Fund: {fund}")
        lines.append(f"   Theme: {theme or 'General'} | Source: {source}")
        if catalysts:
            lines.append(f"   Catalyst: {catalysts}")
    
    lines.extend([
        "",
        "-" * 60,
        "💡 RECOMMENDATION: Review these tickers for potential allocation.",
        "   Consider position sizing based on your risk tolerance.",
        "",
        "📈 Next Steps:",
        "   1. Run deep-dive analysis on top 3",
        "   2. Check technical charts",
        "   3. Verify liquidity and volume",
        "   4. Allocate if thesis aligns with goals",
    ])
    
    return "\n".join(lines)

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'alert'
    
    if action == 'alert':
        discoveries = get_best_discoveries(5)
        alert = format_alert(discoveries)
        print(alert)
    elif action == 'count':
        conn = connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) FROM vox_grades vg
            JOIN universe_tiers ut ON vg.ticker = ut.ticker
            LEFT JOIN positions p ON vg.ticker = p.ticker
            WHERE vg.vox_grade >= 80 AND p.ticker IS NULL
        """)
        print(f"Grade 80+ discoveries not in portfolio: {cur.fetchone()[0]}")
        conn.close()
    else:
        print("Usage: alert, count")

if __name__ == '__main__':
    main()
