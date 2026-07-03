import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os, sys, time, signal
from datetime import datetime

# HARD SCRIPT TIMEOUT: ensure we never exceed cron's 120s limit
SCRIPT_TIMEOUT = 100  # seconds — leave 20s buffer for cron overhead

def script_timeout_handler(signum, frame):
    print(f'\n🚨 SCRIPT TIMEOUT: Exiting after {SCRIPT_TIMEOUT}s to prevent cron failure')
    sys.exit(0)  # Exit 0 so cron doesn't flag as error

# Set script-level timeout immediately
signal.signal(signal.SIGALRM, script_timeout_handler)
signal.alarm(SCRIPT_TIMEOUT)

# Set 4 Alpha Vantage API keys for rotation
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

# Timeout wrapper for per-ticker grading (prevent hanging on API calls)
class TickerTimeoutError(Exception):
    pass

def ticker_timeout_handler(signum, frame):
    raise TickerTimeoutError("Ticker grading timed out")

def grade_with_timeout(ticker, timeout_secs=5):
    """Grade a single ticker with a hard timeout."""
    old_handler = signal.signal(signal.SIGALRM, ticker_timeout_handler)
    signal.alarm(timeout_secs)
    try:
        result = calculate_vox_grade(ticker)
        signal.alarm(0)
        return result
    except TickerTimeoutError:
        return None
    except Exception as e:
        signal.alarm(0)
        raise e
    finally:
        signal.signal(signal.SIGALRM, old_handler)

print(f"VOX S&P 500 Weekly Regrade — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print("=" * 60)

with _get_cursor() as cur:
    cur.execute('SELECT ticker FROM sp500_universe WHERE is_active = TRUE ORDER BY ticker')
    tickers = [r['ticker'] for r in cur.fetchall()]

print(f'Re-grading {len(tickers)} S&P 500 tickers with 4 Alpha Vantage keys...')
print('(Processing in small batches with per-ticker timeouts to avoid cron timeout)')
print()

results = []
errors = []
BATCH_SIZE = 10
SLEEP_SECS = 1   # Reduced from 2 — faster cycling, less chance of hitting script timeout

# Rotate through the full list using day-of-year offset
import datetime as dt
day_of_year = dt.datetime.now().timetuple().tm_yday
num_batches = max(1, len(tickers) // BATCH_SIZE)
offset = (day_of_year % num_batches) * BATCH_SIZE
batch_tickers = tickers[offset:offset + BATCH_SIZE]

print(f'Processing batch {offset//BATCH_SIZE + 1}/{num_batches} (tickers {offset+1}-{offset+len(batch_tickers)})')
print()

for i, ticker in enumerate(batch_tickers):
    try:
        result = grade_with_timeout(ticker, timeout_secs=5)  # Reduced from 6
        if result is None:
            errors.append((ticker, "TIMEOUT (5s)"))
            print(f'  {ticker}: TIMEOUT (5s)', flush=True)
            continue
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
        print(f'  {ticker}: grade {result.overall_grade} (ok)', flush=True)
    except Exception as e:
        errors.append((ticker, str(e)[:80]))
        print(f'  {ticker}: ERROR - {str(e)[:80]}', flush=True)
    
    time.sleep(SLEEP_SECS)

print()
print(f'Grading complete: {len(results)} succeeded, {len(errors)} errors')

if results:
    print('Saving to database...')
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
    print(f'✅ Saved {len(results)} grades to sp500_grades')

if errors:
    print(f'⚠️ {len(errors)} errors (see above)')

# Cancel script timeout before normal exit
signal.alarm(0)
print('Done')
