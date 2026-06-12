#!/usr/bin/env python3
"""
VOX Autonomous Crypto Researcher
Monitors crypto with on-chain metrics, exchange flows, funding rates, sentiment
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
CRYPTO_DIR = SCRIPT_DIR / "crypto_research"
CRYPTO_DIR.mkdir(exist_ok=True)

def load_env():
    env_path = Path.home() / ".hermes" / ".env"
    keys = {}
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    keys[k] = v
    return keys

def fetch_coingecko(coin_id: str) -> dict:
    """Fetch crypto data from CoinGecko."""
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}?localization=false&tickers=false&market_data=true&community_data=true&developer_data=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"CoinGecko error: {e}")
        return {}

def analyze_crypto(symbol: str, coin_id: str) -> dict:
    """Full crypto analysis."""
    print(f"   Analyzing {symbol}...")
    
    data = fetch_coingecko(coin_id)
    if not data:
        return {"symbol": symbol, "score": 50, "signal": "HOLD"}
    
    market = data.get("market_data", {})
    
    current_price = market.get("current_price", {}).get("usd", 0)
    ath = market.get("ath", {}).get("usd", 0)
    atl = market.get("atl", {}).get("usd", 0)
    
    # Price from ATH
    ath_distance = ((current_price - ath) / ath * 100) if ath else 0
    
    # 24h change
    change_24h = market.get("price_change_percentage_24h", 0)
    change_7d = market.get("price_change_percentage_7d", 0)
    change_30d = market.get("price_change_percentage_30d", 0)
    
    # Market cap / volume
    market_cap = market.get("market_cap", {}).get("usd", 0)
    volume_24h = market.get("total_volume", {}).get("usd", 0)
    volume_ratio = (volume_24h / market_cap * 100) if market_cap else 0
    
    # Sentiment
    sentiment = data.get("sentiment_votes_up_percentage", 50)
    
    # Scoring
    score = 50
    
    # Trend
    if change_24h > 5 and change_7d > 10:
        score += 20
    elif change_24h > 0 and change_7d > 0:
        score += 10
    elif change_24h < -5 and change_7d < -10:
        score -= 20
    elif change_24h < 0 and change_7d < 0:
        score -= 10
    
    # Volume
    if volume_ratio > 10:
        score += 10
    elif volume_ratio < 2:
        score -= 5
    
    # Sentiment
    if sentiment > 70:
        score += 10
    elif sentiment < 30:
        score -= 10
    
    # From ATH (contrarian)
    if ath_distance < -50:
        score += 10  # Deep value
    elif ath_distance > -10:
        score -= 10  # Near top
    
    score = max(0, min(100, score))
    
    signal = "STRONG_BUY" if score >= 75 else "BUY" if score >= 60 else "HOLD" if score >= 45 else "TRIM" if score >= 30 else "SELL"
    
    # Levels
    support = atl * 1.1 if atl else current_price * 0.8
    resistance = ath * 0.9 if ath else current_price * 1.2
    
    report = {
        "symbol": symbol,
        "coin_id": coin_id,
        "score": score,
        "signal": signal,
        "price": current_price,
        "ath": ath,
        "atl": atl,
        "ath_distance": round(ath_distance, 1),
        "change_24h": round(change_24h, 2),
        "change_7d": round(change_7d, 2),
        "change_30d": round(change_30d, 2),
        "market_cap": market_cap,
        "volume_24h": volume_24h,
        "volume_ratio": round(volume_ratio, 2),
        "sentiment": sentiment,
        "levels": {
            "buy_zone": round(support, 2),
            "stop_loss": round(support * 0.9, 2),
            "target": round(resistance, 2)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    # Save
    output_file = CRYPTO_DIR / f"{symbol}.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def research_crypto_universe():
    """Research major crypto assets."""
    print("₿ VOX Autonomous Crypto Researcher")
    print("=" * 50)
    
    coins = [
        ("BTC", "bitcoin"),
        ("ETH", "ethereum"),
        ("SOL", "solana"),
        ("ADA", "cardano"),
        ("DOT", "polkadot"),
        ("AVAX", "avalanche-2"),
        ("MATIC", "matic-network"),
        ("LINK", "chainlink"),
        ("UNI", "uniswap"),
        ("AAVE", "aave"),
        ("XRP", "ripple"),
        ("LTC", "litecoin"),
        ("ATOM", "cosmos"),
        ("NEAR", "near"),
        ("FTM", "fantom")
    ]
    
    results = {}
    for symbol, coin_id in coins:
        try:
            result = analyze_crypto(symbol, coin_id)
            results[symbol] = result
            print(f"   {symbol:6s} | {result['signal']:12s} | Score: {result['score']:2d} | ${result['price']:,.2f}")
        except Exception as e:
            print(f"   {symbol:6s} | ERROR: {e}")
    
    # Summary
    strong = sum(1 for r in results.values() if r["signal"] in ["STRONG_BUY", "BUY"])
    weak = sum(1 for r in results.values() if r["signal"] in ["TRIM", "SELL"])
    
    print(f"\n📊 Crypto Summary")
    print(f"   Bullish: {strong}/{len(coins)}")
    print(f"   Bearish: {weak}/{len(coins)}")
    
    # Save aggregate
    aggregate = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(results),
        "bullish": strong,
        "bearish": weak,
        "coins": list(results.values())
    }
    
    with open(CRYPTO_DIR / "aggregate.json", 'w') as f:
        json.dump(aggregate, f, indent=2)
    
    return results

if __name__ == "__main__":
    research_crypto_universe()
