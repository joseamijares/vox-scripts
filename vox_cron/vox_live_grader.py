#!/usr/bin/env python3
"""
VOX LIVE GRADING ENGINE v2.0
Replaces random grading with actual market data:
1. Fetches live prices from yfinance
2. Calculates real momentum (1D, 1W, 1M, 3M, 6M, YTD)
3. Computes technical score from price action
4. Estimates fundamental score from P/E, revenue growth, margins
5. Checks macro alignment (sector momentum, market regime)
6. Generates a REAL grade based on data, not randomness

Stores in vox_grades with data_hash to detect if market changed.
"""

import os
import sys
import psycopg2
import yfinance as yf
import hashlib
import json
import signal
import time
from datetime import datetime, timedelta

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

# Per-ticker timeout handler
class TickerTimeoutError(Exception):
    pass

def ticker_timeout_handler(signum, frame):
    raise TickerTimeoutError(f"yfinance call timed out")

def get_db_password():
    with open(os.path.expanduser('~/.hermes/.env')) as f:
        for line in f:
            if line.startswith('DB_PASSWORD='):
                return line.strip().split('=', 1)[1]
    return os.environ.get('PGPASSWORD', '')

def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )

def fetch_market_data(ticker, timeout_secs=10):
    """Fetch real market data from yfinance with hard timeout."""
    # Set alarm for Unix-based timeout
    old_handler = signal.signal(signal.SIGALRM, ticker_timeout_handler)
    signal.alarm(timeout_secs)
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period='1y')
        
        signal.alarm(0)  # Cancel alarm on success
        
        if hist.empty:
            return None
        
        current_price = float(hist['Close'].iloc[-1])
        
        # Calculate returns
        price_1d = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else current_price
        price_1w = float(hist['Close'].iloc[-5]) if len(hist) >= 5 else current_price
        price_1m = float(hist['Close'].iloc[-20]) if len(hist) >= 20 else current_price
        price_3m = float(hist['Close'].iloc[-60]) if len(hist) >= 60 else current_price
        price_6m = float(hist['Close'].iloc[-120]) if len(hist) >= 120 else current_price
        price_ytd = float(hist['Close'].iloc[0]) if len(hist) >= 1 else current_price
        
        returns = {
            '1d': ((current_price - price_1d) / price_1d) * 100,
            '1w': ((current_price - price_1w) / price_1w) * 100,
            '1m': ((current_price - price_1m) / price_1m) * 100,
            '3m': ((current_price - price_3m) / price_3m) * 100,
            '6m': ((current_price - price_6m) / price_6m) * 100,
            'ytd': ((current_price - price_ytd) / price_ytd) * 100,
        }
        
        # 52-week range
        week_52_high = float(hist['Close'].max())
        week_52_low = float(hist['Close'].min())
        from_52w_high = ((current_price - week_52_high) / week_52_high) * 100
        from_52w_low = ((current_price - week_52_low) / week_52_low) * 100
        
        # Volume trend
        volume_20d = float(hist['Volume'].iloc[-20:].mean()) if len(hist) >= 20 else float(hist['Volume'].mean())
        volume_5d = float(hist['Volume'].iloc[-5:].mean()) if len(hist) >= 5 else float(hist['Volume'].mean())
        volume_trend = (volume_5d / volume_20d - 1) * 100 if volume_20d > 0 else 0
        
        # Fundamental data from info
        pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 0
        market_cap = info.get('marketCap') or 0
        revenue = info.get('totalRevenue') or info.get('revenue') or 0
        profit_margin = info.get('profitMargins') or 0
        revenue_growth = info.get('revenueGrowth') or 0
        earnings_growth = info.get('earningsGrowth') or 0
        roe = info.get('returnOnEquity') or 0
        debt_to_equity = info.get('debtToEquity') or 0
        
        return {
            'price': current_price,
            'returns': returns,
            'from_52w_high': from_52w_high,
            'from_52w_low': from_52w_low,
            'volume_trend': volume_trend,
            'pe_ratio': pe_ratio,
            'market_cap': market_cap,
            'revenue': revenue,
            'profit_margin': profit_margin,
            'revenue_growth': revenue_growth,
            'earnings_growth': earnings_growth,
            'roe': roe,
            'debt_to_equity': debt_to_equity,
        }
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return None

def calculate_technical_score(data):
    """Calculate technical score from real price action."""
    if not data:
        return 50
    
    r = data['returns']
    score = 50
    
    # Momentum scoring (aggressive style: reward strong momentum)
    if r['1m'] > 20: score += 15
    elif r['1m'] > 10: score += 10
    elif r['1m'] > 5: score += 5
    elif r['1m'] < -10: score -= 15
    elif r['1m'] < -5: score -= 10
    
    if r['3m'] > 30: score += 10
    elif r['3m'] > 15: score += 5
    elif r['3m'] < -20: score -= 10
    
    if r['6m'] > 50: score += 10
    elif r['6m'] > 25: score += 5
    elif r['6m'] < -30: score -= 10
    
    # YTD performance
    if r['ytd'] > 50: score += 10
    elif r['ytd'] > 25: score += 5
    elif r['ytd'] < -30: score -= 10
    
    # 52-week position (buying near highs = momentum, near lows = value trap)
    if data['from_52w_high'] > -5: score += 10  # Near highs
    elif data['from_52w_high'] > -15: score += 5
    elif data['from_52w_high'] < -50: score -= 10  # Deep drawdown
    
    # Volume confirmation
    if data['volume_trend'] > 20: score += 5
    elif data['volume_trend'] < -20: score -= 5
    
    return max(0, min(100, score))

def calculate_fundamental_score(data):
    """Calculate fundamental score from real financial data."""
    if not data:
        return 50
    
    score = 50
    
    # Profitability
    if data['profit_margin'] > 0.30: score += 15
    elif data['profit_margin'] > 0.20: score += 10
    elif data['profit_margin'] > 0.10: score += 5
    elif data['profit_margin'] < 0: score -= 15
    
    # Growth
    if data['revenue_growth'] > 0.50: score += 15
    elif data['revenue_growth'] > 0.30: score += 10
    elif data['revenue_growth'] > 0.15: score += 5
    elif data['revenue_growth'] < 0: score -= 10
    
    if data['earnings_growth'] > 0.50: score += 10
    elif data['earnings_growth'] < 0: score -= 10
    
    # ROE
    if data['roe'] > 0.25: score += 10
    elif data['roe'] > 0.15: score += 5
    elif data['roe'] < 0: score -= 10
    
    # Valuation (P/E)
    pe = float(data['pe_ratio']) if data['pe_ratio'] else 0
    if pe > 0 and pe < 15: score += 10  # Cheap
    elif pe > 0 and pe < 25: score += 5
    elif pe > 100: score -= 10  # Expensive
    elif pe < 0: score -= 15  # Losing money
    
    # Balance sheet
    if data['debt_to_equity'] < 50: score += 5
    elif data['debt_to_equity'] > 200: score -= 10
    
    return max(0, min(100, score))

def get_sector_momentum_from_db(ticker):
    """Fetch live sector momentum score from database."""
    try:
        conn = connect_db()
        cur = conn.cursor()
        
        # Get ticker sector
        cur.execute("SELECT sector FROM ticker_sectors WHERE ticker = %s", (ticker,))
        row = cur.fetchone()
        if not row or not row[0]:
            conn.close()
            return 50
        
        sector_name = row[0]
        
        # Try exact match
        cur.execute("""
            SELECT momentum_score FROM sector_momentum 
            WHERE sector = %s ORDER BY computed_at DESC LIMIT 1
        """, (sector_name,))
        row = cur.fetchone()
        
        if row and row[0]:
            conn.close()
            return min(100, max(0, float(row[0])))
        
        # GICS mapping fallback
        gics_map = {
            'Technology': 'Technology', 'Healthcare': 'Healthcare',
            'Financial Services': 'Financials', 'Consumer Cyclical': 'Consumer Discretionary',
            'Consumer Defensive': 'Consumer Staples', 'Industrials': 'Industrials',
            'Communication Services': 'Communication Services', 'Energy': 'Energy',
            'Basic Materials': 'Materials', 'Real Estate': 'Real Estate',
            'Utilities': 'Utilities',
        }
        mapped = gics_map.get(sector_name, sector_name)
        cur.execute("""
            SELECT momentum_score FROM sector_momentum 
            WHERE sector ILIKE %s ORDER BY computed_at DESC LIMIT 1
        """, (f"%{mapped}%",))
        row = cur.fetchone()
        
        conn.close()
        if row and row[0]:
            return min(100, max(0, float(row[0])))
        return 50
    except Exception:
        return 50


def calculate_macro_score(data, sector_momentum=0):
    """Calculate macro alignment score with live sector momentum."""
    if not data:
        return 50
    
    score = 50
    
    # Market regime (using YTD as proxy)
    r = data['returns']
    if r['ytd'] > 30: score += 10  # Bull market
    elif r['ytd'] < -20: score -= 10  # Bear market
    
    # Sector momentum (LIVE from DB)
    if sector_momentum > 60: score += 15  # Hot sector
    elif sector_momentum > 50: score += 10
    elif sector_momentum > 40: score += 5
    elif sector_momentum < 30: score -= 10  # Cold sector
    elif sector_momentum < 20: score -= 15
    
    # Trend consistency (all timeframes aligned)
    if r['1d'] > 0 and r['1w'] > 0 and r['1m'] > 0:
        score += 10  # Strong uptrend
    elif r['1d'] < 0 and r['1w'] < 0 and r['1m'] < 0:
        score -= 10  # Strong downtrend
    
    return max(0, min(100, score))

def calculate_sentiment_score(data):
    """Calculate sentiment from price action (no news API yet)."""
    if not data:
        return 50
    
    score = 50
    r = data['returns']
    
    # Recent price action as sentiment proxy
    if r['1d'] > 5: score += 10
    elif r['1d'] > 2: score += 5
    elif r['1d'] < -5: score -= 10
    elif r['1d'] < -2: score -= 5
    
    # Recovery from lows = improving sentiment
    if data['from_52w_low'] > 50: score += 10
    elif data['from_52w_low'] > 20: score += 5
    
    return max(0, min(100, score))

def generate_live_grade(ticker, sector_momentum=0):
    """Generate a REAL grade based on live market data + sector momentum."""
    data = fetch_market_data(ticker)
    
    if not data:
        return None
    
    # Get live sector momentum if not provided
    if sector_momentum == 0:
        sector_momentum = get_sector_momentum_from_db(ticker)
    
    technical = calculate_technical_score(data)
    fundamental = calculate_fundamental_score(data)
    macro = calculate_macro_score(data, sector_momentum)
    sentiment = calculate_sentiment_score(data)
    
    # Composite grade (weights optimized for aggressive growth)
    vox_grade = int(
        technical * 0.30 +      # Momentum matters most
        fundamental * 0.25 +    # But fundamentals matter too
        macro * 0.20 +         # Market context (includes sector momentum)
        sentiment * 0.15 +     # Recent sentiment
        50 * 0.10              # Base (prevents extreme scores)
    )
    
    # Determine action
    if vox_grade >= 80:
        action = 'STRONG_BUY'
    elif vox_grade >= 65:
        action = 'BUY'
    elif vox_grade >= 50:
        action = 'HOLD'
    elif vox_grade >= 40:
        action = 'TRIM'
    else:
        action = 'SELL'
    
    # Create data hash to detect if market changed
    data_hash = hashlib.md5(json.dumps({
        'price': round(data['price'], 2),
        '1m': round(data['returns']['1m'], 2),
        '3m': round(data['returns']['3m'], 2),
    }, sort_keys=True).encode()).hexdigest()[:8]
    
    return {
        'technical': technical,
        'fundamental': fundamental,
        'macro': macro,
        'sentiment': sentiment,
        'vox_grade': vox_grade,
        'action': action,
        'current_price': data['price'],
        'returns': data['returns'],
        'data_hash': data_hash,
        'market_cap': data['market_cap'],
        'pe_ratio': data['pe_ratio'],
        'revenue_growth': data['revenue_growth'],
        'profit_margin': data['profit_margin'],
    }

def get_tickers_to_grade():
    """Get all tickers that need fresh grading, rotated by hour offset."""
    conn = connect_db()
    cur = conn.cursor()
    
    # Get all tickers from watchlist, positions, discovery_queue
    cur.execute("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM watchlist
            UNION
            SELECT ticker FROM positions WHERE shares > 0
            UNION
            SELECT ticker FROM discovery_queue WHERE status = 'pending'
            UNION
            SELECT ticker FROM vox_grades WHERE generated_at < NOW() - INTERVAL '1 day'
        ) t
        ORDER BY ticker
    """)
    
    tickers = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Rotate using hour-of-day so different tickers get processed each run
    # This prevents always grading A, AA, AAPL, etc.
    import datetime as dt
    hour = dt.datetime.now().hour
    batch_size = 10
    if len(tickers) > batch_size:
        num_batches = max(1, len(tickers) // batch_size)
        offset = (hour % num_batches) * batch_size
        tickers = tickers[offset:] + tickers[:offset]
    
    return tickers

def grade_ticker(ticker, sector_momentum=0, timeout_secs=12):
    """Grade a single ticker with live data and hard timeout."""
    # Set hard timeout on the entire grading operation
    old_handler = signal.signal(signal.SIGALRM, ticker_timeout_handler)
    signal.alarm(timeout_secs)
    try:
        result = generate_live_grade(ticker, sector_momentum)
        signal.alarm(0)  # Cancel alarm on success
        
        if not result:
            return None
        
        conn = connect_db()
        cur = conn.cursor()
        
        # Check if we already have this exact data hash (market hasn't changed)
        cur.execute("""
            SELECT id FROM vox_grades 
            WHERE ticker = %s AND data_hash = %s 
            ORDER BY generated_at DESC LIMIT 1
        """, (ticker, result['data_hash']))
        
        existing = cur.fetchone()
        
        if existing:
            # Market hasn't changed, just update timestamp
            cur.execute("""
                UPDATE vox_grades SET generated_at = NOW() 
                WHERE id = %s
            """, (existing[0],))
            conn.commit()
            conn.close()
            return {'updated': True, 'ticker': ticker, 'grade': result['vox_grade'], 'action': result['action']}
        
        # Market changed or new grade needed
        cur.execute("""
            INSERT INTO vox_grades (
                ticker, name, vox_grade, previous_grade, action,
                current_price, technical_score, fundamental_score, macro_score, sentiment_score,
                momentum_score, data_hash, catalysts, generated_at
            ) VALUES (%s, %s, %s, 
                (SELECT vox_grade FROM vox_grades WHERE ticker = %s ORDER BY generated_at DESC LIMIT 1),
                %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
        """, (
            ticker, ticker, result['vox_grade'], ticker, result['action'],
            result['current_price'], result['technical'], result['fundamental'],
            result['macro'], result['sentiment'], 0, result['data_hash'],
            f"Live: 1M={result['returns']['1m']:.1f}%, 3M={result['returns']['3m']:.1f}%, YTD={result['returns']['ytd']:.1f}%"
        ))
        
        conn.commit()
        conn.close()
        
        return {'updated': False, 'ticker': ticker, 'grade': result['vox_grade'], 'action': result['action']}
    except TickerTimeoutError:
        signal.alarm(0)
        return {'timeout': True, 'ticker': ticker, 'grade': None, 'action': None}
    except Exception as e:
        signal.alarm(0)
        raise e
    finally:
        signal.signal(signal.SIGALRM, old_handler)

def run_live_grading(batch_size=10):
    """Run live grading for all tickers."""
    print("=" * 70)
    print(f"VOX LIVE GRADING ENGINE — {datetime.now()}")
    print("=" * 70)
    
    tickers = get_tickers_to_grade()
    print(f"\nFound {len(tickers)} tickers needing grading. Processing {min(len(tickers), batch_size)} with LIVE market data...")
    
    graded = 0
    updated = 0
    failed = 0
    timed_out = 0
    
    for i, ticker in enumerate(tickers[:batch_size]):
        print(f"  [{i+1}/{min(len(tickers), batch_size)}] {ticker}...", end='', flush=True)
        try:
            result = grade_ticker(ticker, timeout_secs=12)
            
            if result is None:
                print(" FAILED")
                failed += 1
            elif result.get('timeout'):
                print(" TIMEOUT (12s)")
                timed_out += 1
            elif result.get('updated'):
                print(f" UNCHANGED (grade {result['grade']})")
                updated += 1
            else:
                print(f" GRADED {result['grade']} ({result['action']})")
                graded += 1
        except Exception as e:
            print(f" ERROR: {e}")
            failed += 1
        
        # Rate limit: 3s between tickers to prevent yfinance DNS/timeout issues
        time.sleep(3)
    
    print(f"\n{'='*70}")
    print(f"Results: {graded} newly graded, {updated} unchanged, {timed_out} timed out, {failed} failed")
    print(f"{'='*70}")
    
    return graded, updated, failed

if __name__ == '__main__':
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    run_live_grading(batch_size)
