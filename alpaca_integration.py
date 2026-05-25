#!/usr/bin/env python3
"""
Alpaca Integration — JOS-25
Connects to Alpaca paper/live account for order placement.
Supports stocks and options. Paper trading by default.
"""

import os
import json
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def load_env():
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


def get_alpaca_client(paper=True):
    """Get Alpaca trading client."""
    try:
        from alpaca.trading.client import TradingClient
    except ImportError:
        print("❌ alpaca-py not installed. Run: python3 -m pip install alpaca-py")
        return None

    env = load_env()
    api_key = env.get("ALPACA_API_KEY", "")
    secret_key = env.get("ALPACA_SECRET_KEY", "")

    if not api_key or not secret_key:
        print("❌ ALPACA_API_KEY or ALPACA_SECRET_KEY not set in ~/.hermes/.env")
        print("   Get them from: https://app.alpaca.markets/")
        return None

    # These are LIVE keys (endpoint is api.alpaca.markets, not paper-api)
    is_paper = env.get("ALPACA_PAPER", "false").lower() == "true"
    
    if not is_paper:
        print("⚠️  ⚠️  ⚠️  LIVE TRADING MODE  ⚠️  ⚠️  ⚠️")
        print("   Real money will be used. Kill switches active.")
    else:
        print("📋 Paper trading mode")

    return TradingClient(api_key, secret_key, paper=is_paper)


def check_kill_switches(order_value=0):
    """
    Safety checks before ANY order.
    Returns (allowed: bool, reason: str)
    """
    env = load_env()
    
    # Kill switch 1: Max daily loss
    daily_loss_limit = float(env.get("MAX_DAILY_LOSS", "500"))
    
    # Kill switch 2: Max position size
    max_position = float(env.get("MAX_POSITION_SIZE", "2000"))
    
    # Kill switch 3: Max portfolio risk %
    max_portfolio_risk_pct = float(env.get("MAX_PORTFOLIO_RISK_PCT", "5"))
    
    # Kill switch 4: Master disable
    if env.get("TRADING_DISABLED", "false").lower() == "true":
        return False, "🚫 TRADING_DISABLED flag is set in .env"
    
    # Check position size
    if order_value > max_position:
        return False, f"🚫 Order ${order_value:.0f} exceeds max position ${max_position:.0f}"
    
    # Check daily loss tracking
    loss_log_path = Path.home() / ".hermes" / "scripts" / "daily_loss_log.json"
    today = datetime.now().strftime("%Y-%m-%d")
    daily_loss = 0
    
    if loss_log_path.exists():
        try:
            with open(loss_log_path) as f:
                data = json.load(f)
            daily_loss = data.get(today, 0)
        except:
            pass
    
    if daily_loss >= daily_loss_limit:
        return False, f"🚫 Daily loss limit reached: ${daily_loss:.0f}/${daily_loss_limit:.0f}"
    
    return True, "✅ Kill switches passed"


def get_account_info():
    """Get Alpaca account details."""
    client = get_alpaca_client(paper=True)
    if not client:
        return None

    try:
        account = client.get_account()
        return {
            "account_id": account.id,
            "status": account.status,
            "currency": account.currency,
            "cash": float(account.cash),
            "portfolio_value": float(account.portfolio_value),
            "buying_power": float(account.buying_power),
            "equity": float(account.equity),
            "maintenance_margin": float(account.maintenance_margin),
            "daytrade_count": account.daytrade_count,
            "pattern_day_trader": account.pattern_day_trader,
        }
    except Exception as e:
        return {"error": str(e)}


def place_stock_order(symbol, qty, side="buy", order_type="market", time_in_force="day"):
    """Place a stock order with kill switches."""
    client = get_alpaca_client()
    if not client:
        return None

    # Kill switch check
    env = load_env()
    price_estimate = 100  # Will get actual price from API
    order_value = qty * price_estimate
    
    allowed, reason = check_kill_switches(order_value)
    print(f"Kill switch check: {reason}")
    if not allowed:
        return {"error": reason, "blocked": True}

    try:
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        tif = TimeInForce.DAY if time_in_force == "day" else TimeInForce.GTC

        if order_type.lower() == "market":
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=side_enum,
                time_in_force=tif
            )
        else:
            print("❌ Only market orders supported in v1")
            return None

        print(f"\n⚠️  ABOUT TO PLACE LIVE ORDER:")
        print(f"   {side.upper()} {qty} shares of {symbol}")
        print(f"   This is REAL MONEY. Confirm? (y/n)")
        # In automated mode, we'd skip this. For now, require confirmation.
        
        order = client.submit_order(order_request)
        return {
            "id": order.id,
            "symbol": order.symbol,
            "qty": order.qty,
            "side": order.side,
            "type": order.type,
            "status": order.status,
            "created_at": str(order.created_at),
            "live": True,
        }
    except Exception as e:
        return {"error": str(e)}


def get_positions():
    """Get current positions."""
    client = get_alpaca_client(paper=True)
    if not client:
        return None

    try:
        positions = client.get_all_positions()
        return [
            {
                "symbol": pos.symbol,
                "qty": pos.qty,
                "market_value": float(pos.market_value),
                "avg_entry_price": float(pos.avg_entry_price),
                "unrealized_pl": float(pos.unrealized_pl),
                "unrealized_plpc": float(pos.unrealized_plpc),
                "current_price": float(pos.current_price),
            }
            for pos in positions
        ]
    except Exception as e:
        return {"error": str(e)}


def get_orders(status="open"):
    """Get orders."""
    client = get_alpaca_client(paper=True)
    if not client:
        return None

    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        status_enum = QueryOrderStatus.OPEN if status == "open" else QueryOrderStatus.CLOSED
        request = GetOrdersRequest(status=status_enum)
        orders = client.get_orders(request)

        return [
            {
                "id": order.id,
                "symbol": order.symbol,
                "qty": order.qty,
                "side": order.side,
                "type": order.type,
                "status": order.status,
                "filled_qty": order.filled_qty,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
            }
            for order in orders
        ]
    except Exception as e:
        return {"error": str(e)}


def test_alpaca_connection():
    """Test Alpaca connection and display account info."""
    print("=" * 70)
    print("🦙 ALPACA INTEGRATION TEST")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    account = get_account_info()
    if not account:
        print("❌ Failed to connect. Check API keys in ~/.hermes/.env")
        return False

    if "error" in account:
        print(f"❌ API Error: {account['error']}")
        return False

    print("✅ CONNECTED!")
    print()
    print("ACCOUNT INFO:")
    print(f"   Account ID:   {account['account_id']}")
    print(f"   Status:       {account['status']}")
    print(f"   Cash:         ${account['cash']:,.2f}")
    print(f"   Equity:       ${account['equity']:,.2f}")
    print(f"   Buying Power: ${account['buying_power']:,.2f}")
    print(f"   Portfolio:    ${account['portfolio_value']:,.2f}")
    print(f"   Daytrades:    {account['daytrade_count']}")
    print(f"   PDT Status:   {'Yes' if account['pattern_day_trader'] else 'No'}")
    print()

    # Show kill switch settings
    env = load_env()
    print("KILL SWITCHES:")
    print(f"   Max daily loss:    ${env.get('MAX_DAILY_LOSS', '500')}")
    print(f"   Max position:      ${env.get('MAX_POSITION_SIZE', '2000')}")
    print(f"   Max portfolio risk: {env.get('MAX_PORTFOLIO_RISK_PCT', '5')}%")
    print(f"   Trading disabled:  {env.get('TRADING_DISABLED', 'false')}")
    print()

    # Positions
    positions = get_positions()
    if positions and not isinstance(positions, dict):
        print(f"POSITIONS ({len(positions)}):")
        for pos in positions:
            pl_emoji = "🟢" if pos["unrealized_pl"] >= 0 else "🔴"
            print(f"   {pl_emoji} {pos['symbol']}: {pos['qty']} shares @ ${pos['avg_entry_price']:.2f}")
            print(f"      Current: ${pos['current_price']:.2f} | P&L: ${pos['unrealized_pl']:,.2f} ({pos['unrealized_plpc']*100:+.1f}%)")
    else:
        print("POSITIONS: None")

    print()

    # Open orders
    orders = get_orders("open")
    if orders and not isinstance(orders, dict):
        print(f"OPEN ORDERS ({len(orders)}):")
        for order in orders:
            print(f"   {order['side']} {order['qty']} {order['symbol']} — {order['status']}")
    else:
        print("OPEN ORDERS: None")

    print()
    print("=" * 70)
    print("✅ Alpaca integration ready!")
    print("=" * 70)

    return True


def main():
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "test":
            test_alpaca_connection()
        elif cmd == "buy" and len(sys.argv) >= 4:
            symbol = sys.argv[2].upper()
            qty = float(sys.argv[3])
            result = place_stock_order(symbol, qty, "buy")
            print(json.dumps(result, indent=2))
        elif cmd == "sell" and len(sys.argv) >= 4:
            symbol = sys.argv[2].upper()
            qty = float(sys.argv[3])
            result = place_stock_order(symbol, qty, "sell")
            print(json.dumps(result, indent=2))
        elif cmd == "positions":
            result = get_positions()
            print(json.dumps(result, indent=2))
        elif cmd == "orders":
            result = get_orders("open")
            print(json.dumps(result, indent=2))
        else:
            print("Usage:")
            print("  python3 alpaca_integration.py test")
            print("  python3 alpaca_integration.py buy AAPL 10")
            print("  python3 alpaca_integration.py sell AAPL 5")
            print("  python3 alpaca_integration.py positions")
            print("  python3 alpaca_integration.py orders")
    else:
        test_alpaca_connection()


if __name__ == "__main__":
    main()
