import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
from datetime import datetime

os.environ['PGPASSWORD'] = ''
os.environ['PGHOST'] = 'acela.proxy.rlwy.net'
os.environ['PGPORT'] = '35577'
os.environ['PGUSER'] = 'postgres'
os.environ['PGDATABASE'] = 'railway'

sys.path.insert(0, os.path.expanduser('~/dev/vox-grader/src'))
from sync.vox_postgres_sync import _get_cursor
from grading.vox_engine import calculate_vox_grade
from psycopg2.extras import execute_values

# Skip sentiment API calls - use synthetic fallback only
os.environ['VOX_SKIP_SENTIMENT_API'] = '1'

with _get_cursor() as cur:
    cur.execute('SELECT ticker FROM sp500_universe ORDER BY ticker')
    tickers = [r['ticker'] for r in cur.fetchall()]

print(f'Re-grading {len(tickers)} tickers WITHOUT sentiment API (synthetic fallback)...')
results = []
errors = []

for i, ticker in enumerate(tickers):
    try:
        # Patch: force sentiment to use synthetic by setting use_real_sentiment=False
        # We need to modify the engine temporarily
        import grading.vox_engine as engine
        original_sentiment = engine._score_sentiment_v2
        
        def synthetic_sentiment_only(technical, fundamental, ticker=None, use_real_sentiment=True):
            # Always use synthetic, ignore API
            scores = []
            if technical.get("macd_bullish"):
                scores.append(65)
            else:
                scores.append(45)
            trend = technical.get("trend", 0)
            scores.append(int((trend + 1) * 50))
            mom = technical.get("momentum_score", 50)
            scores.append(mom)
            if fundamental.get("score", 50) >= 70:
                scores.append(75)
            elif fundamental.get("score", 50) >= 55:
                scores.append(55)
            else:
                scores.append(40)
            import numpy as np
            return int(np.mean(scores))
        
        engine._score_sentiment_v2 = synthetic_sentiment_only
        
        result = calculate_vox_grade(ticker)
        
        # Restore original
        engine._score_sentiment_v2 = original_sentiment
        
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
print('Done')
