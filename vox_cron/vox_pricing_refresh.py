#!/usr/bin/env python3
"""
VOX Pricing — SINGLE OWNER (Phase 2)

Canonical writer for:
  - positions.live_price / price_asof / prev_close / day_chg_pct / price_source
  - price_history UPSERT
  - price_feed_log
  - optional vox_grades.current_price (mode=grades)

Order of live marks:
  1) Alpaca snapshots (US equities) when keys present
  2) Yahoo chart (history + global/crypto/MX aliases)
  3) Dual-check on |day%| >= 8% (Alpaca vs Yahoo)

Adapters:
  - eToro: separate job (broker-specific), does not own book marks for non-eToro
  - hybrid_price_feed*: thin wrappers or paused — do not write competing truth

Modes:
  held | eod | universe | grades | ticker SYM
"""
from __future__ import annotations

import os
import sys
import time
import urllib.parse
import urllib.request
import json
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

from vox_price_quote import yahoo_chart

BIG_MOVE_PCT = 8.0

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

CRYPTO = set(YAHOO_ALIAS.keys()) - {"NAFTRAC"}

# Book tickers whose Yahoo feed is MXN-quoted. Marks stored in USD for AUM consistency.
MXN_NATIVE = {"NAFTRAC"}

# Fallback only if FX fetch fails (≈1/18.2)
_MXN_USD_FALLBACK = 0.055
_fx_cache: Dict[str, float] = {}


def mxn_to_usd_rate() -> float:
    """Live MXN→USD. Prefer MXNUSD=X, else invert USDMXN=X."""
    if "mxn_usd" in _fx_cache:
        return _fx_cache["mxn_usd"]
    rate = None
    try:
        meta, bars = yahoo_chart("MXNUSD=X", range_="5d", interval="1d")
        px = meta.get("regularMarketPrice")
        if px is None and bars:
            px = bars[-1]["close"]
        if px and float(px) > 0.01:
            rate = float(px)
    except Exception:
        rate = None
    if rate is None:
        try:
            meta, bars = yahoo_chart("USDMXN=X", range_="5d", interval="1d")
            px = meta.get("regularMarketPrice")
            if px is None and bars:
                px = bars[-1]["close"]
            if px and float(px) > 1:
                rate = 1.0 / float(px)
        except Exception:
            rate = None
    if rate is None or rate <= 0:
        rate = _MXN_USD_FALLBACK
    _fx_cache["mxn_usd"] = rate
    return rate


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
          ADD COLUMN IF NOT EXISTS day_chg_pct NUMERIC(10,4),
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
    return [
        r["t"]
        for r in cur.fetchall()
        if r["t"] and r["t"] not in ("MIRROR_TOTAL", "CASH") and " " not in r["t"]
    ]


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


def grades_stale_tickers(cur, limit: int = 200) -> List[str]:
    cur.execute(
        """
        SELECT DISTINCT ON (ticker) ticker, current_price, generated_at
        FROM vox_grades
        ORDER BY ticker, generated_at DESC
        """
    )
    out = []
    cutoff = datetime.now() - timedelta(days=7)
    for r in cur.fetchall():
        t = (r["ticker"] or "").upper()
        if not t or " " in t:
            continue
        px = r.get("current_price")
        gen = r.get("generated_at")
        if px is None or float(px or 0) <= 0 or gen is None or gen < cutoff:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def alpaca_keys() -> Tuple[str, str]:
    return (
        os.environ.get("ALPACA_API_KEY") or "",
        os.environ.get("ALPACA_SECRET_KEY") or "",
    )


def is_us_equity_symbol(t: str) -> bool:
    t = (t or "").upper().strip()
    if not t or t in CRYPTO or t in YAHOO_ALIAS:
        return False
    if " " in t or "-" in t or "/" in t or t.startswith("$"):
        return False
    return t.isalnum()


def fetch_alpaca_batch(tickers: List[str]) -> Dict[str, float]:
    """Live US marks from Alpaca data API. Returns {TICKER: price}."""
    key, sec = alpaca_keys()
    if not key or not sec:
        return {}
    eligible = [t.upper().strip() for t in tickers if is_us_equity_symbol(t)]
    if not eligible:
        return {}
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": sec,
        "Accept": "application/json",
    }
    prices: Dict[str, float] = {}
    for i in range(0, len(eligible), 80):
        batch = eligible[i : i + 80]
        symbols = ",".join(urllib.parse.quote(s, safe="") for s in batch)
        url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={symbols}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode())
            # API may return {snapshots: {...}} or flat dict
            snaps = data.get("snapshots") if isinstance(data, dict) and "snapshots" in data else data
            if not isinstance(snaps, dict):
                continue
            for symbol, snapshot in snaps.items():
                if not isinstance(snapshot, dict):
                    continue
                try:
                    trade = snapshot.get("latestTrade") or {}
                    price = float(trade.get("p") or 0)
                    if price <= 0:
                        quote = snapshot.get("latestQuote") or {}
                        bp = float(quote.get("bp") or 0)
                        ap = float(quote.get("ap") or 0)
                        if bp > 0 and ap > 0:
                            price = (bp + ap) / 2
                    if price > 0:
                        prices[symbol.upper()] = price
                except Exception:
                    continue
        except Exception as e:
            print(f"  ⚠️ Alpaca batch error: {e}")
        time.sleep(0.15)
    print(f"  Alpaca live marks: {len(prices)}/{len(eligible)} US symbols")
    return prices


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


def refresh_ticker(
    cur,
    ticker: str,
    history_days: int = 45,
    alpaca_cache: Optional[Dict[str, float]] = None,
    update_positions: bool = True,
    update_grades: bool = False,
) -> Optional[dict]:
    t = (ticker or "").strip().upper()
    if not t or " " in t or t in ("MIRROR_TOTAL", "CASH"):
        return {"ticker": ticker, "error": "skip_invalid_symbol"}
    ysym = YAHOO_ALIAS.get(t, t)
    alpaca_cache = alpaca_cache or {}
    try:
        range_ = "2mo" if history_days >= 40 else "1mo"
        meta, bars = yahoo_chart(ysym, range_=range_, interval="1d")
        if not bars:
            # last resort: alpaca-only live without history
            if t in alpaca_cache:
                px = float(alpaca_cache[t])
                asof = datetime.now(timezone.utc)
                if update_positions:
                    fx = mxn_to_usd_rate()
                    cur.execute(
                        """
                        UPDATE positions
                        SET live_price=%s, live_value=shares*%s,
                            live_value_usd=CASE WHEN currency='MXN' THEN shares*%s*%s ELSE shares*%s END,
                            price_source='alpaca_only', price_asof=%s, updated_at=NOW()
                        WHERE UPPER(ticker)=%s
                        """,
                        (px, px, px, fx, px, asof, t),
                    )
                return {"ticker": t, "price": px, "source": "alpaca_only", "day_chg_pct": None}
            return None

        upsert_history(cur, t, bars[-history_days:], "yahoo_chart")

        last_bar = float(bars[-1]["close"])
        bar_prev = float(bars[-2]["close"]) if len(bars) >= 2 else None
        meta_prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        prev = bar_prev
        if meta_prev is not None and bar_prev is not None:
            mp = float(meta_prev)
            if abs(mp - bar_prev) / max(bar_prev, 1e-9) <= 0.03:
                prev = mp
        elif meta_prev is not None:
            prev = float(meta_prev)

        source = "yahoo_chart"
        notes = ""

        y_live = meta.get("regularMarketPrice") or last_bar
        y_live = float(y_live)
        # Trust daily bar over meta when they diverge materially (NAFTRAC.MX meta
        # has returned junk mid-price while bars stay on the real MXN close).
        diverge_lim = 0.08 if (t in MXN_NATIVE or (ysym or "").endswith(".MX")) else 0.5
        if last_bar > 0 and abs(y_live - last_bar) / last_bar > diverge_lim:
            y_live = last_bar
            notes = (notes + f" prefer_bar meta={meta.get('regularMarketPrice')}").strip()

        # Prefer bar-to-bar prev for MXN-native (meta previousClose often USD-mixed junk)
        if t in MXN_NATIVE or (ysym or "").endswith(".MX"):
            if bar_prev is not None:
                prev = bar_prev

        px = y_live

        # Prefer Alpaca for US live mark when available
        if t in alpaca_cache and alpaca_cache[t] > 0:
            apx = float(alpaca_cache[t])
            if y_live > 0 and abs(apx - y_live) / y_live > 0.03:
                notes = f"prefer_alpaca yahoo={y_live:.2f}"
                px = apx
                source = "alpaca"
            else:
                px = apx
                source = "alpaca+yahoo"
                notes = "alpaca_primary"

        chg = 100.0 * (px - prev) / prev if prev else None

        # Dual-check big moves if only yahoo so far
        if (
            chg is not None
            and abs(chg) >= BIG_MOVE_PCT
            and source.startswith("yahoo")
            and t in alpaca_cache
        ):
            apx = float(alpaca_cache[t])
            if y_live > 0 and abs(apx - y_live) / y_live > 0.03:
                notes = f"dual_disagree yahoo={y_live:.2f} alpaca={apx:.2f}"
                px = apx
                source = "alpaca_dual"
                chg = 100.0 * (px - prev) / prev if prev else chg
            else:
                notes = (notes + " dual_ok").strip()

        if ysym != t:
            notes = (notes + f" alias={ysym}").strip()

        # MXN-native (e.g. NAFTRAC.MX): day% from native bars; store USD marks for book AUM.
        # Prior bug: hardcoded *0.055 on live_value_usd while live_price sometimes left in MXN
        # and prev_close mixed units → fake −30% day moves and junk Ops shocks.
        native_px = px
        native_prev = prev
        currency_hint = None
        if t in MXN_NATIVE or (ysym or "").endswith(".MX"):
            fx = mxn_to_usd_rate()
            # day% must use native MXN only
            chg = (
                100.0 * (native_px - native_prev) / native_prev
                if native_prev
                else chg
            )
            px = native_px * fx
            prev = native_prev * fx if native_prev is not None else None
            currency_hint = "MXN"
            notes = (notes + f" mxn_native fx={fx:.6f} native={native_px:.4f}").strip()
            source = f"{source}+mxn_usd"

        asof = datetime.now(timezone.utc)
        if update_positions:
            if currency_hint == "MXN":
                cur.execute(
                    """
                    UPDATE positions
                    SET live_price = %s,
                        live_value = shares * %s,
                        live_value_usd = shares * %s,
                        currency = COALESCE(NULLIF(currency,''), 'MXN'),
                        price_source = %s,
                        price_asof = %s,
                        prev_close = %s,
                        day_chg_pct = %s,
                        updated_at = NOW()
                    WHERE UPPER(ticker) = %s
                    """,
                    (px, px, px, source[:40], asof, prev, chg, t),
                )
            else:
                cur.execute(
                    """
                    UPDATE positions
                    SET live_price = %s,
                        live_value = shares * %s,
                        live_value_usd = CASE
                          WHEN currency = 'MXN' THEN shares * %s * %s
                          ELSE shares * %s
                        END,
                        price_source = %s,
                        price_asof = %s,
                        prev_close = %s,
                        day_chg_pct = %s,
                        updated_at = NOW()
                    WHERE UPPER(ticker) = %s
                    """,
                    (
                        px,
                        px,
                        px,
                        mxn_to_usd_rate(),
                        px,
                        source[:40],
                        asof,
                        prev,
                        chg,
                        t,
                    ),
                )
        if update_grades:
            cur.execute(
                """
                UPDATE vox_grades SET current_price = %s
                WHERE ticker = %s
                  AND id IN (
                    SELECT id FROM vox_grades WHERE ticker = %s
                    ORDER BY generated_at DESC LIMIT 1
                  )
                """,
                (px, t, t),
            )

        cur.execute(
            """
            INSERT INTO price_feed_log (ticker, price, prev_close, day_chg_pct, source, notes)
            VALUES (%s,%s,%s,%s,%s,%s)
            """,
            (t, px, prev, chg, source, notes or "pricing_owner"),
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


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "held"
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ensure_schema(cur)
    conn.commit()

    update_positions = True
    update_grades = False

    if mode == "held":
        tickers = held_tickers(cur)
    elif mode == "universe":
        tickers = universe_tickers(cur, 250)
    elif mode == "eod":
        tickers = universe_tickers(cur, 400)
    elif mode == "grades":
        tickers = grades_stale_tickers(cur, 200)
        update_positions = False
        update_grades = True
    elif mode == "ticker" and len(sys.argv) > 2:
        tickers = [sys.argv[2].upper()]
    else:
        tickers = held_tickers(cur)

    print(f"💰 VOX Pricing OWNER — mode={mode} tickers={len(tickers)}")
    alpaca_cache = fetch_alpaca_batch(tickers)

    ok, err, big = 0, 0, []
    for i, t in enumerate(tickers):
        r = refresh_ticker(
            cur,
            t,
            alpaca_cache=alpaca_cache,
            update_positions=update_positions,
            update_grades=update_grades,
        )
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
        time.sleep(0.10)
    conn.commit()

    print(f"Done ok={ok} err={err} big_moves={len(big)} alpaca_cache={len(alpaca_cache)}")
    if big:
        print("Big moves:")
        for r in sorted(big, key=lambda x: abs(x.get("day_chg_pct") or 0), reverse=True)[:15]:
            print(f"  {r['ticker']:6} {r['day_chg_pct']:+6.1f}%  ${r['price']:.2f}  {r['source']}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
