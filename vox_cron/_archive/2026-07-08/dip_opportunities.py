#!/usr/bin/env python3
"""Find high-grade dip buying opportunities."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2, os

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD=os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "railway")

conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER,
    password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
)
cur = conn.cursor()

print('=== HIGH-GRADE DIP BUYING OPPORTUNITIES ===')
print('(Grade >= 70, not in portfolio, aggressive sectors)\n')

cur.execute('''
    SELECT 
        v.ticker, 
        v.vox_grade, 
        v.action,
        v.technical_score,
        v.fundamental_score,
        v.sentiment_score,
        ts.sector,
        sm.momentum_score as sector_momentum
    FROM vox_grades v
    LEFT JOIN ticker_sectors ts ON v.ticker = ts.ticker
    LEFT JOIN sector_momentum sm ON ts.sector = sm.sector
    WHERE v.vox_grade >= 70
      AND v.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
      AND v.ticker NOT IN (SELECT ticker FROM positions WHERE shares > 0)
      AND v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
    ORDER BY v.vox_grade DESC
    LIMIT 20
''')

rows = cur.fetchall()
for row in rows:
    ticker, grade, action, tech, fund, sent, sector, sec_mom = row
    sector_emoji = '🔥' if sec_mom and sec_mom >= 60 else '🟢' if sec_mom and sec_mom >= 50 else '⚪'
    print(f'{ticker:6} | Grade: {grade:2} | {action:12} | Tech: {tech:3} | Fund: {fund:3} | Sent: {sent:3} | Sector: {sector or "Unknown":25} {sector_emoji}')

# Also check portfolio positions that are down but still high grade
print('\n=== PORTFOLIO POSITIONS — ADD ON DIPS ===')
print('(High grade positions that may be down today)\n')

cur.execute('''
    SELECT 
        p.ticker,
        p.shares,
        p.live_price,
        p.grade,
        p.council,
        v.vox_grade as latest_grade,
        v.action as latest_action
    FROM positions p
    LEFT JOIN vox_grades v ON p.ticker = v.ticker
    WHERE p.shares > 0
      AND v.generated_at = (SELECT MAX(generated_at) FROM vox_grades v2 WHERE v2.ticker = v.ticker)
      AND v.vox_grade >= 75
    ORDER BY v.vox_grade DESC
''')

rows = cur.fetchall()
for row in rows:
    ticker, shares, price, grade, council, latest_grade, latest_action = row
    print(f'{ticker:6} | Shares: {shares:8.2f} | Price: ${price:8.2f} | Grade: {latest_grade} | Action: {latest_action} | Council: {council}')

conn.close()
