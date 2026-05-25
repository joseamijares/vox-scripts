#!/usr/bin/env python3
"""
Bitso API Wrapper using official bitso-py library
Fetches balances and current prices in MXN and USD.
"""

import os
import sys
import json
from pathlib import Path


def load_env():
    """Load API keys from ~/.hermes/.env"""
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    keys[key] = val
    return keys


def fetch_bitso_portfolio():
    """Fetch Bitso account balances using bitso-py."""
    try:
        import bitso
    except ImportError:
        print("❌ bitso-py not installed. Run: pip3 install bitso-py")
        sys.exit(1)

    env = load_env()
    api_key = env.get("BITSO_API_KEY")
    api_secret = env.get("BITSO_API_SECRET")

    if not api_key or not api_secret:
        print("❌ BITSO_API_KEY or BITSO_API_SECRET not found in ~/.hermes/.env")
        sys.exit(1)

    print("🔑 Connecting to Bitso...")

    try:
        api = bitso.Api(api_key, api_secret)

        # Get balances
        balances_obj = api.balances()

        # Get USD/MXN rate
        print("📊 Fetching prices...")
        try:
            usd_ticker = api.ticker("usd_mxn")
            usd_mxn_rate = float(usd_ticker.last)
        except:
            usd_mxn_rate = 0

        # Process balances
        non_zero = []
        total_mxn = 0
        total_usd = 0

        for attr in dir(balances_obj):
            if attr.startswith('_') or attr == 'currencies':
                continue

            bal = getattr(balances_obj, attr)
            if not hasattr(bal, 'total'):
                continue

            total = float(bal.total)
            available = float(bal.available)
            locked = float(bal.locked)

            if total > 0:
                currency = attr.lower()

                # Get price
                price_mxn = 0
                price_usd = 0

                if currency == "mxn":
                    price_mxn = 1.0
                    price_usd = 1.0 / usd_mxn_rate if usd_mxn_rate > 0 else 0
                    value_mxn = total
                    value_usd = total * price_usd
                elif currency == "usd":
                    price_mxn = usd_mxn_rate
                    price_usd = 1.0
                    value_mxn = total * price_mxn
                    value_usd = total
                else:
                    # Try to get price from ticker
                    try:
                        book = f"{currency}_mxn"
                        t = api.ticker(book)
                        price_mxn = float(t.last)
                        price_usd = price_mxn / usd_mxn_rate if usd_mxn_rate > 0 else 0
                    except:
                        price_mxn = 0
                        price_usd = 0

                    value_mxn = total * price_mxn
                    value_usd = total * price_usd

                non_zero.append({
                    "currency": currency,
                    "available": available,
                    "locked": locked,
                    "total": total,
                    "price_mxn": price_mxn,
                    "price_usd": price_usd,
                    "value_mxn": value_mxn,
                    "value_usd": value_usd
                })

                total_mxn += value_mxn
                total_usd += value_usd

        # Sort by USD value
        non_zero.sort(key=lambda x: x["value_usd"], reverse=True)

        return non_zero, total_mxn, total_usd, usd_mxn_rate

    except Exception as e:
        print(f"❌ Bitso API error: {e}")
        sys.exit(1)


def format_portfolio(balances, total_mxn, total_usd, usd_mxn_rate):
    """Pretty-print Bitso portfolio."""
    print("=" * 80)
    print("📊 BITSO PORTFOLIO SUMMARY")
    print("=" * 80)

    print(f"\n💰 TOTAL VALUE: ${total_usd:,.2f} USD | ${total_mxn:,.2f} MXN")
    print(f"📈 USD/MXN Rate: {usd_mxn_rate:,.2f}")
    print(f"📋 Assets: {len(balances)}")

    if balances:
        print("-" * 80)
        print(f"{'Currency':10} | {'Available':>15} | {'Locked':>12} | {'Total':>15} | {'Price USD':>12} | {'Value USD':>12}")
        print("-" * 80)

        for b in balances[:20]:
            currency = b["currency"]
            available = b["available"]
            locked = b["locked"]
            total = b["total"]
            price_usd = b["price_usd"]
            value_usd = b["value_usd"]

            print(f"{currency:10} | {available:15.6f} | {locked:12.6f} | {total:15.6f} | ${price_usd:>10.4f} | ${value_usd:>10.2f}")

        if len(balances) > 20:
            print(f"\n   ... and {len(balances) - 20} more assets")

    print("\n" + "=" * 80)


def main():
    balances, total_mxn, total_usd, rate = fetch_bitso_portfolio()
    format_portfolio(balances, total_mxn, total_usd, rate)

    # Save raw data
    output_path = Path.home() / ".hermes" / "scripts" / "bitso_portfolio.json"
    with open(output_path, "w") as f:
        json.dump({
            "balances": balances,
            "total_mxn": total_mxn,
            "total_usd": total_usd,
            "usd_mxn_rate": rate
        }, f, indent=2)
    print(f"\n💾 Raw data saved to: {output_path}")


if __name__ == "__main__":
    main()
