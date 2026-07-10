#!/usr/bin/env python3
"""
VOX Alpha Signal Adapter
Adopts virattt/ai-hedge-fund Analyst -> Signal contract on top of existing VOX tables.

Read-only adapters map source tables into signals_normalized.
No source tables are modified.
"""

import os
import sys
import json
import hashlib
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
from psycopg2.extras import RealDictCursor

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = int(os.environ.get('DB_PORT', '35577'))
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD') or os.environ.get('PGPASSWORD')


class SignalContract:
    __slots__ = ('analyst_id', 'ticker', 'as_of_date', 'generated_at', 'signal', 'score',
                 'confidence', 'rationale', 'inputs_hash', 'source_table', 'source_id', 'raw_inputs')

    def __init__(self, analyst_id, ticker, as_of_date, generated_at, signal, score,
                 confidence, rationale, inputs_hash, source_table, source_id, raw_inputs):
        self.analyst_id = analyst_id
        self.ticker = ticker.upper().strip()
        self.as_of_date = as_of_date
        self.generated_at = generated_at
        self.signal = signal
        self.score = score
        self.confidence = confidence
        self.rationale = rationale
        self.inputs_hash = inputs_hash
        self.source_table = source_table
        self.source_id = source_id
        self.raw_inputs = raw_inputs

    def to_tuple(self):
        return (self.analyst_id, self.ticker, self.as_of_date, self.generated_at,
                self.signal, self.score, self.confidence, self.rationale,
                self.inputs_hash, self.source_table, self.source_id,
                json.dumps(self.raw_inputs, default=str, sort_keys=True) if self.raw_inputs else None)


def connect_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def _hash_inputs(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _action_to_signal(action, action_map):
    a = (action or '').upper().strip()
    if a in action_map:
        return action_map[a]
    # Fallbacks
    if a in ('BUY', 'STRONG_BUY', 'OVERWEIGHT'):
        return 1
    if a in ('SELL', 'STRONG_SELL', 'UNDERWEIGHT'):
        return -1
    return 0


def _score_to_signal(score):
    if score is None:
        return 0
    if score >= 70:
        return 1
    if score <= 30:
        return -1
    return 0


def _score_confidence(score):
    if score is None:
        return 0.5
    return _clamp(abs(score - 50) / 50.0, 0.0, 1.0)


# ---------- Adapters ----------

def from_vox_grades(cursor, lookback_days=30):
    """Map latest vox_grades per ticker to SignalContract."""
    analyst_id = 'vox_grade_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, ticker, vox_grade, previous_grade, action,
               generated_at, data_available_at, catalysts
        FROM vox_grades
        WHERE (generated_at >= %s OR %s IS NULL)
          AND vox_grade IS NOT NULL
    """, (since, since))

    signals = []
    for row in cursor.fetchall():
        score = _score_to_signal(row['vox_grade'])
        if score == 0:
            continue
        generated = row['data_available_at'] or row['generated_at'] or datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        raw = {
            'vox_grade': row['vox_grade'],
            'previous_grade': row['previous_grade'],
            'action': row['action'],
            'catalysts': row['catalysts']
        }
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=row['ticker'],
            as_of_date=as_of,
            generated_at=generated,
            signal='bullish' if score > 0 else 'bearish',
            score=_clamp(score, -1, 1),
            confidence=_score_confidence(row['vox_grade']),
            rationale=f"vox_grade={row['vox_grade']} action={row['action']}",
            inputs_hash=_hash_inputs(raw),
            source_table='vox_grades',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


def from_unified_grades(cursor, lookback_days=30):
    analyst_id = 'unified_grade_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, ticker, unified_grade, action, vox_grade, sp500_grade, trade_grade,
               computed_at, data_available_at, contradiction
        FROM unified_grades
        WHERE (computed_at >= %s OR %s IS NULL)
          AND unified_grade IS NOT NULL
    """, (since, since))

    signals = []
    for row in cursor.fetchall():
        score = _score_to_signal(row['unified_grade'])
        if score == 0:
            continue
        generated = row['data_available_at'] or row['computed_at'] or datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        raw = {
            'unified_grade': row['unified_grade'],
            'action': row['action'],
            'vox_grade': row['vox_grade'],
            'sp500_grade': row['sp500_grade'],
            'trade_grade': row['trade_grade'],
            'contradiction': row['contradiction']
        }
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=row['ticker'],
            as_of_date=as_of,
            generated_at=generated,
            signal='bullish' if score > 0 else 'bearish',
            score=_clamp(score, -1, 1),
            confidence=_score_confidence(row['unified_grade']),
            rationale=f"unified_grade={row['unified_grade']} action={row['action']}",
            inputs_hash=_hash_inputs(raw),
            source_table='unified_grades',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


def from_technical_signals(cursor, lookback_days=30):
    analyst_id = 'technical_alpha_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, ticker, score, alpha_zoo_score, alpha_factor_count,
               mean_reversion_signals, computed_at, data_available_at
        FROM technical_signals
        WHERE (computed_at >= %s OR %s IS NULL)
          AND score IS NOT NULL
    """, (since, since))

    signals = []
    for row in cursor.fetchall():
        score = row['score'] or 0
        if score == 0:
            continue
        generated = row['data_available_at'] or row['computed_at'] or datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        raw = {
            'score': row['score'],
            'alpha_zoo_score': row['alpha_zoo_score'],
            'alpha_factor_count': row['alpha_factor_count'],
            'mean_reversion_signals': row['mean_reversion_signals']
        }
        s = _clamp((score - 50) / 50.0, -1, 1)
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=row['ticker'],
            as_of_date=as_of,
            generated_at=generated,
            signal='bullish' if s > 0 else 'bearish',
            score=s,
            confidence=_score_confidence(score),
            rationale=f"technical_score={score}",
            inputs_hash=_hash_inputs(raw),
            source_table='technical_signals',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


def from_macro_signals(cursor, lookback_days=30):
    analyst_id = 'macro_tilt_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, signal_name, signal_value, signal_direction, impact_sector,
               confidence, source, computed_at, data_available_at
        FROM macro_signals
        WHERE (computed_at >= %s OR %s IS NULL)
          AND signal_value IS NOT NULL
    """, (since, since))

    signals = []
    for row in cursor.fetchall():
        generated = row['data_available_at'] or row['computed_at'] or datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        direction = (row['signal_direction'] or '').lower()
        if direction in ('bullish', 'positive', 'up'):
            score = 1
        elif direction in ('bearish', 'negative', 'down'):
            score = -1
        else:
            val = row['signal_value'] or 0
            score = _clamp(val, -1, 1)
        if score == 0:
            continue
        raw = {
            'signal_name': row['signal_name'],
            'signal_value': row['signal_value'],
            'signal_direction': row['signal_direction'],
            'impact_sector': row['impact_sector'],
            'confidence': row['confidence'],
            'source': row['source']
        }
        # Macro signals apply to a sector, not a ticker; we mark ticker = sector or ALL for now.
        ticker = (row['impact_sector'] or 'ALL').upper().replace(' ', '_')
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=ticker,
            as_of_date=as_of,
            generated_at=generated,
            signal='bullish' if score > 0 else 'bearish',
            score=score,
            confidence=_clamp((row['confidence'] or 50) / 100.0, 0, 1),
            rationale=f"macro_signal={row['signal_name']} direction={row['signal_direction']}",
            inputs_hash=_hash_inputs(raw),
            source_table='macro_signals',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


def from_insider_trades(cursor, window_days=30, min_insiders=2, min_value=100_000):
    analyst_id = 'insider_cluster_v1'
    since = (datetime.utcnow() - timedelta(days=window_days)).date()
    cursor.execute("""
        SELECT ticker, transaction_type, total_value, transaction_date,
               insider_name, insider_title, is_officer, is_director, is_10pct_owner
        FROM insider_trades
        WHERE transaction_date >= %s
          AND transaction_type IN ('P', 'A', 'S')
    """, (since,))

    rows = cursor.fetchall()
    # Cluster by ticker and direction
    clusters = {}
    for r in rows:
        key = (r['ticker'].upper(), r['transaction_type'])
        clusters.setdefault(key, []).append(r)

    signals = []
    for (ticker, ttype), trades in clusters.items():
        buy_trades = [t for t in trades if ttype in ('P', 'A')]
        sell_trades = [t for t in trades if ttype == 'S']
        if ttype in ('P', 'A') and len(buy_trades) >= min_insiders:
            total_value = sum(t['total_value'] or 0 for t in buy_trades)
            if total_value >= min_value:
                score = 1
            else:
                score = 0.5
        elif ttype == 'S' and len(sell_trades) >= min_insiders:
            total_value = sum(t['total_value'] or 0 for t in sell_trades)
            score = -1 if total_value >= min_value else -0.5
        else:
            continue

        latest = max(t['transaction_date'] for t in trades)
        raw = {
            'window_days': window_days,
            'min_insiders': min_insiders,
            'min_value': min_value,
            'cluster_count': len(trades),
            'total_value': sum(t['total_value'] or 0 for t in trades),
            'officers': sum(1 for t in trades if t['is_officer']),
            'directors': sum(1 for t in trades if t['is_director'])
        }
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=ticker,
            as_of_date=latest,
            generated_at=datetime.utcnow(),
            signal='bullish' if score > 0 else 'bearish',
            score=_clamp(score, -1, 1),
            confidence=_clamp(len(trades) / (min_insiders * 2), 0.3, 1.0),
            rationale=f"{len(trades)} insider {ttype}-trades in {window_days}d, total_value=${raw['total_value']:,.0f}",
            inputs_hash=_hash_inputs(raw),
            source_table='insider_trades',
            source_id=None,
            raw_inputs=raw
        ))
    return signals


def from_trader_calls(cursor, lookback_days=30):
    analyst_id = 'trader_call_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, ticker, call_date, price_at_call, target_price, stop_price, call_type,
               trader_name, data_available_at
        FROM trader_calls
        WHERE (call_date >= %s OR %s IS NULL)
          AND call_type IS NOT NULL
    """, (since, since))

    signals = []
    for row in cursor.fetchall():
        generated = row['data_available_at'] or row['call_date']
        if generated is None:
            generated = datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        score = _action_to_signal(row['call_type'], {})
        if score == 0:
            continue
        raw = {
            'call_type': row['call_type'],
            'trader_name': row['trader_name'],
            'price_at_call': row['price_at_call'],
            'target_price': row['target_price'],
            'stop_price': row['stop_price']
        }
        confidence = 0.7
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=row['ticker'],
            as_of_date=as_of,
            generated_at=generated if isinstance(generated, datetime) else datetime.utcnow(),
            signal='bullish' if score > 0 else 'bearish',
            score=score,
            confidence=confidence,
            rationale=f"trader_call type={row['call_type']} trader={row['trader_name']}",
            inputs_hash=_hash_inputs(raw),
            source_table='trader_calls',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


def from_grade_alerts(cursor, lookback_days=30, min_delta=20):
    analyst_id = 'grade_alert_v1'
    since = (datetime.utcnow() - timedelta(days=lookback_days)).date()
    cursor.execute("""
        SELECT id, ticker, alert_type, old_grade, new_grade, old_action, new_action, triggered_at
        FROM grade_alerts
        WHERE (triggered_at >= %s OR %s IS NULL)
          AND ABS(COALESCE(old_grade, 0) - COALESCE(new_grade, 0)) >= %s
    """, (since, since, min_delta))

    signals = []
    for row in cursor.fetchall():
        generated = row['triggered_at'] or datetime.utcnow()
        as_of = generated.date() if isinstance(generated, datetime) else generated
        delta = (row['new_grade'] or 0) - (row['old_grade'] or 0)
        score = _clamp(delta / 100.0, -1, 1) if delta != 0 else 0
        if score == 0:
            continue
        raw = {
            'alert_type': row['alert_type'],
            'old_grade': row['old_grade'],
            'new_grade': row['new_grade'],
            'old_action': row['old_action'],
            'new_action': row['new_action']
        }
        signals.append(SignalContract(
            analyst_id=analyst_id,
            ticker=row['ticker'],
            as_of_date=as_of,
            generated_at=generated,
            signal='bullish' if score > 0 else 'bearish',
            score=score,
            confidence=_clamp(abs(delta) / 100.0, 0.1, 1.0),
            rationale=f"grade_alert {row['alert_type']}: {row['old_grade']} -> {row['new_grade']}",
            inputs_hash=_hash_inputs(raw),
            source_table='grade_alerts',
            source_id=row['id'],
            raw_inputs=raw
        ))
    return signals


# ---------- Run ----------

ADAPTERS = [
    from_vox_grades,
    from_unified_grades,
    from_technical_signals,
    from_macro_signals,
    from_insider_trades,
    from_trader_calls,
    from_grade_alerts,
]


def run_adapter(adapter_func, cursor):
    try:
        return adapter_func(cursor)
    except Exception as e:
        print(f"Adapter {adapter_func.__name__} failed: {e}")
        return []


def persist_signals(cursor, signals):
    if not signals:
        return 0
    inserted = 0
    # Use executemany for network efficiency
    rows = [sig.to_tuple() for sig in signals]
    try:
        cursor.executemany("""
            INSERT INTO signals_normalized
            (analyst_id, ticker, as_of_date, generated_at, signal, score, confidence,
             rationale, inputs_hash, source_table, source_id, raw_inputs)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (analyst_id, ticker, as_of_date, inputs_hash) DO NOTHING
        """, rows)
        inserted = cursor.rowcount if cursor.rowcount else 0
    except Exception as e:
        print(f"Bulk insert failed: {e}; falling back to one-by-one")
        for sig in signals:
            try:
                cursor.execute("""
                    INSERT INTO signals_normalized
                    (analyst_id, ticker, as_of_date, generated_at, signal, score, confidence,
                     rationale, inputs_hash, source_table, source_id, raw_inputs)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (analyst_id, ticker, as_of_date, inputs_hash) DO NOTHING
                """, sig.to_tuple())
                if cursor.rowcount > 0:
                    inserted += 1
            except Exception as e2:
                print(f"Insert failed for {sig.ticker}: {e2}")
    return inserted


def main(dry_run=False, lookback_days=30):
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    total = 0
    for func in ADAPTERS:
        signals = run_adapter(func, cursor)
        if dry_run:
            print(f"[DRY] {func.__name__}: {len(signals)} signals")
        else:
            inserted = persist_signals(cursor, signals)
            print(f"{func.__name__}: {inserted} new signals ({len(signals)} emitted)")
            total += inserted
    if not dry_run:
        conn.commit()
    print(f"Total signals normalized: {total}")
    cursor.close()
    conn.close()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Normalize VOX signals into SignalContract')
    parser.add_argument('--dry-run', action='store_true', help='Print counts without writing')
    parser.add_argument('--lookback-days', type=int, default=30, help='Days of source history to scan')
    args = parser.parse_args()
    main(dry_run=args.dry_run, lookback_days=args.lookback_days)
