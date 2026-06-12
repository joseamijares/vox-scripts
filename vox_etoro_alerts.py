#!/usr/bin/env python3
"""
VOX eToro Alert Monitor
Tracks stop losses, targets, and portfolio risk in real-time
"""

import json
import os
import urllib.request
from datetime import datetime

# Load portfolio
PORTFOLIO_FILE = os.path.expanduser('~/.hermes/scripts/vox_etoro_portfolio.json')
POLYGON_KEY = None

def load_env():
    global POLYGON_KEY
    env_path = os.path.expanduser('~/.hermes/.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith('POLYGON_API_KEY='):
                    POLYGON_KEY = line.strip().split('=', 1)[1].strip().strip('"').strip("'")

def get_price(ticker):
    """Get current price from Polygon.io"""
    if not POLYGON_KEY:
        return None
    try:
        url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={POLYGON_KEY}"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read())
            if data.get('results') and len(data['results']) > 0:
                return data['results'][0]['c']
    except Exception:
        pass
    return None

def check_alerts():
    """Check all positions against stops and targets"""
    if not os.path.exists(PORTFOLIO_FILE):
        print("❌ Portfolio file not found")
        return
    
    with open(PORTFOLIO_FILE) as f:
        portfolio = json.load(f)
    
    load_env()
    
    alerts_triggered = []
    warnings = []
    
    print(f"🔍 VOX eToro Alert Check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    for ticker, position in portfolio['positions'].items():
        current_price = get_price(ticker)
        if not current_price:
            print(f"⚠️  Could not fetch price for {ticker}")
            continue
        
        entry = position['price']
        shares = position['shares']
        net_value = shares * current_price
        pl = net_value - position['net_value']
        pl_pct = (current_price / entry - 1) * 100
        
        # Check stops
        stop_key = f"{ticker}_stop"
        if stop_key in portfolio['alerts']:
            stop = portfolio['alerts'][stop_key]
            if current_price <= stop:
                alerts_triggered.append({
                    'type': 'STOP',
                    'ticker': ticker,
                    'price': current_price,
                    'stop': stop,
                    'pl': pl
                })
        
        # Check targets
        # Load graded data for targets
        try:
            with open(os.path.expanduser('~/.hermes/scripts/vox_watchlist_graded.json')) as f:
                graded = json.load(f)
            stock = next((s for s in graded['results'] if s['ticker'] == ticker), None)
            if stock:
                t1 = stock.get('target_1', 0)
                t2 = stock.get('target_2', 0)
                
                if t1 > 0 and current_price >= t1:
                    warnings.append({
                        'type': 'T1',
                        'ticker': ticker,
                        'price': current_price,
                        'target': t1,
                        'pl': pl
                    })
                
                if t2 > 0 and current_price >= t2:
                    alerts_triggered.append({
                        'type': 'T2',
                        'ticker': ticker,
                        'price': current_price,
                        'target': t2,
                        'pl': pl
                    })
        except Exception:
            pass
        
        # Display status
        emoji = "🟢" if pl >= 0 else "🔴"
        print(f"{emoji} {ticker:6s} | ${current_price:8.2f} | P/L: ${pl:+8.2f} ({pl_pct:+5.1f}%)")
    
    # Portfolio level checks
    total_value = sum(p['shares'] * get_price(t) for t, p in portfolio['positions'].items() if get_price(t))
    if total_value > 0:
        print(f"\n📊 Portfolio Value: ${total_value:.2f}")
        
        # Check if speculative > 60%
        speculative_tickers = ['MIRA', 'CORZ', 'SIDU']
        spec_value = sum(
            portfolio['positions'][t]['shares'] * get_price(t)
            for t in speculative_tickers
            if t in portfolio['positions'] and get_price(t)
        )
        spec_pct = (spec_value / total_value * 100) if total_value > 0 else 0
        
        if spec_pct > 60:
            alerts_triggered.append({
                'type': 'REBALANCE',
                'message': f'Speculative exposure at {spec_pct:.1f}% — consider trimming'
            })
        
        print(f"  Speculative: {spec_pct:.1f}% (MIRA + CORZ + SIDU)")
    
    # Print alerts
    if alerts_triggered:
        print(f"\n🚨 ALERTS TRIGGERED:")
        for alert in alerts_triggered:
            if alert['type'] == 'STOP':
                print(f"  🔴 STOP LOSS: {alert['ticker']} at ${alert['price']:.2f} (stop: ${alert['stop']:.2f})")
            elif alert['type'] == 'T2':
                print(f"  🎯 T2 TARGET: {alert['ticker']} at ${alert['price']:.2f} — SELL 50%")
            elif alert['type'] == 'REBALANCE':
                print(f"  ⚠️  {alert['message']}")
    
    if warnings:
        print(f"\n⚠️  WARNINGS:")
        for w in warnings:
            print(f"  🎯 T1 TARGET: {w['ticker']} at ${w['price']:.2f} — Consider selling 50%")
    
    if not alerts_triggered and not warnings:
        print(f"\n✅ No alerts — portfolio within parameters")
    
    print(f"\n{'=' * 80}")

if __name__ == '__main__':
    check_alerts()
