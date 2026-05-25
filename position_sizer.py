#!/usr/bin/env python3
"""
Position Sizing Calculator — JOS-11
Kelly Criterion + Risk-based sizing with portfolio context.
"""

import json
import math
from pathlib import Path
from datetime import datetime


def kelly_fraction(win_rate, avg_win, avg_loss):
    """
    Kelly Criterion: f* = (p*b - q) / b
    where p = win rate, q = loss rate, b = avg_win/avg_loss
    """
    if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
        return 0
    b = avg_win / avg_loss
    q = 1 - win_rate
    kelly = (win_rate * b - q) / b
    return max(0, min(0.25, kelly))  # Cap at 25% per trade


def calculate_position(
    ticker,
    entry_price,
    stop_loss,
    target_price,
    portfolio_value,
    risk_per_trade_pct=1.0,  # Default 1% risk per trade
    win_rate=0.55,           # Your historical win rate
    avg_win_pct=8.0,         # Average winning trade %
    avg_loss_pct=4.0,        # Average losing trade %
    max_position_pct=10.0,   # Max position as % of portfolio
    confidence=1.0,          # 0.5-1.5 multiplier based on grade
):
    """
    Calculate optimal position size.
    """
    print(f"\n{'='*70}")
    print(f"📐 POSITION SIZER: {ticker}")
    print(f"{'='*70}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Risk parameters
    risk_amount = portfolio_value * (risk_per_trade_pct / 100)
    stop_distance = abs(entry_price - stop_loss)
    target_distance = abs(target_price - entry_price)

    if stop_distance == 0:
        print("❌ Stop loss cannot equal entry price")
        return None

    # Risk-based shares
    risk_based_shares = int(risk_amount / stop_distance)
    risk_based_value = risk_based_shares * entry_price
    risk_based_pct = (risk_based_value / portfolio_value) * 100

    # Kelly-optimal fraction
    kelly = kelly_fraction(win_rate, avg_win_pct, avg_loss_pct)
    kelly_value = portfolio_value * kelly * confidence
    kelly_shares = int(kelly_value / entry_price)
    kelly_pct = (kelly_shares * entry_price / portfolio_value) * 100

    # R/R ratio
    rr_ratio = target_distance / stop_distance

    # Expected value per trade
    expected_value = (win_rate * target_distance) - ((1 - win_rate) * stop_distance)
    expected_value_pct = (expected_value / entry_price) * 100

    # Position sizing decision
    # Use the SMALLER of risk-based and Kelly, but cap at max_position_pct
    suggested_value = min(risk_based_value, kelly_value)
    suggested_value = min(suggested_value, portfolio_value * (max_position_pct / 100))
    suggested_shares = int(suggested_value / entry_price)
    suggested_pct = (suggested_shares * entry_price / portfolio_value) * 100

    # Display
    print(f"INPUTS:")
    print(f"   Entry:        ${entry_price:.2f}")
    print(f"   Stop:         ${stop_loss:.2f} ({((stop_loss-entry_price)/entry_price*100):+.1f}%)")
    print(f"   Target:       ${target_price:.2f} ({((target_price-entry_price)/entry_price*100):+.1f}%)")
    print(f"   Portfolio:    ${portfolio_value:,.0f}")
    print(f"   Risk/trade:   {risk_per_trade_pct}% (${risk_amount:,.0f})")
    print()

    print(f"RISK ANALYSIS:")
    print(f"   Stop distance:  ${stop_distance:.2f}")
    print(f"   Target distance: ${target_distance:.2f}")
    print(f"   R/R ratio:      1:{rr_ratio:.1f}")
    print(f"   Expected value: ${expected_value:.2f} ({expected_value_pct:+.2f}%)")
    print()

    print(f"POSITION OPTIONS:")
    print(f"   Risk-based:     {risk_based_shares:,.0f} shares = ${risk_based_value:,.0f} ({risk_based_pct:.1f}% of portfolio)")
    print(f"   Kelly ({kelly*100:.1f}%):     {kelly_shares:,.0f} shares = ${kelly_shares*entry_price:,.0f} ({kelly_pct:.1f}% of portfolio)")
    print()

    print(f"{'='*70}")
    print(f"SUGGESTED POSITION")
    print(f"{'='*70}")
    print(f"   Shares:   {suggested_shares:,.0f}")
    print(f"   Value:    ${suggested_shares * entry_price:,.0f}")
    print(f"   % of PF:  {suggested_pct:.1f}%")
    print(f"   Max loss: ${suggested_shares * stop_distance:,.0f} ({(suggested_shares*stop_distance/portfolio_value*100):.1f}% of portfolio)")
    print(f"   Max gain: ${suggested_shares * target_distance:,.0f} ({(suggested_shares*target_distance/portfolio_value*100):.1f}% of portfolio)")
    print(f"{'='*70}")

    # Warnings
    if rr_ratio < 1.5:
        print(f"\n⚠️  WARNING: R/R ratio {rr_ratio:.1f} is below 1.5 minimum. Consider better entry or wider target.")
    if suggested_pct > max_position_pct * 0.8:
        print(f"⚠️  WARNING: Position near max limit ({max_position_pct}%).")
    if expected_value <= 0:
        print(f"🚫 NEGATIVE EXPECTED VALUE — DO NOT TAKE THIS TRADE")

    # Grade-based sizing adjustment
    print(f"\nGRADE-BASED ADJUSTMENTS:")
    print(f"   If Grade 85+ (Strong Buy): Use full position above")
    print(f"   If Grade 70-84 (Moderate): Reduce by 25% → {int(suggested_shares*0.75):,.0f} shares")
    print(f"   If Grade 55-69 (Neutral):  Reduce by 50% → {int(suggested_shares*0.5):,.0f} shares (or skip)")
    print(f"   If Grade <55 (Avoid):      NO POSITION")

    result = {
        "ticker": ticker,
        "timestamp": datetime.now().isoformat(),
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "target_price": target_price,
        "portfolio_value": portfolio_value,
        "risk_per_trade_pct": risk_per_trade_pct,
        "rr_ratio": round(rr_ratio, 2),
        "suggested_shares": suggested_shares,
        "suggested_value": round(suggested_shares * entry_price, 2),
        "suggested_pct_of_portfolio": round(suggested_pct, 2),
        "max_loss": round(suggested_shares * stop_distance, 2),
        "max_gain": round(suggested_shares * target_distance, 2),
        "kelly_fraction": round(kelly, 4),
        "expected_value_pct": round(expected_value_pct, 2),
    }

    # Save
    out_path = Path.home() / ".hermes" / "scripts" / "position_results.json"
    if out_path.exists():
        with open(out_path) as f:
            all_results = json.load(f)
    else:
        all_results = {"positions": []}
    all_results["positions"].append(result)
    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"\n💾 Saved to position_results.json")

    return result


def main():
    import sys
    if len(sys.argv) >= 5:
        ticker = sys.argv[1].upper()
        entry = float(sys.argv[2])
        stop = float(sys.argv[3])
        target = float(sys.argv[4])
        portfolio = float(sys.argv[5]) if len(sys.argv) > 5 else 195000
        calculate_position(ticker, entry, stop, target, portfolio)
    else:
        print("Usage: python3 position_sizer.py TICKER ENTRY STOP TARGET [PORTFOLIO]")
        print("Example: python3 position_sizer.py WDC 486 470 525 195000")
        print()
        # Demo
        calculate_position("WDC", 486.46, 470.0, 525.0, 195000)


if __name__ == "__main__":
    main()
