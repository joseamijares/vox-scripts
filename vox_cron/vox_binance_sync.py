#!/usr/bin/env python3
"""Sync Binance balances → broker_positions (Railway Postgres).

Spot + Simple Earn (flex/locked) when permitted by API key.
Does NOT rewrite multi-broker consolidated positions.shares.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
import time
import urllib.parse
import urllib.request
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2

BROKER = "Binance"
MIN_USD = 1.0
BASE = "https://api.binance.com"


def load_env() -> None:
    for p in (
        Path.home() / ".hermes" / ".env.generated",
        Path.home() / ".hermes" / ".env",
    ):
        if not p.exists():
            continue
        for line in p.read_text(errors="replace").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if not k or not v or "Chrome" in v or v.startswith("***"):
                continue
            if k.startswith("BINANCE_") or k in ("DB_PASSWORD", "PGPASSWORD") or k not in os.environ:
                os.environ[k] = v


def connect():
    pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=pwd,
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        connect_timeout=20,
    )


def signed_get(path: str, key: str, secret: str, params: dict | None = None) -> dict:
    params = dict(params or {})
    params["timestamp"] = int(time.time() * 1000)
    query = urllib.parse.urlencode(params)
    sig = hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE}{path}?{query}&signature={sig}"
    req = urllib.request.Request(url, headers={"X-MBX-APIKEY": key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def public_get(path: str) -> dict | list:
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "VOX-BinanceSync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def resolve_price(asset: str, prices: Dict[str, float]) -> float:
    a = asset.upper()
    if a.startswith("LD") and len(a) > 2:
        a = a[2:]
    stables = {
        "USDT", "FDUSD", "BUSD", "USDC", "TUSD", "DAI", "USD1", "USDS",
        "USDE", "EURI", "AEUR", "RLUSD", "XUSD", "BFUSD", "USD",
    }
    if a in stables:
        return 1.0
    if a in ("BETH", "WBETH"):
        return prices.get("ETH", 0.0)
    if a == "WBTC":
        return prices.get("BTC", 0.0)
    if a.startswith("1000") and len(a) > 4:
        base = a[4:]
        return prices.get(base, 0.0) / 1000.0
    return float(prices.get(a, 0.0) or 0.0)


def fetch_portfolio(key: str, secret: str) -> Tuple[list, float]:
    try:
        from binance.client import Client
    except ImportError:
        print("❌ python-binance not installed")
        raise

    client = Client(key, secret)
    prices: Dict[str, float] = {}
    for t in client.get_symbol_ticker():
        s = t["symbol"]
        if s.endswith("USDT"):
            prices[s[:-4]] = float(t["price"])

    spot: Dict[str, float] = {}
    account = client.get_account()
    for b in account.get("balances", []):
        total = float(b.get("free") or 0) + float(b.get("locked") or 0)
        if total > 0:
            spot[b["asset"]] = total

    flex: Dict[str, float] = {}
    locked: Dict[str, float] = {}
    try:
        resp = signed_get("/sapi/v1/simple-earn/flexible/position", key, secret, {"size": 100})
        for row in resp.get("rows", []) or []:
            asset = row.get("asset") or ""
            amt = float(row.get("totalAmount") or 0)
            if asset and amt > 0:
                flex[asset] = flex.get(asset, 0.0) + amt
    except Exception as e:
        print(f"  ⚠️ flex earn: {e}")

    try:
        resp = signed_get("/sapi/v1/simple-earn/locked/position", key, secret, {"size": 100})
        for row in resp.get("rows", []) or []:
            asset = row.get("asset") or ""
            amt = 0.0
            for field in ("amount", "totalAmount", "principal"):
                if row.get(field) is not None:
                    try:
                        amt = float(row[field])
                        break
                    except Exception:
                        pass
            if asset and amt > 0:
                locked[asset] = locked.get(asset, 0.0) + amt
    except Exception as e:
        print(f"  ⚠️ locked earn: {e}")

    merged: Dict[str, float] = {}

    def add(asset: str, qty: float) -> None:
        if qty <= 0:
            return
        a = asset.upper()
        if a.startswith("LD") and len(a) > 2:
            a = a[2:]
        merged[a] = merged.get(a, 0.0) + qty

    for a, q in spot.items():
        add(a, q)
    for a, q in flex.items():
        add(a, q)
    for a, q in locked.items():
        add(a, q)

    rows = []
    total_usd = 0.0
    for asset, qty in merged.items():
        px = resolve_price(asset, prices)
        val = qty * px
        total_usd += val
        if val >= MIN_USD:
            rows.append({"ticker": asset, "shares": qty, "price": px, "value": val})
    rows.sort(key=lambda x: x["value"], reverse=True)
    return rows, total_usd


def main() -> int:
    load_env()
    print("🔄 Binance → broker_positions")
    key = os.environ.get("BINANCE_API_KEY") or ""
    secret = os.environ.get("BINANCE_API_SECRET") or os.environ.get("BINANCE_SECRET") or ""
    if not key or not secret:
        print("❌ Missing BINANCE_API_KEY / BINANCE_API_SECRET")
        return 1

    try:
        rows, total_usd = fetch_portfolio(key, secret)
    except Exception as e:
        print(f"❌ Binance fetch failed: {e}")
        return 1

    print(f"Assets >${MIN_USD}: {len(rows)} · gross ${total_usd:,.2f}")
    conn = connect()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    live: list[str] = []
    imported = 0
    book_usd = 0.0

    for b in rows:
        t = b["ticker"]
        cur.execute(
            "SELECT grade, council, sector FROM positions WHERE UPPER(ticker)=%s LIMIT 1",
            (t,),
        )
        row = cur.fetchone()
        grade, council, sector = row if row else (None, None, "Crypto")
        cur.execute(
            """
            INSERT INTO broker_positions
              (broker, ticker, shares, live_price, live_value, currency, live_value_usd,
               grade, council, sector, source, last_sync_at, price_source, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (broker, ticker) DO UPDATE SET
              shares=EXCLUDED.shares,
              live_price=EXCLUDED.live_price,
              live_value=EXCLUDED.live_value,
              live_value_usd=EXCLUDED.live_value_usd,
              grade=COALESCE(EXCLUDED.grade, broker_positions.grade),
              council=COALESCE(EXCLUDED.council, broker_positions.council),
              sector=COALESCE(EXCLUDED.sector, broker_positions.sector),
              source=EXCLUDED.source,
              last_sync_at=EXCLUDED.last_sync_at,
              price_source=EXCLUDED.price_source,
              updated_at=NOW()
            """,
            (
                BROKER,
                t,
                b["shares"],
                b["price"],
                b["value"],
                "USD",
                b["value"],
                grade,
                council,
                sector or "Crypto",
                "api",
                now,
                "binance",
            ),
        )
        imported += 1
        book_usd += b["value"]
        live.append(t)
        print(f"  ✅ {t}: {b['shares']:.6f} @ ${b['price']:,.4f} = ${b['value']:,.2f}")

    if live:
        cur.execute(
            """
            UPDATE broker_positions
            SET shares=0, live_value=0, live_value_usd=0, updated_at=NOW(),
                source='api_stale_zero', last_sync_at=%s
            WHERE broker=%s AND ticker <> ALL(%s) AND COALESCE(shares,0)>0
            """,
            (now, BROKER, live),
        )

    try:
        cur.execute(
            """
            INSERT INTO broker_accounts (broker, account_type, has_api, currency_default, is_active, last_sync_at)
            VALUES (%s, 'crypto', TRUE, 'USD', TRUE, NOW())
            ON CONFLICT DO NOTHING
            """,
            (BROKER,),
        )
        cur.execute(
            "UPDATE broker_accounts SET last_sync_at=NOW(), updated_at=NOW() WHERE broker=%s",
            (BROKER,),
        )
    except Exception:
        pass

    conn.commit()
    conn.close()
    print(f"Binance done · n={imported} · ${book_usd:,.2f}")
    return 0 if imported > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
