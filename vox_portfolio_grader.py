#!/usr/bin/env python3
"""
VOX Portfolio Grader + Entry/Exit Target Generator
Proactively grades all portfolio positions with multi-factor scoring
"""

import json, os, sys, urllib.request, math
from datetime import datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")

def load_env():
    env = {}
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v.strip('"').strip("'")
    return env

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_api(endpoint):
    url = f"https://api.polygon.io{endpoint}&apiKey={POLYGON_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

def get_daily_bars(ticker, days=60):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - __import__('datetime').timedelta(days=days)).strftime("%Y-%m-%d")
    data = polygon_api(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?limit=5000")
    return data.get("results", [])

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[-i] - closes[-i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(bars, period=14):
    if len(bars) < period:
        return None
    trs = []
    for i in range(1, min(period + 1, len(bars))):
        high = bars[-i]["h"]
        low = bars[-i]["l"]
        prev_close = bars[-i-1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs) / len(trs)

def grade_position(ticker, bars, position_data):
    """Multi-factor grading with entry/exit targets for portfolio positions"""
    if not bars or len(bars) < 21:
        return None
    
    closes = [b["c"] for b in bars]
    volumes = [b["v"] for b in bars]
    current_price = closes[-1]
    
    # Technical indicators
    ema21 = calculate_ema(closes, 21)
    ema50 = calculate_ema(closes, 50) if len(closes) >= 50 else None
    rsi = calculate_rsi(closes)
    atr = calculate_atr(bars)
    
    if not ema21 or not atr:
        return None
    
    # Volume analysis
    avg_volume = sum(volumes[-20:]) / 20
    latest_volume = volumes[-1]
    volume_ratio = latest_volume / avg_volume if avg_volume > 0 else 1
    
    # Support/Resistance
    recent_highs = [b["h"] for b in bars[-20:]]
    recent_lows = [b["l"] for b in bars[-20:]]
    resistance = max(recent_highs)
    support = min(recent_lows)
    
    # Position context
    entry_price = position_data.get("price", current_price)
    shares = position_data.get("shares", 0)
    live_value = position_data.get("live_value", 0)
    live_pnl = position_data.get("live_pnl", 0)
    pnl_pct = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
    
    # === GRADING ===
    # Trend score (0-30)
    trend_score = 15
    if ema50 and current_price > ema21 > ema50:
        trend_score = 30
    elif current_price > ema21:
        trend_score = 24
    elif ema50 and current_price > ema50:
        trend_score = 18
    elif ema50 and ema21 > ema50:
        trend_score = 12
    else:
        trend_score = 6
    
    # Momentum score (0-25)
    momentum_score = 12.5
    if rsi > 70:
        momentum_score = 20
    elif rsi > 60:
        momentum_score = 25
    elif rsi > 50:
        momentum_score = 20
    elif rsi > 40:
        momentum_score = 15
    elif rsi > 30:
        momentum_score = 10
    else:
        momentum_score = 5
    
    # Volatility score (0-20)
    vol_pct = (atr / current_price) * 100
    if vol_pct < 2:
        volatility_score = 20
    elif vol_pct < 4:
        volatility_score = 16
    elif vol_pct < 6:
        volatility_score = 12
    elif vol_pct < 10:
        volatility_score = 8
    else:
        volatility_score = 4
    
    # Volume score (0-15)
    if volume_ratio > 2.0:
        volume_score = 15
    elif volume_ratio > 1.5:
        volume_score = 12
    elif volume_ratio > 1.2:
        volume_score = 9
    elif volume_ratio > 0.8:
        volume_score = 7
    else:
        volume_score = 4
    
    # Support/Resistance score (0-10)
    sr_score = 5
    if current_price > resistance * 0.98:
        sr_score = 10
    elif current_price > support * 1.05:
        sr_score = 7
    elif current_price < support * 1.02:
        sr_score = 3
    
    total_score = trend_score + momentum_score + volatility_score + volume_score + sr_score
    grade = min(100, max(0, int(total_score)))
    
    # === ENTRY/EXIT TARGETS ===
    # For existing positions: trailing stop and add-on levels
    if current_price > ema21:
        add_on_zone = ema21 * 0.98
    else:
        add_on_zone = support * 1.01
    
    # Trailing stop: below support or ATR-based
    trailing_stop = min(support * 0.97, current_price - (atr * 2))
    
    # Take profit 1: recent resistance
    take_profit_1 = resistance * 1.02
    
    # Take profit 2: extended target (3R)
    risk = current_price - trailing_stop
    take_profit_2 = current_price + (risk * 3)
    
    # Signal
    if grade >= 70:
        signal = "STRONG_HOLD"
    elif grade >= 60:
        signal = "HOLD"
    elif grade >= 50:
        signal = "HOLD"
    elif grade >= 40:
        signal = "WEAK"
    elif grade >= 30:
        signal = "TRIM"
    else:
        signal = "SELL"
    
    # Override for positions with big gains
    if pnl_pct > 50 and grade >= 50:
        signal = "STRONG_HOLD"
    elif pnl_pct < -20 and grade < 40:
        signal = "CUT_LOSS"
    
    return {
        "ticker": ticker,
        "price": round(current_price, 2),
        "entry_price": round(entry_price, 2),
        "shares": shares,
        "live_value": round(live_value, 2),
        "live_pnl": round(live_pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "grade": grade,
        "signal": signal,
        "rsi": round(rsi, 1),
        "ema21": round(ema21, 2),
        "ema50": round(ema50, 2) if ema50 else None,
        "atr": round(atr, 2),
        "volume_ratio": round(volume_ratio, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "add_on_zone": round(add_on_zone, 2),
        "trailing_stop": round(trailing_stop, 2),
        "take_profit_1": round(take_profit_1, 2),
        "take_profit_2": round(take_profit_2, 2),
        "risk_reward": round((take_profit_1 - current_price) / (current_price - trailing_stop), 2) if (current_price - trailing_stop) > 0 else 0,
        "scores": {
            "trend": round(trend_score, 1),
            "momentum": round(momentum_score, 1),
            "volatility": round(volatility_score, 1),
            "volume": round(volume_score, 1),
            "support_resistance": round(sr_score, 1)
        },
        "graded_at": datetime.now().isoformat()
    }

def main():
    print("=" * 60)
    print("VOX PORTFOLIO GRADER + ENTRY/EXIT TARGETS")
    print("=" * 60)
    
    # Load portfolio
    portfolio_path = os.path.expanduser("~/.hermes/scripts/dashboard_positions_live.json")
    with open(portfolio_path) as f:
        data = json.load(f)
    
    positions = data.get("positions", [])
    print(f"\nGrading {len(positions)} portfolio positions...")
    print("-" * 60)
    
    graded = []
    errors = []
    
    for i, pos in enumerate(positions):
        ticker = pos["ticker"]
        print(f"\n[{i+1}/{len(positions)}] {ticker}...", end=" ", flush=True)
        
        bars = get_daily_bars(ticker)
        if not bars or len(bars) < 21:
            print(f"ERROR: Insufficient data ({len(bars)} bars)")
            errors.append({"ticker": ticker, "error": "insufficient_data"})
            continue
        
        result = grade_position(ticker, bars, pos)
        
        if result:
            graded.append(result)
            print(f"GRADE={result['grade']} SIGNAL={result['signal']} PnL={result['pnl_pct']}%")
            print(f"       Add@${result['add_on_zone']} → TP1=${result['take_profit_1']} → TP2=${result['take_profit_2']}")
            print(f"       Trailing@${result['trailing_stop']} R:R={result['risk_reward']}x")
        else:
            print("ERROR: Grading failed")
            errors.append({"ticker": ticker, "error": "grading_failed"})
    
    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "total": len(positions),
        "graded": len(graded),
        "errors": len(errors),
        "results": graded,
        "errors_detail": errors
    }
    
    output_path = os.path.expanduser("~/.hermes/scripts/vox_portfolio_graded.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {len(positions)}")
    print(f"Graded: {len(graded)}")
    print(f"Errors: {len(errors)}")
    
    if graded:
        strong_hold = [g for g in graded if g["signal"] == "STRONG_HOLD"]
        hold = [g for g in graded if g["signal"] == "HOLD"]
        weak = [g for g in graded if g["signal"] == "WEAK"]
        trim = [g for g in graded if g["signal"] == "TRIM"]
        sell = [g for g in graded if g["signal"] == "SELL"]
        cut_loss = [g for g in graded if g["signal"] == "CUT_LOSS"]
        
        print(f"\nSTRONG HOLD: {len(strong_hold)}")
        for g in strong_hold[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
        
        print(f"\nHOLD: {len(hold)}")
        for g in hold[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
        
        print(f"\nWEAK: {len(weak)}")
        for g in weak[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
        
        print(f"\nTRIM: {len(trim)}")
        for g in trim[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
        
        print(f"\nSELL: {len(sell)}")
        for g in sell[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
        
        print(f"\nCUT LOSS: {len(cut_loss)}")
        for g in cut_loss[:5]:
            print(f"  {g['ticker']}: {g['grade']} | PnL {g['pnl_pct']}% | ${g['live_value']}")
    
    print(f"\nSaved to: {output_path}")
    return output

if __name__ == "__main__":
    main()
