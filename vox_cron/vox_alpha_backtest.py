#!/usr/bin/env python3
"""
VOX Alpha Backtest Harness
Replays signals_normalized against price_history with T+1 open execution.
No broker required. Writes synthetic trades to backtest_trades and metrics to backtest_runs.
"""

import os
import sys
import json
import math
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = int(os.environ.get('DB_PORT', '35577'))
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD') or os.environ.get('PGPASSWORD')

HORIZONS = [5, 20, 60]


def connect_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def price_lookup(cursor):
    """Return dict: ticker -> sorted list of (date, open, close, high, low)"""
    cursor.execute("""
        SELECT ticker, date, open, close, high, low
        FROM price_history
        ORDER BY ticker, date
    """)
    prices = defaultdict(list)
    for row in cursor.fetchall():
        prices[row['ticker'].upper()].append({
            'date': row['date'],
            'open': row['open'],
            'close': row['close'],
            'high': row['high'],
            'low': row['low']
        })
    return prices


def next_trading_day(prices, ticker, from_date, offset=1):
    """Return price dict for ticker on (from_date + offset) trading days, or None."""
    seq = prices.get(ticker.upper())
    if not seq:
        return None
    # find index of from_date or the next available date
    idx = 0
    for i, p in enumerate(seq):
        if p['date'] >= from_date:
            idx = i
            break
    target = idx + offset
    if 0 <= target < len(seq):
        return seq[target]
    return None


def price_on_or_after(prices, ticker, target_date):
    seq = prices.get(ticker.upper())
    if not seq:
        return None
    for p in seq:
        if p['date'] >= target_date:
            return p
    return None


def get_universe(cursor, universe_name, start_date, end_date):
    if universe_name == 'all_positions':
        cursor.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0")
        return [r['ticker'].upper() for r in cursor.fetchall()]
    if universe_name == 'signals':
        cursor.execute("""
            SELECT DISTINCT ticker FROM signals_normalized
            WHERE as_of_date BETWEEN %s AND %s
        """, (start_date, end_date))
        return [r['ticker'].upper() for r in cursor.fetchall()]
    # comma-separated list
    return [t.strip().upper() for t in universe_name.split(',') if t.strip()]


def get_signals(cursor, analyst_id, start_date, end_date, tickers=None):
    q = """
        SELECT id, analyst_id, ticker, as_of_date, signal, score, confidence, rationale
        FROM signals_normalized
        WHERE analyst_id = %s
          AND as_of_date BETWEEN %s AND %s
    """
    args = [analyst_id, start_date, end_date]
    if tickers:
        q += " AND ticker IN %s"
        args.append(tuple(tickers))
    q += " ORDER BY ticker, as_of_date"
    cursor.execute(q, args)
    return cursor.fetchall()


def simulate_trade(signal, prices, notional, stop_loss_pct, max_holding_days):
    """Simulate one trade per signal at T+1 open; exit by horizon or stop."""
    ticker = signal['ticker'].upper()
    entry_day = next_trading_day(prices, ticker, signal['as_of_date'], offset=1)
    if not entry_day or entry_day['open'] is None or entry_day['open'] <= 0:
        return None

    entry_price = float(entry_day['open'])
    direction = 1 if signal['score'] > 0 else -1 if signal['score'] < 0 else 0
    if direction == 0:
        return None

    shares = notional / entry_price
    stop_price = entry_price * (1 - stop_loss_pct * direction) if stop_loss_pct else None
    # max_holding_days selects the horizon; if None use first available HORIZONS
    horizon = max_holding_days or HORIZONS[0]
    exit_day = next_trading_day(prices, ticker, entry_day['date'], offset=horizon)
    exit_reason = 'horizon_hit'

    if stop_loss_pct:
        # scan daily closes between entry+1 and exit
        for i in range(1, horizon):
            day = next_trading_day(prices, ticker, entry_day['date'], offset=i)
            if not day:
                break
            day_high = float(day['high']) if day['high'] is not None else None
            day_low = float(day['low']) if day['low'] is not None else None
            # For long: stop if low <= stop_price; for short: high >= stop_price
            if direction > 0 and day_low is not None and day_low <= stop_price:
                exit_day = day
                exit_reason = 'stop_loss'
                break
            if direction < 0 and day_high is not None and day_high >= stop_price:
                exit_day = day
                exit_reason = 'stop_loss'
                break

    if not exit_day or exit_day['close'] is None:
        return None

    exit_price = float(exit_day['close'])
    pnl_pct = (exit_price / entry_price - 1.0) * direction * 100.0
    return {
        'ticker': ticker,
        'signal_id': signal['id'],
        'entry_date': entry_day['date'],
        'entry_price': entry_price,
        'exit_date': exit_day['date'],
        'exit_price': exit_price,
        'holding_days': (exit_day['date'] - entry_day['date']).days,
        'pnl_pct': pnl_pct,
        'exit_reason': exit_reason,
        'raw_return_bps': int(pnl_pct * 100),
        'direction': direction,
        'metadata': {
            'score': float(signal['score']),
            'confidence': float(signal['confidence']),
            'rationale': signal['rationale']
        }
    }


def sharpe_ratio(returns):
    if not returns or len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    std = math.sqrt(variance) if variance > 0 else 0
    return mean / std if std > 0 else 0.0


def max_drawdown(equity_curve):
    peak = -float('inf')
    max_dd = 0.0
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = (peak - val) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
    return max_dd


def compute_metrics(trades, per_horizon=True):
    metrics = {}
    all_returns = [t['pnl_pct'] for t in trades]
    if all_returns:
        metrics['overall'] = {
            'trades': len(trades),
            'hit_rate': sum(1 for r in all_returns if r > 0) / len(all_returns),
            'avg_return': sum(all_returns) / len(all_returns),
            'sharpe': sharpe_ratio(all_returns),
            'max_drawdown': None
        }
    else:
        metrics['overall'] = {'trades': 0}

    if per_horizon:
        for horizon in HORIZONS:
            htrades = [t for t in trades if t['holding_days'] <= horizon]
            if not htrades:
                continue
            rets = [t['pnl_pct'] for t in htrades]
            metrics[f'horizon_{horizon}'] = {
                'trades': len(htrades),
                'hit_rate': sum(1 for r in rets if r > 0) / len(rets),
                'avg_return': sum(rets) / len(rets),
                'sharpe': sharpe_ratio(rets)
            }

    return metrics


def run_backtest(analyst_id, start_date, end_date, universe='signals',
                 notional=10000, stop_loss_pct=0.08, max_holding_days=20,
                 quiet=False):
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    run_id = None
    try:
        cursor.execute("""
            INSERT INTO backtest_runs (analyst_id, start_date, end_date, universe,
                                       strategy_config, status)
            VALUES (%s, %s, %s, %s, %s, 'running')
            RETURNING run_id
        """, (analyst_id, start_date, end_date, universe,
              json.dumps({
                  'notional': notional,
                  'stop_loss_pct': stop_loss_pct,
                  'max_holding_days': max_holding_days,
                  'execution': 'T+1_open'
              })))
        run_id = cursor.fetchone()['run_id']
        conn.commit()

        prices = price_lookup(cursor)
        tickers = get_universe(cursor, universe, start_date, end_date)
        signals = get_signals(cursor, analyst_id, start_date, end_date, tickers)

        trades = []
        for sig in signals:
            trade = simulate_trade(sig, prices, notional, stop_loss_pct, max_holding_days)
            if trade:
                trades.append(trade)

        # Persist trades
        for t in trades:
            cursor.execute("""
                INSERT INTO backtest_trades
                (run_id, ticker, signal_id, entry_date, entry_price, exit_date, exit_price,
                 holding_days, pnl_pct, exit_reason, raw_return_bps, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (run_id, t['ticker'], t['signal_id'], t['entry_date'], t['entry_price'],
                  t['exit_date'], t['exit_price'], t['holding_days'], t['pnl_pct'],
                  t['exit_reason'], t['raw_return_bps'], json.dumps(t['metadata'])))

        metrics = compute_metrics(trades)
        cursor.execute("""
            UPDATE backtest_runs
            SET status = 'complete', metrics = %s, completed_at = now()
            WHERE run_id = %s
        """, (json.dumps(metrics), run_id))
        conn.commit()

        if not quiet:
            print(f"Backtest complete: {run_id}")
            print(f"Signals: {len(signals)} | Trades: {len(trades)}")
            print(json.dumps(metrics, indent=2))
        return run_id, metrics

    except Exception as e:
        if run_id:
            cursor.execute("""
                UPDATE backtest_runs SET status = 'failed', error_log = %s
                WHERE run_id = %s
            """, (str(e), run_id))
            conn.commit()
        print(f"Backtest failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VOX Alpha Backtest Harness')
    parser.add_argument('--analyst', required=True, help='analyst_id to backtest')
    parser.add_argument('--start-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--end-date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--universe', default='signals', help='signals | all_positions | TICKER,TICKER')
    parser.add_argument('--notional', type=float, default=10000)
    parser.add_argument('--stop-loss', type=float, default=0.08)
    parser.add_argument('--max-holding-days', type=int, default=20)
    args = parser.parse_args()
    run_backtest(
        analyst_id=args.analyst,
        start_date=args.start_date,
        end_date=args.end_date,
        universe=args.universe,
        notional=args.notional,
        stop_loss_pct=args.stop_loss,
        max_holding_days=args.max_holding_days
    )
