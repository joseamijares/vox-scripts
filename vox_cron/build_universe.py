import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import os

# Read password from env file
DB_PASSWORD = ''
with open(os.path.expanduser('~/.hermes/.env')) as f:
    for line in f:
        if line.startswith('DB_PASSWORD='):
            DB_PASSWORD = line.strip().split('=', 1)[1]
            break

conn = psycopg2.connect(
    host='acela.proxy.rlwy.net', port=35577, database='railway',
    user='postgres', password=DB_PASSWORD, sslmode='require'
)
cur = conn.cursor()

# Drop and recreate
cur.execute('DROP TABLE IF EXISTS liquid_universe')
cur.execute('''
    CREATE TABLE liquid_universe (
        ticker TEXT PRIMARY KEY,
        vox_grade INTEGER,
        action TEXT,
        technical_score INTEGER,
        fundamental_score INTEGER,
        macro_score INTEGER,
        sector_score INTEGER,
        weather_score INTEGER,
        sentiment_score INTEGER,
        composite_score NUMERIC,
        is_new_entry BOOLEAN DEFAULT FALSE,
        is_removed BOOLEAN DEFAULT FALSE,
        first_seen TIMESTAMP DEFAULT NOW(),
        last_updated TIMESTAMP DEFAULT NOW()
    )
''')
conn.commit()

# Load all grades
print('Loading grades...')
cur.execute('''
    SELECT ticker, vox_grade, action,
           COALESCE(technical_score,0), COALESCE(fundamental_score,0),
           COALESCE(macro_score,0), COALESCE(sector_score,0),
           COALESCE(weather_score,0), COALESCE(sentiment_score,0)
    FROM vox_grades WHERE ticker IS NOT NULL
''')
rows = cur.fetchall()
print(f'Loaded {len(rows)} rows')

# Score in memory
scored = []
for row in rows:
    ticker, grade, action, tech, fund, macro, sector, weather, sentiment = row
    layer_scores = [tech, fund, macro, sector, weather, sentiment]
    valid = [s for s in layer_scores if s > 0]
    avg_layer = sum(valid) / len(valid) if valid else 0
    composite = (grade * 0.5) + (avg_layer * 0.5) if grade else avg_layer
    scored.append((ticker, grade or 0, action or 'UNKNOWN', tech, fund, macro, sector, weather, sentiment, composite))

# Sort and take top 5000
scored.sort(key=lambda x: x[-1], reverse=True)
top_5000 = scored[:5000]
print(f'Top 5000 selected (composite >= {top_5000[-1][-1]:.1f})')

# Remove duplicates before insert
seen = set()
unique_5000 = []
for s in top_5000:
    if s[0] not in seen:
        seen.add(s[0])
        unique_5000.append(s)

print(f'Unique top 5000: {len(unique_5000)} (removed {len(top_5000) - len(unique_5000)} duplicates)')

# Batch insert using executemany
print('Inserting...')
insert_sql = '''
    INSERT INTO liquid_universe 
    (ticker, vox_grade, action, technical_score, fundamental_score, macro_score,
     sector_score, weather_score, sentiment_score, composite_score, is_new_entry, is_removed, first_seen, last_updated)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, FALSE, NOW(), NOW())
'''
cur.executemany(insert_sql, [s[:10] for s in unique_5000])
conn.commit()

# Stats
high_grade = len([s for s in unique_5000 if s[1] >= 70])
buy_strong = len([s for s in unique_5000 if s[2] in ('BUY', 'STRONG_BUY')])
print(f'Grade 70+: {high_grade}')
print(f'BUY/STRONG_BUY: {buy_strong}')

print('\n**TOP 20:**')
for i, s in enumerate(unique_5000[:20], 1):
    print(f'{i:2d}. {s[0]:6s} | Grade: {s[1]:2d} | Comp: {s[-1]:5.1f} | {s[2]}')

cur.close()
conn.close()
print('Done!')
