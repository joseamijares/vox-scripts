#!/usr/bin/env python3
"""
VOX Market Regime Detector v1.0
Detects market regime: Bull/Bear/Range/Volatile
Adjusts strategy weights accordingly.

Regimes:
- EARLY_BULL: Rising prices, low volatility, increasing volume
- LATE_BULL: High prices, high volatility, divergences
- EARLY_BEAR: Falling prices, increasing volatility
- LATE_BEAR: Capitulation, extreme fear
- RANGE: Sideways, low volatility
- VOLATILE: High volatility, directionless

Usage:
    python3 vox_regime_detector.py detect
    python3 vox_regime_detector.py history
"""

import json
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List

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

ENV = load_env()
POLYGON_KEY = ENV.get("POLYGON_API_KEY", "")

def polygon_get(path, params=""):
    if not POLYGON_KEY:
        return {"error": "POLYGON_API_KEY not set"}
    url = f"https://api.polygon.io{path}?apiKey={POLYGON_KEY}{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "Vox-Finance/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

def get_market_data(ticker: str = "SPY", days: int = 60) -> List[Dict]:
    """Get market data for regime detection"""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days + 10)).strftime("%Y-%m-%d")
    result = polygon_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}")
    if "error" in result:
        return []
    return result.get("results", [])

def calculate_ema(prices: List[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices: List[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(bars: List[Dict], period: int = 14) -> float:
    """Calculate Average True Range"""
    if len(bars) < period + 1:
        return 0
    trs = []
    for i in range(1, len(bars)):
        high = bars[i]["h"]
        low = bars[i]["l"]
        prev_close = bars[i-1]["c"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return sum(trs[-period:]) / period

def detect_regime() -> Dict:
    """Detect current market regime"""
    print("\n🌍 Detecting market regime...")
    
    # Get SPY data
    bars = get_market_data("SPY", 60)
    if not bars:
        return {"error": "No market data"}
    
    closes = [b["c"] for b in bars]
    volumes = [b["v"] for b in bars]
    
    # Calculate indicators
    ema_20 = calculate_ema(closes, 20)
    ema_50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes)
    atr = calculate_atr(bars)
    
    current_price = closes[-1]
    
    # Price vs EMAs
    above_ema20 = current_price > ema_20
    above_ema50 = current_price > ema_50
    ema20_above_50 = ema_20 > ema_50
    
    # Trend strength
    price_20d_ago = closes[-20] if len(closes) >= 20 else closes[0]
    price_50d_ago = closes[-50] if len(closes) >= 50 else closes[0]
    
    return_20d = (current_price - price_20d_ago) / price_20d_ago * 100
    return_50d = (current_price - price_50d_ago) / price_50d_ago * 100
    
    # Volatility
    avg_price = sum(closes) / len(closes)
    volatility = atr / avg_price * 100
    
    # Volume trend
    recent_vol = sum(volumes[-5:]) / 5
    avg_vol = sum(volumes[-20:]) / 20
    volume_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    
    # Determine regime
    regime = "UNKNOWN"
    confidence = 0
    
    if above_ema20 and above_ema50 and ema20_above_50:
        if return_20d > 5 and volatility < 2:
            regime = "EARLY_BULL"
            confidence = 85
        elif return_20d > 5 and volatility >= 2:
            regime = "LATE_BULL"
            confidence = 70
        else:
            regime = "BULL"
            confidence = 75
    elif not above_ema20 and not above_ema50 and not ema20_above_50:
        if return_20d < -5 and volatility > 3:
            regime = "EARLY_BEAR"
            confidence = 80
        elif return_20d < -10:
            regime = "LATE_BEAR"
            confidence = 75
        else:
            regime = "BEAR"
            confidence = 70
    else:
        if volatility > 2.5:
            regime = "VOLATILE"
            confidence = 65
        else:
            regime = "RANGE"
            confidence = 60
    
    # Strategy adjustments per regime
    strategy_adjustments = {
        "EARLY_BULL": {"grade_threshold": 55, "position_size": 1.2, "stop_loss": 12, "trailing_stop": True},
        "BULL": {"grade_threshold": 50, "position_size": 1.0, "stop_loss": 10, "trailing_stop": True},
        "LATE_BULL": {"grade_threshold": 65, "position_size": 0.8, "stop_loss": 8, "trailing_stop": True},
        "EARLY_BEAR": {"grade_threshold": 70, "position_size": 0.5, "stop_loss": 7, "trailing_stop": False},
        "BEAR": {"grade_threshold": 75, "position_size": 0.3, "stop_loss": 5, "trailing_stop": False},
        "LATE_BEAR": {"grade_threshold": 80, "position_size": 0.2, "stop_loss": 5, "trailing_stop": False},
        "RANGE": {"grade_threshold": 60, "position_size": 0.8, "stop_loss": 8, "trailing_stop": False},
        "VOLATILE": {"grade_threshold": 70, "position_size": 0.5, "stop_loss": 6, "trailing_stop": False},
    }
    
    adjustments = strategy_adjustments.get(regime, strategy_adjustments["RANGE"])
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "regime": regime,
        "confidence": confidence,
        "indicators": {
            "price": current_price,
            "ema_20": ema_20,
            "ema_50": ema_50,
            "rsi": rsi,
            "volatility": volatility,
            "return_20d": return_20d,
            "return_50d": return_50d,
            "volume_ratio": volume_ratio,
        },
        "strategy_adjustments": adjustments,
    }
    
    print(f"   Regime: {regime} (confidence: {confidence}%)")
    print(f"   Price: ${current_price:.2f} | EMA20: ${ema_20:.2f} | EMA50: ${ema_50:.2f}")
    print(f"   RSI: {rsi:.1f} | Volatility: {volatility:.1f}% | 20d Return: {return_20d:+.1f}%")
    print(f"   Volume: {volume_ratio:.1f}x average")
    print(f"\n   Strategy Adjustments:")
    print(f"      Grade threshold: {adjustments['grade_threshold']}")
    print(f"      Position size: {adjustments['position_size']}x")
    print(f"      Stop loss: {adjustments['stop_loss']}%")
    print(f"      Trailing stop: {'Yes' if adjustments['trailing_stop'] else 'No'}")
    
    return result

def save_regime(result: Dict):
    """Save regime to file"""
    output_file = Path.home() / ".hermes" / "scripts" / "vox_market_regime.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\n✅ Saved to {output_file}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Regime Detector")
    parser.add_argument("command", choices=["detect", "history"])
    
    args = parser.parse_args()
    
    if args.command == "detect":
        result = detect_regime()
        if "error" not in result:
            save_regime(result)
    elif args.command == "history":
        print("📜 Regime history not yet implemented")

if __name__ == "__main__":
    main()
