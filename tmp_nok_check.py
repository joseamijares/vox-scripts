#!/usr/bin/env python3
import psycopg2, os

env_path = os.path.expanduser('~/.hermes/.env')
env_vars = {}
with open(env_path) as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env_vars[k] = v

DB_PASSWORD=env_va...RD', '')
DB_HOST = env_vars.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = env_vars.get('DB_PORT', '35577')
DB_NAME = env_vars.get('DB_NAME', 'railway')
DB_USER = env_vars.get('DB_USER', 'postgres')

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD)
cur = conn.cursor()

# Position check
cur.execute("SELECT ticker, shares, avg_cost, live_price, live_value, currency, grade, council, brokers FROM positions WHERE ticker = 'NOK'")
row = cur.fetchone()
print('=== POSITION ===')
if row:
    print(f'Shares: {row[1]} | Avg Cost: {row[2]} | Live Price: {row[3]} | Value: {row[4]} {row[5]}')
    print(f'Grade: {row[6]} | Council: {row[7]} | Brokers: {row[8]}')
else:
    print('No position in NOK')

# Trade signals
cur.execute("SELECT ticker, composite_score, grade, signal_type, created_at FROM trade_signals WHERE ticker = 'NOK' ORDER BY created_at DESC LIMIT 1")
row = cur.fetchone()
print('\n=== TRADE SIGNALS ===')
if row:
    print(f'Composite: {row[1]} | Grade: {row[2]} | Type: {row[3]} | Created: {row[4]}')
else:
    print('No trade signals for NOK')

# SP500 grade
cur.execute("SELECT ticker, vox_grade, action, computed_at FROM sp500_grades WHERE ticker = 'NOK' ORDER BY computed_at DESC LIMIT 1")
row = cur.fetchone()
print('\n=== SP500 GRADE ===')
if row:
    print(f'Grade: {row[1]} | Action: {row[2]} | Computed: {row[3]}')
else:
    print('NOK not in sp500_grades')

# Watchlist
cur.execute("SELECT ticker, grade, action FROM watchlist WHERE ticker = 'NOK'")
row = cur.fetchone()
print('\n=== WATCHLIST ===')
if row:
    print(f'Grade: {row[1]} | Action: {row[2]}')
else:
    print('NOK not in watchlist')

# Technical signals
cur.execute("SELECT ticker, score, alpha_zoo_score, computed_at FROM technical_signals WHERE ticker = 'NOK' ORDER BY computed_at DESC LIMIT 1")
row = cur.fetchone()
print('\n=== TECHNICAL SIGNALS ===')
if row:
    print(f'Score: {row[1]} | Alpha Zoo: {row[2]} | Computed: {row[3]}')
else:
    print('No technical signals for NOK')

# Sentiment
cur.execute("SELECT ticker, vox_score, raw_score, computed_at FROM sentiment_scores WHERE ticker = 'NOK' ORDER BY computed_at DESC LIMIT 1")
row = cur.fetchone()
print('\n=== SENTIMENT ===')
if row:
    print(f'VOX Score: {row[1]} | Raw: {row[2]} | Computed: {row[3]}')
else:
    print('No sentiment scores for NOK')

cur.close()
conn.close()
