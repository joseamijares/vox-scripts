#!/usr/bin/env python3
"""
VOX TRADER TRACKER v1.0
Tracks famous traders on X/Twitter, their stock calls, and performance.

Features:
- Track trader profiles (Shay Boloor, etc.)
- Monitor their stock mentions and recommendations
- Score their call accuracy
- Alert when top traders mention new stocks
- Cross-reference with VOX grades for validation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
import json
from datetime import datetime, timedelta

def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=get_db_password(), dbname='railway', sslmode='require',
    )

# Famous traders to track
TRADER_UNIVERSE = {
    # Tech/Growth Traders
    'shay boloor': {'handle': '@shayboloor', 'style': 'tech_growth', 'focus': ['AI', 'semiconductors', 'cloud'], 'weight': 1.0},
    'cathie wood': {'handle': '@cathiewood', 'style': 'disruptive_innovation', 'focus': ['AI', 'genomics', 'fintech', 'crypto'], 'weight': 0.9},
    'gene munster': {'handle': '@munster_gene', 'style': 'tech_analyst', 'focus': ['AAPL', 'TSLA', 'AI'], 'weight': 0.85},
    'ross gerber': {'handle': '@gerberkawasaki', 'style': 'growth', 'focus': ['TSLA', 'tech', 'EV'], 'weight': 0.8},
    
    # Macro/Global Traders
    'raoul pal': {'handle': '@RaoulGMI', 'style': 'macro', 'focus': ['crypto', 'BTC', 'ETH', 'macro'], 'weight': 0.9},
    'lyn alden': {'handle': '@LynAldenContact', 'style': 'macro_value', 'focus': ['energy', 'commodities', 'macro'], 'weight': 0.85},
    'julian brigden': {'handle': '@julianbrigden', 'style': 'macro', 'focus': ['rates', 'FX', 'macro'], 'weight': 0.8},
    
    # Options/Day Traders
    'pete najarian': {'handle': '@petenajarian', 'style': 'options', 'focus': ['options_flow', 'unusual_activity'], 'weight': 0.75},
    'jon najarian': {'handle': '@jonnajarian', 'style': 'options', 'focus': ['options_flow', 'unusual_activity'], 'weight': 0.75},
    'tom sosnoff': {'handle': '@tastytrade', 'style': 'options_education', 'focus': ['options', 'volatility'], 'weight': 0.7},
    
    # Short Sellers / Activists
    'carson block': {'handle': '@CarsonBlock', 'style': 'activist_short', 'focus': ['fraud', 'shorts'], 'weight': 0.8},
    'jim chanos': {'handle': '@jimchanos', 'style': 'short_seller', 'focus': ['accounting', 'shorts'], 'weight': 0.75},
    
    # Crypto Traders
    'michael saylor': {'handle': '@saylor', 'style': 'bitcoin_maxi', 'focus': ['BTC', 'MSTR'], 'weight': 0.85},
    'anthony pompliano': {'handle': '@APompliano', 'style': 'crypto', 'focus': ['BTC', 'crypto', 'tech'], 'weight': 0.75},
    
    # Quant/Systematic
    'meb faber': {'handle': '@mebfaber', 'style': 'quant', 'focus': ['trend_following', 'global'], 'weight': 0.7},
    'wesley gray': {'handle': '@alphaarchitect', 'style': 'quant', 'focus': ['value', 'momentum'], 'weight': 0.7},
    
    # Mexican/EM Traders
    'carlos slim': {'handle': None, 'style': 'em_value', 'focus': ['Mexico', 'telecom', 'infrastructure'], 'weight': 0.6},
    'emerging market guru': {'handle': None, 'style': 'em', 'focus': ['EM', 'frontier', 'fintech'], 'weight': 0.5},
    
    # AI/Space/Nuclear Specialists
    'ark invest': {'handle': '@ARKInvest', 'style': 'disruptive', 'focus': ['AI', 'robotics', 'space', 'genomics'], 'weight': 0.9},
    'dr kathy wood': {'handle': '@ARKInvest', 'style': 'disruptive', 'focus': ['AI', 'robotics', 'space'], 'weight': 0.9},
    'elon musk': {'handle': '@elonmusk', 'style': 'meme_momentum', 'focus': ['TSLA', 'DOGE', 'X', 'space'], 'weight': 0.85},
    
    # Additional Popular X Traders
    'mrbeast': {'handle': '@MrBeast', 'style': 'retail_sentiment', 'focus': ['consumer', 'media', 'tech'], 'weight': 0.4},
    'dave portnoy': {'handle': '@stoolpresidente', 'style': 'meme_momentum', 'focus': ['meme_stocks', 'sports'], 'weight': 0.5},
    'keith gill': {'handle': '@TheRoaringKitty', 'style': 'meme_momentum', 'focus': ['meme_stocks', 'retail'], 'weight': 0.6},
    'james altucher': {'handle': '@jaltucher', 'style': 'crypto_ai', 'focus': ['crypto', 'AI', 'startups'], 'weight': 0.5},
    'ian cassel': {'handle': '@iancassel', 'style': 'microcap', 'focus': ['microcap', 'growth'], 'weight': 0.75},
    'microcap magician': {'handle': '@microcapmag', 'style': 'microcap', 'focus': ['microcap', 'biotech', 'tech'], 'weight': 0.6},
    'fintwit alpha': {'handle': '@fintwit_alpha', 'style': 'swing_trading', 'focus': ['momentum', 'technicals'], 'weight': 0.5},
    'swing trader': {'handle': '@swingtrader', 'style': 'swing', 'focus': ['swing', 'momentum'], 'weight': 0.4},
    'dividend growth': {'handle': '@dividendgrowth', 'style': 'dividend', 'focus': ['dividends', 'utilities'], 'weight': 0.3},
    'spac king': {'handle': '@spacking', 'style': 'spac', 'focus': ['SPAC', 'deals'], 'weight': 0.4},
    'biotech analyst': {'handle': '@biotechanalyst', 'style': 'biotech', 'focus': ['biotech', 'FDA', 'clinical'], 'weight': 0.6},
    'uranium insider': {'handle': '@uraniuminsider', 'style': 'commodity', 'focus': ['uranium', 'nuclear', 'CCJ'], 'weight': 0.7},
    'hydrogen evangelist': {'handle': '@hydrogenevangelist', 'style': 'thematic', 'focus': ['hydrogen', 'clean_energy'], 'weight': 0.5},
    'quantum computing': {'handle': '@quantumcomputing', 'style': 'thematic', 'focus': ['quantum', 'IONQ', 'IBM'], 'weight': 0.6},
    'ev analyst': {'handle': '@evanalyst', 'style': 'thematic', 'focus': ['EV', 'TSLA', 'battery'], 'weight': 0.5},
    'space investor': {'handle': '@spaceinvestor', 'style': 'thematic', 'focus': ['space', 'RKLB', 'ASTS'], 'weight': 0.6},
}

def init_tables():
    """Create trader tracking tables"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trader_profiles (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            handle VARCHAR(50),
            style VARCHAR(50),
            focus TEXT[],
            weight DECIMAL(3,2) DEFAULT 1.0,
            accuracy_score DECIMAL(5,2) DEFAULT 50.0,
            total_calls INTEGER DEFAULT 0,
            successful_calls INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(name)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trader_calls (
            id SERIAL PRIMARY KEY,
            trader_name VARCHAR(100) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            call_type VARCHAR(20) NOT NULL, -- 'buy', 'sell', 'hold', 'watch'
            price_at_call DECIMAL(10,2),
            target_price DECIMAL(10,2),
            stop_price DECIMAL(10,2),
            thesis TEXT,
            source VARCHAR(50), -- 'x_post', 'interview', 'newsletter', 'podcast'
            source_url TEXT,
            call_date TIMESTAMP DEFAULT NOW(),
            resolved BOOLEAN DEFAULT FALSE,
            result VARCHAR(20), -- 'hit_target', 'hit_stop', 'open', 'expired'
            return_pct DECIMAL(8,2),
            verified BOOLEAN DEFAULT FALSE
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trader_mentions (
            id SERIAL PRIMARY KEY,
            trader_name VARCHAR(100) NOT NULL,
            ticker VARCHAR(20) NOT NULL,
            mention_date TIMESTAMP DEFAULT NOW(),
            sentiment VARCHAR(20), -- 'bullish', 'bearish', 'neutral'
            context TEXT,
            source VARCHAR(50)
        )
    """)
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trader_alerts (
            id SERIAL PRIMARY KEY,
            alert_type VARCHAR(50) NOT NULL, -- 'new_call', 'high_conviction', 'consensus', 'contrarian'
            ticker VARCHAR(20) NOT NULL,
            traders TEXT[],
            avg_sentiment VARCHAR(20),
            vox_grade INTEGER,
            action_recommended VARCHAR(20),
            alert_date TIMESTAMP DEFAULT NOW(),
            delivered BOOLEAN DEFAULT FALSE
        )
    """)
    
    conn.commit()
    print("✅ Trader tracking tables created")
    
    # Seed trader profiles
    for name, data in TRADER_UNIVERSE.items():
        cur.execute("""
            INSERT INTO trader_profiles (name, handle, style, focus, weight)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
                handle = EXCLUDED.handle,
                style = EXCLUDED.style,
                focus = EXCLUDED.focus,
                weight = EXCLUDED.weight
        """, (name, data['handle'], data['style'], data['focus'], data['weight']))
    
    conn.commit()
    print(f"✅ {len(TRADER_UNIVERSE)} trader profiles seeded")
    
    conn.close()

def add_trader_call(trader_name, ticker, call_type, price_at_call=None, target_price=None, 
                    stop_price=None, thesis=None, source='manual', source_url=None):
    """Record a trader call"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO trader_calls (trader_name, ticker, call_type, price_at_call, target_price, 
                                  stop_price, thesis, source, source_url)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (trader_name, ticker, call_type, price_at_call, target_price, 
          stop_price, thesis, source, source_url))
    
    conn.commit()
    conn.close()
    print(f"✅ Recorded {trader_name} {call_type} call on {ticker}")

def get_trader_leaderboard():
    """Get trader performance leaderboard"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tp.name,
            tp.handle,
            tp.style,
            tp.weight,
            tp.accuracy_score,
            tp.total_calls,
            tp.successful_calls,
            CASE WHEN tp.total_calls > 0 
                THEN ROUND(tp.successful_calls::numeric / tp.total_calls * 100, 1)
                ELSE 0 
            END as win_rate
        FROM trader_profiles tp
        ORDER BY tp.accuracy_score DESC, tp.weight DESC
        LIMIT 20
    """)
    
    traders = cur.fetchall()
    conn.close()
    return traders

def get_recent_calls(days=7, limit=20):
    """Get recent trader calls"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tc.trader_name,
            tc.ticker,
            tc.call_type,
            tc.price_at_call,
            tc.target_price,
            tc.stop_price,
            tc.thesis,
            tc.source,
            tc.call_date,
            vg.vox_grade,
            vg.action as vox_action
        FROM trader_calls tc
        LEFT JOIN vox_grades vg ON tc.ticker = vg.ticker
        WHERE tc.call_date > NOW() - INTERVAL '%s days'
        ORDER BY tc.call_date DESC
        LIMIT %s
    """, (days, limit))
    
    calls = cur.fetchall()
    conn.close()
    return calls

def find_consensus_trades():
    """Find tickers with multiple trader mentions"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            tc.ticker,
            COUNT(DISTINCT tc.trader_name) as trader_count,
            ARRAY_AGG(DISTINCT tc.trader_name) as traders,
            AVG(CASE WHEN tc.call_type = 'buy' THEN 1 ELSE 0 END) as buy_ratio,
            MAX(tc.call_date) as latest_call
        FROM trader_calls tc
        WHERE tc.call_date > NOW() - INTERVAL '30 days'
          AND tc.resolved = FALSE
        GROUP BY tc.ticker
        HAVING COUNT(DISTINCT tc.trader_name) >= 2
        ORDER BY trader_count DESC, latest_call DESC
        LIMIT 10
    """)
    
    consensus = cur.fetchall()
    conn.close()
    return consensus

def generate_weekly_digest():
    """Generate weekly trader activity digest"""
    leaderboard = get_trader_leaderboard()
    recent_calls = get_recent_calls(7, 10)
    consensus = find_consensus_trades()
    
    lines = [
        "🎯 VOX TRADER TRACKER — WEEKLY DIGEST",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "📊 TOP TRADERS (by accuracy)",
        "-" * 60,
    ]
    
    for i, trader in enumerate(leaderboard[:10], 1):
        name, handle, style, weight, accuracy, total, successful, win_rate = trader
        lines.append(f"{i}. {name} ({handle or 'N/A'})")
        lines.append(f"   Style: {style} | Accuracy: {accuracy:.0f} | Win Rate: {win_rate}% | Calls: {total}")
    
    lines.extend([
        "",
        "🔥 RECENT CALLS (last 7 days)",
        "-" * 60,
    ])
    
    for call in recent_calls[:5]:
        trader, ticker, call_type, price, target, stop, thesis, source, date, vox_grade, vox_action = call
        lines.append(f"• {trader}: {call_type.upper()} {ticker} @ ${price or 'N/A'}")
        lines.append(f"  Target: ${target or 'N/A'} | Stop: ${stop or 'N/A'}")
        lines.append(f"  VOX Grade: {vox_grade or 'N/A'} | VOX Action: {vox_action or 'N/A'}")
        if thesis:
            lines.append(f"  Thesis: {thesis[:100]}...")
    
    lines.extend([
        "",
        "🤝 CONSENSUS TRADES (2+ traders)",
        "-" * 60,
    ])
    
    for cons in consensus[:5]:
        ticker, count, traders, buy_ratio, latest = cons
        sentiment = "BULLISH" if buy_ratio > 0.5 else "BEARISH" if buy_ratio < 0.5 else "MIXED"
        lines.append(f"• {ticker}: {count} traders | {sentiment} | Latest: {latest.strftime('%m/%d')}")
        lines.append(f"  Traders: {', '.join(traders[:3])}")
    
    lines.extend([
        "",
        "-" * 60,
        "💡 TIP: When 3+ top traders agree on a ticker with VOX grade 70+, it's high conviction.",
    ])
    
    return "\n".join(lines)

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'digest'
    
    if action == 'init':
        init_tables()
    elif action == 'digest':
        print(generate_weekly_digest())
    elif action == 'leaderboard':
        traders = get_trader_leaderboard()
        print("\n🏆 TRADER LEADERBOARD")
        print("-" * 80)
        print(f"{'Rank':<5} {'Name':<25} {'Style':<20} {'Accuracy':<10} {'Win Rate':<10} {'Calls'}")
        print("-" * 80)
        for i, t in enumerate(traders, 1):
            name, handle, style, weight, accuracy, total, successful, win_rate = t
            print(f"{i:<5} {name:<25} {style:<20} {accuracy:<10.0f} {win_rate:<10}% {total}")
    elif action == 'consensus':
        consensus = find_consensus_trades()
        print("\n🤝 CONSENSUS TRADES")
        for c in consensus:
            ticker, count, traders, buy_ratio, latest = c
            print(f"{ticker}: {count} traders, {buy_ratio:.0%} bullish, latest {latest.strftime('%m/%d')}")
    elif action == 'add_call':
        if len(sys.argv) < 5:
            print("Usage: add_call <trader_name> <ticker> <buy|sell|hold> [price] [target] [stop] [thesis]")
            return
        add_trader_call(sys.argv[2], sys.argv[3], sys.argv[4], 
                       float(sys.argv[5]) if len(sys.argv) > 5 else None,
                       float(sys.argv[6]) if len(sys.argv) > 6 else None,
                       float(sys.argv[7]) if len(sys.argv) > 7 else None,
                       sys.argv[8] if len(sys.argv) > 8 else None)
    else:
        print("Usage: init, digest, leaderboard, consensus, add_call <trader> <ticker> <type>")

if __name__ == '__main__':
    main()
