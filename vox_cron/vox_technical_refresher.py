#!/usr/bin/env python3
"""VOX Technical Signals Refresher — real yfinance/price_history scores.

Refreshes technical_signals for portfolio + top unified_grades tickers.
Prevents stale tech scores from corrupting the unified grade blend.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: F401

import psycopg2

try:
    import yfinance as yf
except Exception as e:  # pragma: no cover
    yf = None
    print(f"WARNING: yfinance unavailable: {e}", file=sys.stderr)


def connect():
    host = os.environ.get("PGHOST") or os.environ.get("DB_HOST") or "acela.proxy.rlwy.net"
    port = int(os.environ.get("PGPORT") or os.environ.get("DB_PORT") or "35577")
    db = os.environ.get("PGDATABASE") or os.environ.get("DB_NAME") or "railway"
    user = os.environ.get("PGUSER") or os.environ.get("DB_USER") or "postgres"
    pw = os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD") or ""
    return psycopg2.connect(host=host, port=port, dbname=db, user=user, password=pw, connect_timeout=20)


def get_tickers(cur, limit: int = 80) -> List[str]:
    cur.execute(
        """
        WITH top_unified AS (
            SELECT ticker FROM unified_grades
            WHERE computed_at > NOW() - INTERVAL '7 days'
            ORDER BY unified_grade DESC NULLS LAST
            LIMIT %s
        ),
        candidates AS (
            SELECT ticker FROM positions WHERE shares > 0 AND ticker IS NOT NULL
            UNION
            SELECT ticker FROM broker_positions WHERE shares > 0 AND ticker IS NOT NULL
            UNION
            SELECT ticker FROM top_unified
        )
        SELECT DISTINCT ticker FROM candidates
        WHERE ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'
        ORDER BY ticker
        """,
        (limit,),
    )
    return [r[0] for r in cur.fetchall()]


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except Exception:
        return None


def score_from_history(closes: List[float]) -> Tuple[int, int, List[str]]:
    """Return (score 0-100, alpha_zoo_score, mean_reversion_signals)."""
    if len(closes) < 20:
        return 50, 50, ["INSUFFICIENT_DATA"]

    last = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma50 = sum(closes[-50:]) / min(50, len(closes)) if len(closes) >= 50 else ma20
    ret5 = (last / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
    ret20 = (last / closes[-21] - 1) * 100 if len(closes) >= 21 else 0

    # RSI-ish 14
    gains, losses = [], []
    window = closes[-15:]
    for i in range(1, len(window)):
        d = window[i] - window[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 1e-9
    rs = avg_gain / avg_loss if avg_loss else 100
    rsi = 100 - (100 / (1 + rs))

    score = 50
    signals: List[str] = []

    # Trend
    if last > ma20 > ma50:
        score += 15
        signals.append("UPTREND")
    elif last < ma20 < ma50:
        score -= 15
        signals.append("DOWNTREND")
    else:
        signals.append("SIDEWAYS")

    # Momentum
    if ret20 > 10:
        score += 12
        signals.append("STRONG_MOMENTUM")
    elif ret20 > 3:
        score += 6
    elif ret20 < -10:
        score -= 12
        signals.append("WEAK_MOMENTUM")
    elif ret20 < -3:
        score -= 6

    # RSI mean reversion
    if rsi < 30:
        score += 8
        signals.append("OVERSOLD")
    elif rsi > 70:
        score -= 8
        signals.append("OVERBOUGHT")
    else:
        signals.append("NEUTRAL_RSI")

    # Short-term bounce/fade
    if ret5 > 5 and ret20 < 0:
        score += 4
        signals.append("SHORT_BOUNCE")
    if ret5 < -5 and ret20 > 0:
        score -= 4
        signals.append("SHORT_FADE")

    score = int(max(0, min(100, round(score))))
    alpha = int(max(0, min(100, round(50 + ret20))))
    return score, alpha, signals


def fetch_closes(ticker: str) -> List[float]:
    if yf is None:
        return []
    try:
        hist = yf.Ticker(ticker).history(period="6mo", interval="1d", timeout=8)
        if hist is None or hist.empty:
            return []
        closes = [_safe_float(x) for x in hist["Close"].tolist()]
        return [c for c in closes if c is not None and c > 0]
    except Exception as e:
        print(f"  {ticker}: yfinance error: {e}")
        return []


def upsert_signal(cur, ticker: str, score: int, alpha: int, signals: List[str]) -> None:
    cur.execute(
        """
        INSERT INTO technical_signals
            (ticker, score, alpha_zoo_score, alpha_factor_count, mean_reversion_signals, computed_at, data_available_at)
        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (ticker) DO UPDATE SET
            score = EXCLUDED.score,
            alpha_zoo_score = EXCLUDED.alpha_zoo_score,
            alpha_factor_count = EXCLUDED.alpha_factor_count,
            mean_reversion_signals = EXCLUDED.mean_reversion_signals,
            computed_at = NOW(),
            data_available_at = NOW()
        """,
        (ticker, score, alpha, len(signals), signals),
    )


def main() -> int:
    print(f"VOX Technical Refresher — {datetime.now(timezone.utc).isoformat()}")
    conn = connect()
    cur = conn.cursor()

    # Ensure unique ticker constraint for ON CONFLICT
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'technical_signals_ticker_key'
            ) THEN
                -- dedupe first
                DELETE FROM technical_signals a
                USING technical_signals b
                WHERE a.ctid < b.ctid AND a.ticker = b.ticker;
                BEGIN
                    ALTER TABLE technical_signals ADD CONSTRAINT technical_signals_ticker_key UNIQUE (ticker);
                EXCEPTION WHEN others THEN
                    NULL;
                END;
            END IF;
        END $$;
        """
    )
    conn.commit()

    tickers = get_tickers(cur, limit=80)
    print(f"Refreshing technical signals for {len(tickers)} tickers")

    ok = 0
    failed = 0
    for i, ticker in enumerate(tickers, 1):
        closes = fetch_closes(ticker)
        if len(closes) < 20:
            failed += 1
            continue
        score, alpha, signals = score_from_history(closes)
        try:
            upsert_signal(cur, ticker, score, alpha, signals)
            ok += 1
            if i % 10 == 0:
                conn.commit()
                print(f"  progress {i}/{len(tickers)} (ok={ok})")
        except Exception as e:
            conn.rollback()
            failed += 1
            print(f"  {ticker}: upsert error: {e}")

    conn.commit()
    cur.execute("SELECT COUNT(*), MAX(computed_at) FROM technical_signals")
    count, latest = cur.fetchone()
    conn.close()
    print(f"Done. Updated {ok}, failed {failed}. Table rows={count}, latest={latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
