import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
from datetime import datetime

# Set the 4 API keys
os.environ['ALPHA_VANTAGE_API_KEYS'] = 'RFQEENHZRK8XG4EE,35YQPJ8T1BMW2PO9,DEXKTIRV6JYTZ2LM,J820ANKUQ4UYDK1K'

os.environ['PGPASSWORD'] = ''
os.environ['PGHOST'] = 'acela.proxy.rlwy.net'
os.environ['PGPORT'] = '35577'
os.environ['PGUSER'] = 'postgres'
os.environ['PGDATABASE'] = 'railway'

sys.path.insert(0, os.path.expanduser('~/dev/vox-grader/src'))
from sync.vox_postgres_sync import _get_cursor
from grading.vox_engine import calculate_vox_grade
from psycopg2.extras import execute_values

with _get_cursor() as cur:
    cur.execute('SELECT ticker FROM sp500_universe ORDER BY ticker')
    tickers = [r['ticker'] for r in cur.fetchall()]

print(f'Re-grading {len(tickers)} tickers WITH 4 Alpha Vantage API keys...')
print(f'Keys loaded: {len(os.environ.get("ALPHA_VANTAGE_API_KEYS","").split(","))}')
results = []
errors = []

for i, ticker in enumerate(tickers):
    try:
        result = calculate_vox_grade(ticker)
        results.append({
            'ticker': ticker,
            'vox_grade': result.overall_grade,
            'technical_score': result.technical_score,
            'fundamental_score': result.fundamental_score,
            'macro_score': result.macro_score,
            'sector_score': result.sector_score,
            'weather_score': result.weather_score,
            'sentiment_score': result.sentiment_score,
        })
        if (i+1) % 50 == 0:
            print(f'Progress: {i+1}/{len(tickers)}', flush=True)
    except Exception as e:
        errors.append((ticker, str(e)[:80]))
        print(f'  {ticker}: ERROR - {str(e)[:80]}')

if results:
    with _get_cursor() as cur:
        rows = [(r['ticker'], r['vox_grade'], r['technical_score'], r['fundamental_score'],
                 r['macro_score'], r['sector_score'], r['weather_score'], r['sentiment_score'],
                 datetime.now()) for r in results]
        execute_values(cur, '''
            INSERT INTO sp500_grades (ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, computed_at)
            VALUES %s
            ON CONFLICT (ticker) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade,
                technical_score = EXCLUDED.technical_score,
                fundamental_score = EXCLUDED.fundamental_score,
                macro_score = EXCLUDED.macro_score,
                sector_score = EXCLUDED.sector_score,
                weather_score = EXCLUDED.weather_score,
                sentiment_score = EXCLUDED.sentiment_score,
                computed_at = NOW()
        ''', rows)
    print(f'Saved {len(results)} grades')

print(f'Errors: {len(errors)}')
if errors:
    for t, e in errors[:10]:
        print(f'  {t}: {e}')
print('Done')
