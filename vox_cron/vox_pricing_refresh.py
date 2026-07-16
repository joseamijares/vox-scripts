#!/usr/bin/env python3
"""
VOX Pricing Architecture v1
- Ensures positions.price_asof / prev_close / day_chg_pct columns
- Refreshes live prices via Yahoo chart (+ Alpaca when available)
- UPSERTs recent price_history
- Dual-source check when |day_chg| >= 8%
- Writes price_feed_log audit trail
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

from vox_price_quote import live_quote, yahoo_chart

BIG_MOVE_PCT = 8.0
STALE_MINUTES = 30

# Yahoo chart symbols for common non-US / crypto holdings
YAHOO_ALIAS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
    "DOGE": "DOGE-USD",
    "ADA": "ADA-USD",
    "BNB": "BNB-USD",
    "TRX": "TRX-USD",
    "HBAR": "HBAR-USD",
    "AVAX": "AVAX-USD",
    "DOT": "DOT-USD",
    "BONK": "BONK-USD",
    "PENGU": "PENGU-USD",
    "VANA": "VANA-USD",
    "MORPHO": "MORPHO-USD",
    "NAFTRAC": "NAFTRAC.MX",
    "KAITO": "KAITO-USD",
    "NIGHT": "NIGHT-USD",
    "NXPC": "NXPC-USD",
    "VAULTA": "VAULTA-USD",
}


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def ensure_schema(cur):
    cur.execute(
        """
        ALTER TABLE positions
          ADD COLUMN IF NOT EXISTS price_asof TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS prev_close NUMERIC(14,6),
          ADD COLUMN IF NOT EXISTS day_chg_pct NUMERIC(10,4);

        ALTER TABLE positions
          ADD COLUMN IF NOT EXISTS price_source VARCHAR(40);

        CREATE TABLE IF NOT EXISTS price_feed_log (
          id SERIAL PRIMARY KEY,
          ticker VARCHAR(20) NOT NULL,
          price NUMERIC(14,6),
          prev_close NUMERIC(14,6),
          day_chg_pct NUMERIC(10,4),
          source VARCHAR(40),
          notes TEXT,
          logged_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_price_feed_log_ticker_time
          ON price_feed_log (ticker, logged_at DESC);
        """
    )


def held_tickers(cur) -> List[str]:
    cur.execute(
        """
        SELECT DISTINCT UPPER(ticker) AS t
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        """
    )
    return [r["t"] for r in cur.fetchall() if r["t"] and r["t"] not in ("MIRROR_TOTAL", "CASH")]


def universe_tickers(cur, limit: int = 200) -> List[str]:
    cur.execute(
        """
        SELECT DISTINCT UPPER(ticker) AS t FROM (
          SELECT ticker FROM positions
          WHERE COALESCE(live_value_usd, live_value, 0) > 0
          UNION
          SELECT ticker FROM vox_grades
          WHERE generated_at > NOW() - INTERVAL '14 days'
        ) s
        WHERE ticker IS NOT NULL
          AND ticker !~ ' '
          AND ticker NOT IN ('MIRROR_TOTAL', 'CASH')
        ORDER BY t
        LIMIT %s
        """,
        (limit,),
    )
    return [r["t"] for r in cur.fetchall()]


def upsert_history(cur, ticker: str, bars: list, source: str = "yahoo_chart") -> int:
    n = 0
    for b in bars:
        cur.execute(
            """
            INSERT INTO price_history
              (ticker, date, open, high, low, close, volume, adj_close, source, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (ticker, date) DO UPDATE SET
              open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
              close=EXCLUDED.close, volume=EXCLUDED.volume,
              adj_close=EXCLUDED.adj_close, source=EXCLUDED.source
            """,
            (
                ticker,
                b["date"],
                b.get("open"),
                b.get("high"),
                b.get("low"),
                b["close"],
                b.get("volume"),
                b.get("adj_close") or b["close"],
                source,
            ),
        )
        n += 1
    return n


def dual_check(ticker: str, price: float, day_chg: Optional[float]) -> Tuple[float, str, str]:
    """If big move, try Alpaca snapshot; return (price, source, notes)."""
    notes = ""
    source = "yahoo_chart"
    if day_chg is None or abs(day_chg) < BIG_MOVE_PCT:
        return price, source, notes

    # try alpaca
    try:
        from vox_hybrid_price_feed import fetch_alpaca_prices

        ap = fetch_alpaca_prices([ticker])
        if ticker in ap and ap[ticker] > 0:
            apx = float(ap[ticker])
            # if within 3% of yahoo, keep yahoo; else note disagreement
            if price > 0 and abs(apx - price) / price > 0.03:
                notes = f"dual_disagree yahoo={price:.2f} alpaca={apx:.2f}"
                # prefer alpaca for US if disagreement large on crash days
                price = apx
                source = "alpaca_dual"
            else:
                notes = f"dual_ok alpaca={apx:.2f}"
                source = "yahoo_chart+alpaca"
    except Exception as e:
        notes = f"dual_skip {e}"
    return price, source, notes


def refresh_ticker(cur, ticker: str, history_days: int = 45) -> Optional[dict]:
    t = (ticker or "").strip().upper()
    if not t or " " in t or t in ("MIRROR_TOTAL", "CASH"):
        return {"ticker": ticker, "error": "skip_invalid_symbol"}
    ysym = YAHOO_ALIAS.get(t, t)
    try:
        range_ = "2mo" if history_days >= 40 else "1mo"
        meta, bars = yahoo_chart(ysym, range_=range_, interval="1d")
        if not bars:
            return None
        # store history under book ticker (not yahoo alias)
        for b in bars:
            b["ticker"] = t
        upsert_history(cur, t, bars[-history_days:], "yahoo_chart")

        px = meta.get("regularMarketPrice") or bars[-1]["close"]
        # Prefer last completed bar as anchor for day% — meta previousClose is often wrong
        last_bar = float(bars[-1]["close"])
        bar_prev = float(bars[-2]["close"]) if len(bars) >= 2 else None
        meta_prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        prev = bar_prev
        if meta_prev is not None and bar_prev is not None:
            mp = float(meta_prev)
            # if meta prev is close to bar_prev, ok; else trust bars
            if abs(mp - bar_prev) / max(bar_prev, 1e-9) <= 0.03:
                prev = mp
        elif meta_prev is not None and bar_prev is None:
            prev = float(meta_prev)

        px = float(px)
        # if live is wildly off last bar (bad print), clamp to last bar for book marks
        if last_bar > 0 and abs(px - last_bar) / last_bar > 0.5:
            px = last_bar
        chg = 100.0 * (px - prev) / prev if prev else None

        px, source, notes = dual_check(t, px, chg)
        if prev:
            chg = 100.0 * (px - prev) / prev
        if ysym != t:
            notes = (notes + f" alias={ysym}").strip()

        asof = datetime.now(timezone.utc)
        cur.execute(
            """
            UPDATE positions
            SET live_price = %s,
                live_value = shares * %s,
                live_value_usd = CASE
                  WHEN currency = 'MXN' THEN shares * %s * 0.055
                  ELSE shares * %s
                END,
                price_source = %s,
                price_asof = %s,
                prev_close = %s,
                day_chg_pct = %s,
                updated_at = NOW()
            WHERE UPPER(ticker) = %s
            """,
            (px, px, px, px, source, asof, prev, chg, t),
        )
        cur.execute(
            """
            INSERT INTO price_feed_log (ticker, price, prev_close, day_chg_pct, source, notes)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (t, px, prev, chg, source, notes or "refresh"),
        )
        return {
            "ticker": t,
            "price": px,
            "prev_close": prev,
            "day_chg_pct": chg,
            "source": source,
            "notes": notes,
        }
    except Exception as e:
        cur.execute(
            """
            INSERT INTO price_feed_log (ticker, price, source, notes)
            VALUES (%s, NULL, 'error', %s)
            """,
            (t, str(e)[:200]),
        )
        return {"ticker": t, "error": str(e)[:160]}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "held"
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ensure_schema(cur)
    conn.commit()

    if mode == "held":
        tickers = held_tickers(cur)
    elif mode == "universe":
        tickers = universe_tickers(cur, 250)
    elif mode == "eod":
        tickers = universe_tickers(cur, 400)
    else:
        tickers = held_tickers(cur)

    print(f"💰 VOX Pricing Refresh — mode={mode} tickers={len(tickers)}")
    ok, err, big = 0, 0, []
    for i, t in enumerate(tickers):
        r = refresh_ticker(cur, t)
        if r and "error" not in r:
            ok += 1
            if r.get("day_chg_pct") is not None and abs(r["day_chg_pct"]) >= BIG_MOVE_PCT:
                big.append(r)
                print(
                    f"  ⚠️ {t} {r['day_chg_pct']:+.1f}% @ {r['price']:.2f} ({r['source']}) {r.get('notes') or ''}"
                )
        else:
            err += 1
            print(f"  ❌ {t} {r}")
        if i % 20 == 19:
            conn.commit()
        time.sleep(0.12)
    conn.commit()

    print(f"Done ok={ok} err={err} big_moves={len(big)}")
    if big:
        print("Big moves:")
        for r in sorted(big, key=lambda x: abs(x.get("day_chg_pct") or 0), reverse=True)[:15]:
            print(f"  {r['ticker']:6} {r['day_chg_pct']:+6.1f}%  ${r['price']:.2f}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
