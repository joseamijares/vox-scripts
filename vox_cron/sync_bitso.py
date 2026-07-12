#!/usr/bin/env python3
"""Sync Bitso balances into broker_positions."""
from __future__ import annotations

import hashlib
import hmac
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
import requests


def load_env_keys():
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and not v.startswith("***") and k not in os.environ:
            os.environ[k] = v
        # Always prefer non-placeholder from file for bitso keys
        if k in ("BITSO_API_KEY", "BITSO_API_SECRET", "DB_PASSWORD", "PGPASSWORD") and v and not v.startswith("***"):
            os.environ[k] = v


def get_db():
    pwd = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        user=os.environ.get("PGUSER", "postgres"),
        password=pwd,
        dbname=os.environ.get("PGDATABASE", "railway"),
        connect_timeout=20,
    )


def main() -> int:
    load_env_keys()
    print("🔄 Syncing Bitso positions...")

    api_key = os.environ.get("BITSO_API_KEY")
    api_secret = os.environ.get("BITSO_API_SECRET")
    if not api_key or not api_secret or api_key.startswith("***"):
        print("❌ Missing Bitso credentials")
        return 1

    base_url = "https://api.bitso.com"
    nonce = str(int(datetime.now().timestamp() * 1000))
    http_method = "GET"
    request_path = "/api/v3/balance/"
    message = nonce + http_method + request_path
    signature = hmac.new(api_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {
        "Authorization": f"Bitso {api_key}:{nonce}:{signature}",
        "Content-Type": "application/json",
    }

    resp = requests.get(f"{base_url}{request_path}", headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"❌ Bitso API error: {resp.status_code}")
        print(f"Error: {resp.text[:500]}")
        return 1

    data = resp.json()
    if not data.get("success"):
        print(f"❌ Bitso API returned error: {data}")
        return 1

    balances = data.get("payload", {}).get("balances", [])

    # BTC USD reference
    btc_price = 0.0
    btc_resp = requests.get("https://api.bitso.com/api/v3/ticker/?book=btc_usd", timeout=10)
    if btc_resp.status_code == 200 and btc_resp.json().get("success"):
        btc_price = float(btc_resp.json().get("payload", {}).get("last", 0))
    print(f"BTC price: ${btc_price:,.2f}")

    conn = get_db()
    cur = conn.cursor()
    now = datetime.now()
    imported = 0
    total_usd = 0.0
    live = []

    for balance in balances:
        currency = (balance.get("currency") or "").upper()
        total = Decimal(str(balance.get("total", "0")))
        if total <= 0 or currency == "MXN":
            continue

        price_usd = 0.0
        value_usd = 0.0
        if currency in ("USD", "USDT", "USDC"):
            price_usd = 1.0
            value_usd = float(total)
        elif currency == "BTC":
            price_usd = btc_price
            value_usd = float(total) * price_usd
        else:
            for book in (f"{currency.lower()}_usd", f"{currency.lower()}_usdt"):
                try:
                    pr = requests.get(f"https://api.bitso.com/api/v3/ticker/?book={book}", timeout=10)
                    if pr.status_code == 200 and pr.json().get("success"):
                        price_usd = float(pr.json().get("payload", {}).get("last", 0))
                        value_usd = float(total) * price_usd
                        break
                except Exception:
                    pass
            if price_usd == 0 and btc_price:
                try:
                    pr = requests.get(
                        f"https://api.bitso.com/api/v3/ticker/?book={currency.lower()}_btc",
                        timeout=10,
                    )
                    if pr.status_code == 200 and pr.json().get("success"):
                        price_btc = float(pr.json().get("payload", {}).get("last", 0))
                        price_usd = price_btc * btc_price
                        value_usd = float(total) * price_usd
                except Exception:
                    pass

        if value_usd < 0.5:
            continue

        cur.execute("SELECT grade, council, sector FROM positions WHERE ticker = %s", (currency,))
        result = cur.fetchone()
        grade, council, sector = result if result else (None, None, None)

        cur.execute(
            """
            INSERT INTO broker_positions
            (broker, ticker, shares, live_price, live_value, currency, live_value_usd,
             grade, council, sector, source, last_sync_at, price_source, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (broker, ticker)
            DO UPDATE SET
                shares = EXCLUDED.shares,
                live_price = EXCLUDED.live_price,
                live_value = EXCLUDED.live_value,
                live_value_usd = EXCLUDED.live_value_usd,
                grade = COALESCE(EXCLUDED.grade, broker_positions.grade),
                council = COALESCE(EXCLUDED.council, broker_positions.council),
                sector = COALESCE(EXCLUDED.sector, broker_positions.sector),
                source = EXCLUDED.source,
                last_sync_at = EXCLUDED.last_sync_at,
                price_source = EXCLUDED.price_source,
                updated_at = NOW()
            """,
            (
                "Bitso", currency, float(total), price_usd, value_usd, "USD",
                value_usd, grade, council, sector, "api", now, "bitso",
            ),
        )
        imported += 1
        total_usd += value_usd
        live.append(currency)
        print(f"✅ {currency}: {float(total):.8f} @ ${price_usd:,.2f} = ${value_usd:,.2f}")

    if live:
        cur.execute(
            """
            UPDATE broker_positions
            SET shares = 0, live_value = 0, live_value_usd = 0, updated_at = NOW(),
                source = 'api_stale_zero'
            WHERE broker = 'Bitso'
              AND ticker <> ALL(%s)
              AND COALESCE(shares, 0) > 0
            """,
            (live,),
        )

    try:
        cur.execute(
            """
            UPDATE broker_accounts
            SET last_sync_at = NOW(), updated_at = NOW()
            WHERE broker = 'Bitso'
            """
        )
    except Exception:
        # Bitso may not be in broker_accounts
        try:
            cur.execute(
                """
                INSERT INTO broker_accounts (broker, account_type, has_api, currency_default, is_active, last_sync_at)
                VALUES ('Bitso', 'crypto', TRUE, 'USD', TRUE, NOW())
                ON CONFLICT DO NOTHING
                """
            )
        except Exception:
            pass

    conn.commit()
    conn.close()

    print("=" * 80)
    print("Bitso Sync Complete")
    print(f"Positions: {imported}")
    print(f"Total USD: ${total_usd:,.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
