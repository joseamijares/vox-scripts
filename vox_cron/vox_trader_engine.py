#!/usr/bin/env python3
"""
VOX Trader Engine v2.0
Unifies vox_trader_tracker.py (weekly digest + morning digest) into one engine.
- Seeds trader profiles daily
- Emits a morning digest on weekdays
- Emits a full weekly digest on Tuesdays
- Tracks consensus trades and leaderboard
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
import json
from datetime import datetime, timedelta


def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))


def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port=35577, user='postgres',
        password=get_db_password(), dbname='railway', sslmode='require',
    )


TRADER_UNIVERSE = {
    'shay boloor': {'handle': '@shayboloor', 'style': 'tech_growth', 'focus': ['AI', 'semiconductors', 'cloud'], 'weight': 1.0},
    'cathie wood': {'handle': '@cathiewood', 'style': 'disruptive_innovation', 'focus': ['AI', 'genomics', 'fintech', 'crypto'], 'weight': 0.9},
    'gene munster': {'handle': '@munster_gene', 'style': 'tech_analyst', 'focus': ['AAPL', 'TSLA', 'AI'], 'weight': 0.85},
    'ross gerber': {'handle': '@gerberkawasaki', 'style': 'growth', 'focus': ['TSLA', 'tech', 'EV'], 'weight': 0.8},
    'raoul pal': {'handle': '@RaoulGMI', 'style': 'macro', 'focus': ['crypto', 'BTC', 'ETH', 'macro'], 'weight': 0.9},
    'lyn alden': {'handle': '@LynAldenContact', 'style': 'macro_value', 'focus': ['energy', 'commodities', 'macro'], 'weight': 0.85},
    'julian brigden': {'handle': '@julianbrigden', 'style': 'macro', 'focus': ['rates', 'FX', 'macro'], 'weight': 0.8},
    'pete najarian': {'handle': '@petenajarian', 'style': 'options', 'focus': ['options_flow', 'unusual_activity'], 'weight': 0.75},
    'jon najarian': {'handle': '@jonnajarian', 'style': 'options', 'focus': ['options_flow', 'unusual_activity'], 'weight': 0.75},
    'tom sosnoff': {'handle': '@tastytrade', 'style': 'options_education', 'focus': ['options', 'volatility'], 'weight': 0.7},
    'carson block': {'handle': '@CarsonBlock', 'style': 'activist_short', 'focus': ['fraud', 'shorts'], 'weight': 0.8},
    'jim chanos': {'handle': '@jimchanos', 'style': 'short_seller', 'focus': ['accounting', 'shorts'], 'weight': 0.75},
    'michael saylor': {'handle': '@saylor', 'style': 'bitcoin_maxi', 'focus': ['BTC', 'MSTR'], 'weight': 0.85},
    'anthony pompliano': {'handle': '@APompliano', 'style': 'crypto', 'focus': ['BTC', 'crypto', 'tech'], 'weight': 0.75},
    'meb faber': {'handle': '@mebfaber', 'style': 'quant', 'focus': ['trend_following', 'global'], 'weight': 0.7},
    'wesley gray': {'handle': '@alphaarchitect', 'style': 'quant', 'focus': ['value', 'momentum'], 'weight': 0.7},
    'ark invest': {'handle': '@ARKInvest', 'style': 'disruptive', 'focus': ['AI', 'robotics', 'space', 'genomics'], 'weight': 0.9},
    'elon musk': {'handle': '@elonmusk', 'style': 'meme_momentum', 'focus': ['TSLA', 'DOGE', 'X', 'space'], 'weight': 0.85},
    'ian cassel': {'handle': '@iancassel', 'style': 'microcap', 'focus': ['microcap', 'growth'], 'weight': 0.75},
    'biotech analyst': {'handle': '@biotechanalyst', 'style': 'biotech', 'focus': ['biotech', 'FDA', 'clinical'], 'weight': 0.6},
    'uranium insider': {'handle': '@uraniuminsider', 'style': 'commodity', 'focus': ['uranium', 'nuclear', 'CCJ'], 'weight': 0.7},
}


def init_tables(conn):
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
            call_type VARCHAR(20) NOT NULL,
            price_at_call DECIMAL(10,2),
            target_price DECIMAL(10,2),
            stop_price DECIMAL(10,2),
            thesis TEXT,
            source VARCHAR(50),
            source_url TEXT,
            call_date TIMESTAMP DEFAULT NOW(),
            resolved BOOLEAN DEFAULT FALSE,
            result VARCHAR(20),
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
            sentiment VARCHAR(20),
            context TEXT,
            source VARCHAR(50)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trader_alerts (
            id SERIAL PRIMARY KEY,
            alert_type VARCHAR(50) NOT NULL,
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
    cur.close()


def get_trader_leaderboard(conn, limit=10):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            tp.name, tp.handle, tp.style, tp.weight, tp.accuracy_score,
            tp.total_calls, tp.successful_calls,
            CASE WHEN tp.total_calls > 0 
                THEN ROUND(tp.successful_calls::numeric / tp.total_calls * 100, 1)
                ELSE 0 
            END as win_rate
        FROM trader_profiles tp
        ORDER BY tp.accuracy_score DESC, tp.weight DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    return rows


def get_recent_calls(conn, days=7, limit=10):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            tc.trader_name, tc.ticker, tc.call_type, tc.price_at_call,
            tc.target_price, tc.stop_price, tc.thesis, tc.source, tc.call_date,
            vg.vox_grade, vg.action
        FROM trader_calls tc
        LEFT JOIN vox_grades vg ON tc.ticker = vg.ticker
        WHERE tc.call_date > NOW() - INTERVAL '%s days'
        ORDER BY tc.call_date DESC
        LIMIT %s
    """, (days, limit))
    rows = cur.fetchall()
    cur.close()
    return rows


def find_consensus_trades(conn, min_traders=2, days=30):
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            tc.ticker,
            COUNT(DISTINCT tc.trader_name) as trader_count,
            ARRAY_AGG(DISTINCT tc.trader_name) as traders,
            AVG(CASE WHEN tc.call_type = 'buy' THEN 1 ELSE 0 END) as buy_ratio,
            MAX(tc.call_date) as latest_call
        FROM trader_calls tc
        WHERE tc.call_date > NOW() - INTERVAL '%s days'
          AND tc.resolved = FALSE
        GROUP BY tc.ticker
        HAVING COUNT(DISTINCT tc.trader_name) >= %s
        ORDER BY trader_count DESC, latest_call DESC
        LIMIT 10
    """, (days, min_traders))
    rows = cur.fetchall()
    cur.close()
    return rows


def generate_morning_digest(conn):
    recent = get_recent_calls(conn, days=1, limit=5)
    consensus = find_consensus_trades(conn, min_traders=2, days=7)
    lines = [
        "🌅 VOX TRADER MORNING DIGEST",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "-" * 60,
    ]
    if recent:
        lines.append("🔔 Recent Calls (last 24h):")
        for call in recent:
            trader, ticker, ctype, price, target, stop, thesis, source, date, vox_grade, action = call
            lines.append(f"  {trader}: {ctype.upper()} {ticker} @ ${price or 'N/A'} | VOX: {vox_grade or 'N/A'} {action or ''}")
    else:
        lines.append("No new trader calls in the last 24h.")
    if consensus:
        lines.append("\n🤝 Consensus Trades (2+ traders, 7 days):")
        for c in consensus[:3]:
            ticker, count, traders, buy_ratio, latest = c
            sentiment = "BULLISH" if buy_ratio > 0.5 else "BEARISH" if buy_ratio < 0.5 else "MIXED"
            lines.append(f"  {ticker}: {count} traders | {sentiment} | Latest: {latest.strftime('%m/%d')}")
    return "\n".join(lines)


def generate_weekly_digest(conn):
    leaderboard = get_trader_leaderboard(conn, 10)
    recent_calls = get_recent_calls(conn, 7, 10)
    consensus = find_consensus_trades(conn, min_traders=2, days=30)
    lines = [
        "🎯 VOX TRADER TRACKER — WEEKLY DIGEST",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "📊 TOP TRADERS (by accuracy)",
        "-" * 60,
    ]
    for i, trader in enumerate(leaderboard, 1):
        name, handle, style, weight, accuracy, total, successful, win_rate = trader
        lines.append(f"{i}. {name} ({handle or 'N/A'})")
        lines.append(f"   Style: {style} | Accuracy: {accuracy:.0f} | Win Rate: {win_rate}% | Calls: {total}")
    lines.extend(["", "🔥 RECENT CALLS (last 7 days)", "-" * 60])
    for call in recent_calls[:5]:
        trader, ticker, ctype, price, target, stop, thesis, source, date, vox_grade, action = call
        lines.append(f"• {trader}: {ctype.upper()} {ticker} @ ${price or 'N/A'}")
        lines.append(f"  Target: ${target or 'N/A'} | Stop: ${stop or 'N/A'}")
        lines.append(f"  VOX Grade: {vox_grade or 'N/A'} | VOX Action: {action or 'N/A'}")
    lines.extend(["", "🤝 CONSENSUS TRADES (2+ traders)", "-" * 60])
    for cons in consensus[:5]:
        ticker, count, traders, buy_ratio, latest = cons
        sentiment = "BULLISH" if buy_ratio > 0.5 else "BEARISH" if buy_ratio < 0.5 else "MIXED"
        lines.append(f"• {ticker}: {count} traders | {sentiment} | Latest: {latest.strftime('%m/%d')}")
        lines.append(f"  Traders: {', '.join(traders[:3])}")
    return "\n".join(lines)


def main():
    conn = connect()
    init_tables(conn)
    weekday = datetime.now().weekday()
    if weekday == 1:  # Tuesday weekly digest
        print(generate_weekly_digest(conn))
    else:
        print(generate_morning_digest(conn))
    conn.close()


if __name__ == '__main__':
    main()
