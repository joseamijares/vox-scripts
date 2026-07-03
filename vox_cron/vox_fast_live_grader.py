#!/usr/bin/env python3
"""
VOX FAST LIVE GRADING ENGINE v2.1
Batches yfinance requests for speed. Processes all tickers in ~2 hours.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
import yfinance as yf
import hashlib
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'

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

def fetch_batch_data(tickers, period='1y'):
    """Fetch data for multiple tickers at once."""
    try:
        data = yf.download(tickers, period=period, progress=False, threads=True)
        return data
    except Exception as e:
        print(f"Batch fetch error: {e}")
        return None

def process_ticker(ticker, hist_data, info_data):
    """Process a single ticker's data."""
    try:
        if hist_data is None or hist_data.empty:
            return None
        
        # Get price data
        if 'Close' in hist_data.columns:
            closes = hist_data['Close']
        else:
            closes = hist_data.iloc[:, 0]  # First column
        
        if len(closes) == 0:
            return None
        
        current_price = float(closes.iloc[-1])
        
        # Calculate returns
        price_1d = float(closes.iloc[-2]) if len(closes) >= 2 else current_price
        price_1w = float(closes.iloc[-5]) if len(closes) >= 5 else current_price
        price_1m = float(closes.iloc[-20]) if len(closes) >= 20 else current_price
        price_3m = float(closes.iloc[-60]) if len(closes) >= 60 else current_price
        price_6m = float(closes.iloc[-120]) if len(closes) >= 120 else current_price
        price_ytd = float(closes.iloc[0])
        
        returns = {
            '1d': ((current_price - price_1d) / price_1d) * 100,
            '1w': ((current_price - price_1w) / price_1w) * 100,
            '1m': ((current_price - price_1m) / price_1m) * 100,
            '3m': ((current_price - price_3m) / price_3m) * 100,
            '6m': ((current_price - price_6m) / price_6m) * 100,
            'ytd': ((current_price - price_ytd) / price_ytd) * 100,
        }
        
        # 52-week range
        week_52_high = float(closes.max())
        week_52_low = float(closes.min())
        from_52w_high = ((current_price - week_52_high) / week_52_high) * 100
        from_52w_low = ((current_price - week_52_low) / week_52_low) * 100
        
        # Volume
        if 'Volume' in hist_data.columns:
            volumes = hist_data['Volume']
            volume_20d = float(volumes.iloc[-20:].mean()) if len(volumes) >= 20 else float(volumes.mean())
            volume_5d = float(volumes.iloc[-5:].mean()) if len(volumes) >= 5 else float(volumes.mean())
            volume_trend = (volume_5d / volume_20d - 1) * 100 if volume_20d > 0 else 0
        else:
            volume_trend = 0
        
        # Fundamental data
        info = info_data.get(ticker, {}) if info_data else {}
        pe_ratio = info.get('trailingPE') or info.get('forwardPE') or 0
        market_cap = info.get('marketCap') or 0
        revenue = info.get('totalRevenue') or info.get('revenue') or 0
        profit_margin = info.get('profitMargins') or 0
        revenue_growth = info.get('revenueGrowth') or 0
        earnings_growth = info.get('earningsGrowth') or 0
        roe = info.get('returnOnEquity') or 0
        debt_to_equity = info.get('debtToEquity') or 0
        
        # Calculate scores
        technical = calculate_technical_score(returns, from_52w_high, from_52w_low, volume_trend)
        fundamental = calculate_fundamental_score(pe_ratio, profit_margin, revenue_growth, earnings_growth, roe, debt_to_equity)
        macro = calculate_macro_score(returns)
        sentiment = calculate_sentiment_score(returns, from_52w_low)
        
        vox_grade = int(technical * 0.30 + fundamental * 0.25 + macro * 0.20 + sentiment * 0.15 + 50 * 0.10)
        
        if vox_grade >= 80: action = 'STRONG_BUY'
        elif vox_grade >= 65: action = 'BUY'
        elif vox_grade >= 50: action = 'HOLD'
        elif vox_grade >= 40: action = 'TRIM'
        else: action = 'SELL'
        
        data_hash = hashlib.md5(json.dumps({
            'price': round(current_price, 2),
            '1m': round(returns['1m'], 2),
            '3m': round(returns['3m'], 2),
        }, sort_keys=True).encode()).hexdigest()[:8]
        
        return {
            'ticker': ticker,
            'technical': technical,
            'fundamental': fundamental,
            'macro': macro,
            'sentiment': sentiment,
            'vox_grade': vox_grade,
            'action': action,
            'current_price': current_price,
            'returns': returns,
            'data_hash': data_hash,
            'market_cap': market_cap,
            'pe_ratio': pe_ratio,
            'revenue_growth': revenue_growth,
            'profit_margin': profit_margin,
        }
    except Exception as e:
        print(f"  Error processing {ticker}: {e}")
        return None

def calculate_technical_score(returns, from_52w_high, from_52w_low, volume_trend):
    score = 50
    r = returns
    
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
    
    if r['ytd'] > 50: score += 10
    elif r['ytd'] > 25: score += 5
    elif r['ytd'] < -30: score -= 10
    
    if from_52w_high > -5: score += 10
    elif from_52w_high > -15: score += 5
    elif from_52w_high < -50: score -= 10
    
    if volume_trend > 20: score += 5
    elif volume_trend < -20: score -= 5
    
    return max(0, min(100, score))

def calculate_fundamental_score(pe_ratio, profit_margin, revenue_growth, earnings_growth, roe, debt_to_equity):
    score = 50
    
    if profit_margin > 0.30: score += 15
    elif profit_margin > 0.20: score += 10
    elif profit_margin > 0.10: score += 5
    elif profit_margin < 0: score -= 15
    
    if revenue_growth > 0.50: score += 15
    elif revenue_growth > 0.30: score += 10
    elif revenue_growth > 0.15: score += 5
    elif revenue_growth < 0: score -= 10
    
    if earnings_growth > 0.50: score += 10
    elif earnings_growth < 0: score -= 10
    
    if roe > 0.25: score += 10
    elif roe > 0.15: score += 5
    elif roe < 0: score -= 10
    
    if pe_ratio > 0 and pe_ratio < 15: score += 10
    elif pe_ratio > 0 and pe_ratio < 25: score += 5
    elif pe_ratio > 100: score -= 10
    elif pe_ratio < 0: score -= 15
    
    if debt_to_equity < 50: score += 5
    elif debt_to_equity > 200: score -= 10
    
    return max(0, min(100, score))

def calculate_macro_score(returns):
    score = 50
    r = returns
    
    if r['ytd'] > 30: score += 10
    elif r['ytd'] < -20: score -= 10
    
    if r['1d'] > 0 and r['1w'] > 0 and r['1m'] > 0: score += 10
    elif r['1d'] < 0 and r['1w'] < 0 and r['1m'] < 0: score -= 10
    
    return max(0, min(100, score))

def calculate_sentiment_score(returns, from_52w_low):
    score = 50
    r = returns
    
    if r['1d'] > 5: score += 10
    elif r['1d'] > 2: score += 5
    elif r['1d'] < -5: score -= 10
    elif r['1d'] < -2: score -= 5
    
    if from_52w_low > 50: score += 10
    elif from_52w_low > 20: score += 5
    
    return max(0, min(100, score))

def get_tickers_to_grade():
    conn = connect_db()
    cur = conn.cursor()
    
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
    return tickers

def store_results(results):
    """Batch insert results."""
    conn = connect_db()
    cur = conn.cursor()
    
    inserted = 0
    updated = 0
    
    for result in results:
        if not result:
            continue
        
        ticker = result['ticker']
        
        # Check if data hash exists
        cur.execute("""
            SELECT id FROM vox_grades 
            WHERE ticker = %s AND data_hash = %s 
            ORDER BY generated_at DESC LIMIT 1
        """, (ticker, result['data_hash']))
        
        existing = cur.fetchone()
        
        if existing:
            cur.execute("UPDATE vox_grades SET generated_at = NOW() WHERE id = %s", (existing[0],))
            updated += 1
        else:
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
            inserted += 1
    
    conn.commit()
    conn.close()
    return inserted, updated

def run_fast_regrading(batch_size=50):
    print("=" * 70)
    print(f"VOX FAST LIVE GRADING ENGINE — {datetime.now()}")
    print("=" * 70)
    
    tickers = get_tickers_to_grade()
    print(f"\nGrading {len(tickers)} tickers with LIVE market data...")
    print(f"Batch size: {batch_size} (batched yfinance requests)")
    
    total_inserted = 0
    total_updated = 0
    total_failed = 0
    
    # Process in batches
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        print(f"\n  Batch {i//batch_size + 1}/{(len(tickers) + batch_size - 1)//batch_size}: {batch[0]} to {batch[-1]} ({len(batch)} tickers)")
        
        # Fetch batch data
        try:
            data = fetch_batch_data(batch)
            if data is None:
                print("  Batch fetch failed, trying individual...")
                # Fall back to individual
                for ticker in batch:
                    try:
                        stock = yf.Ticker(ticker)
                        hist = stock.history(period='1y')
                        info = stock.info
                        result = process_ticker(ticker, hist, {ticker: info})
                        if result:
                            inserted, updated = store_results([result])
                            total_inserted += inserted
                            total_updated += updated
                            print(f"    {ticker}: {result['vox_grade']} ({result['action']})")
                        else:
                            total_failed += 1
                            print(f"    {ticker}: FAILED")
                    except Exception as e:
                        total_failed += 1
                        print(f"    {ticker}: FAILED - {e}")
                continue
            
            # Process batch results
            results = []
            for ticker in batch:
                try:
                    if ticker in data.columns.get_level_values(1) if hasattr(data.columns, 'get_level_values') else [ticker]:
                        ticker_data = data.xs(ticker, level=1, axis=1) if hasattr(data.columns, 'get_level_values') else data
                        result = process_ticker(ticker, ticker_data, None)
                        if result:
                            results.append(result)
                            print(f"    {ticker}: {result['vox_grade']} ({result['action']})")
                        else:
                            total_failed += 1
                            print(f"    {ticker}: FAILED")
                except Exception as e:
                    total_failed += 1
                    print(f"    {ticker}: FAILED - {e}")
            
            # Store batch
            if results:
                inserted, updated = store_results(results)
                total_inserted += inserted
                total_updated += updated
                
        except Exception as e:
            print(f"  Batch error: {e}")
            total_failed += len(batch)
        
        print(f"  Batch complete: +{total_inserted} inserted, +{total_updated} updated, {total_failed} failed")
    
    print(f"\n{'='*70}")
    print(f"FINAL RESULTS: {total_inserted} newly graded, {total_updated} unchanged, {total_failed} failed")
    print(f"{'='*70}")
    
    return total_inserted, total_updated, total_failed

if __name__ == '__main__':
    batch_size = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    run_fast_regrading(batch_size)
