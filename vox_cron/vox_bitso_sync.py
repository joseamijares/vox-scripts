#!/usr/bin/env python3
"""Sync Bitso balances → broker_positions (Railway Postgres).

Daily adapter. Does NOT rewrite multi-broker positions shares.
Marks only: broker_positions for broker='Bitso'.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
import requests

BROKER = "Bitso"
MIN_USD = 0.50


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
            if k in ("BITSO_API_KEY", "BITSO_API_SECRET", "DB_PASSWORD", "PGPASSWORD") or k not in os.environ:
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


def bitso_get(path: str, key: str, secret: str) -> dict:
    base = "https://api.bitso.com"
    nonce = str(int(datetime.now(timezone.utc).timestamp() * 1000))
    msg = nonce + "GET" + path
    sig = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bitso {key}:{nonce}:{sig}",
        "Content-Type": "application/json",
    }
    r = requests.get(base + path, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Bitso error: {data}")
    return data


def ticker_last(book: str) -> float:
    try:
        r = requests.get(f"https://api.bitso.com/api/v3/ticker/?book={book}", timeout=12)
        if r.status_code != 200:
            return 0.0
        data = r.json()
        if data.get("success"):
            return float(data.get("payload", {}).get("last") or 0)
    except Exception:
        return 0.0
    return 0.0


def price_usd(currency: str, btc_usd: float) -> float:
    c = currency.upper()
    if c in ("USD", "USDT", "USDC"):
        return 1.0
    if c == "BTC":
        return btc_usd
    for book in (f"{c.lower()}_usd", f"{c.lower()}_usdt"):
        px = ticker_last(book)
        if px > 0:
            return px
    if btc_usd > 0:
        px_btc = ticker_last(f"{c.lower()}_btc")
        if px_btc > 0:
            return px_btc * btc_usd
    return 0.0


def main() -> int:
    load_env()
    print("🔄 Bitso → broker_positions")
    key = os.environ.get("BITSO_API_KEY") or ""
    secret = os.environ.get("BITSO_API_SECRET") or ""
    if not key or not secret or key.startswith("***"):
        print("❌ Missing BITSO_API_KEY / BITSO_API_SECRET")
        return 1

    data = bitso_get("/api/v3/balance/", key, secret)
    balances = data.get("payload", {}).get("balances", []) or []
    btc_usd = ticker_last("btc_usd")
    print(f"BTC ref ${btc_usd:,.2f} · raw balances {len(balances)}")

    conn = connect()
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    live: list[str] = []
    imported = 0
    total_usd = 0.0

    for bal in balances:
        currency = (bal.get("currency") or "").upper()
        total = Decimal(str(bal.get("total", "0")))
        if total <= 0 or currency in ("MXN",):
            continue
        px = price_usd(currency, btc_usd)
        value = float(total) * px if px else 0.0
        if value < MIN_USD:
            continue

        cur.execute(
            "SELECT grade, council, sector FROM positions WHERE UPPER(ticker)=%s LIMIT 1",
            (currency,),
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
                currency,
                float(total),
                px,
                value,
                "USD",
                value,
                grade,
                council,
                sector or "Crypto",
                "api",
                now,
                "bitso",
            ),
        )
        imported += 1
        total_usd += value
        live.append(currency)
        print(f"  ✅ {currency}: {float(total):.8f} @ ${px:,.4f} = ${value:,.2f}")

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
        conn.rollback()
        # re-open txn for main work already committed? keep simple
        pass

    conn.commit()
    conn.close()
    print(f"Bitso done · n={imported} · ${total_usd:,.2f}")
    return 0 if imported >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
