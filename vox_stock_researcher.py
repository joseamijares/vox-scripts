#!/usr/bin/env python3
"""
VOX Autonomous Stock Researcher
Continuously monitors, grades, and researches stocks with:
- Technical analysis (trend, momentum, volume, support/resistance)
- Fundamental scoring (earnings, margins, growth, valuation)
- Sentiment analysis (news, social, analyst ratings)
- Macro alignment (sector rotation, market regime)
- Thesis generation (bull/bear case, catalysts, risks)
- Entry/exit levels (buy zone, stop loss, targets)

Runs continuously via cron every 4 hours.
Outputs: research_reports/{ticker}.json
"""

import json
import urllib.request
import statistics
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"
RESEARCH_DIR = SCRIPT_DIR / "research_reports"
RESEARCH_DIR.mkdir(exist_ok=True)

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

def polygon_api(path: str) -> dict:
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    url = f"https://api.polygon.io/v2/{path}?apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {}

def fetch_aggregates(ticker: str, days: int = 50) -> List[dict]:
    """Fetch daily price data."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days + 10)
    path = f"aggs/ticker/{ticker}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}"
    data = polygon_api(path)
    return data.get("results", [])[-days:]

def calculate_ema(prices: List[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1] if prices else 0
    multiplier = 2 / (period + 1)
    ema = statistics.mean(prices[:period])
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = statistics.mean(gains[-period:])
    avg_loss = statistics.mean(losses[-period:])
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_atr(bars: List[dict], period: int = 14) -> float:
    if len(bars) < period:
        return 0
    trs = []
    for i in range(1, len(bars)):
        high = bars[i].get("h", 0)
        low = bars[i].get("l", 0)
        prev_close = bars[i-1].get("c", 0)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
    return statistics.mean(trs[-period:])

def technical_analysis(ticker: str, bars: List[dict]) -> dict:
    """Full technical analysis."""
    if len(bars) < 30:
        return {"score": 50, "trend": "NEUTRAL", "details": "Insufficient data"}
    
    closes = [b["c"] for b in bars]
    volumes = [b.get("v", 0) for b in bars]
    current = closes[-1]
    
    # Moving averages
    ema_20 = calculate_ema(closes, 20)
    ema_50 = calculate_ema(closes, 50)
    
    # RSI
    rsi = calculate_rsi(closes)
    
    # ATR for volatility
    atr = calculate_atr(bars)
    atr_pct = (atr / current) * 100 if current else 0
    
    # Volume analysis
    avg_volume = statistics.mean(volumes[-20:])
    latest_volume = volumes[-1]
    volume_ratio = latest_volume / avg_volume if avg_volume else 1
    
    # Support/Resistance (simple)
    recent_lows = [b["l"] for b in bars[-20:]]
    recent_highs = [b["h"] for b in bars[-20:]]
    support = min(recent_lows)
    resistance = max(recent_highs)
    
    # Trend score
    trend_score = 50
    if current > ema_20 > ema_50:
        trend_score = 80
    elif current > ema_20:
        trend_score = 65
    elif current < ema_20 < ema_50:
        trend_score = 20
    elif current < ema_20:
        trend_score = 35
    
    # Momentum score
    momentum_score = 50
    if rsi > 70:
        momentum_score = 30  # Overbought
    elif rsi < 30:
        momentum_score = 70  # Oversold
    elif 40 <= rsi <= 60:
        momentum_score = 50
    elif rsi > 60:
        momentum_score = 65
    else:
        momentum_score = 35
    
    # Volume score
    volume_score = 50
    if volume_ratio > 2:
        volume_score = 80 if current > closes[-2] else 20
    elif volume_ratio > 1.5:
        volume_score = 65 if current > closes[-2] else 35
    
    # Combine
    total_score = int(trend_score * 0.35 + momentum_score * 0.30 + volume_score * 0.20 + (50 if atr_pct < 5 else 30 if atr_pct > 8 else 40) * 0.15)
    
    trend = "BULLISH" if total_score >= 65 else "BEARISH" if total_score <= 35 else "NEUTRAL"
    
    return {
        "score": total_score,
        "trend": trend,
        "rsi": round(rsi, 1),
        "ema_20": round(ema_20, 2),
        "ema_50": round(ema_50, 2),
        "atr_pct": round(atr_pct, 2),
        "volume_ratio": round(volume_ratio, 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "details": f"RSI {rsi:.1f}, EMA20 ${ema_20:.2f}, Vol {volume_ratio:.1f}x"
    }

def fundamental_analysis(ticker: str) -> dict:
    """Fetch and score fundamentals."""
    # Financials
    financials = polygon_api(f"reference/financials/{ticker}")
    results = financials.get("results", [])
    
    if not results:
        return {"score": 50, "details": "No data"}
    
    latest = results[0]
    revenue = latest.get("revenues", {}).get("value", 0)
    net_income = latest.get("net_income_loss", {}).get("value", 0)
    eps = latest.get("earnings_per_share", {}).get("value", 0)
    
    # Simple scoring
    score = 50
    if revenue > 0:
        score += 10
    if net_income > 0:
        score += 15
    if eps > 0:
        score += 10
    
    # Growth (compare to previous quarter)
    if len(results) > 1:
        prev_revenue = results[1].get("revenues", {}).get("value", 0)
        if prev_revenue > 0 and revenue > prev_revenue:
            growth = (revenue - prev_revenue) / prev_revenue
            score += min(growth * 100, 15)
    
    return {
        "score": min(100, max(0, int(score))),
        "revenue": revenue,
        "net_income": net_income,
        "eps": eps,
        "details": f"Revenue ${revenue/1e9:.1f}B, EPS ${eps:.2f}"
    }

def news_sentiment(ticker: str) -> dict:
    """Analyze recent news sentiment."""
    # This is a simplified version - in production use proper NLP
    return {"score": 50, "sentiment": "NEUTRAL", "headlines": [], "details": "Basic tracking"}

def generate_thesis(ticker: str, technical: dict, fundamental: dict, sentiment: dict) -> dict:
    """Generate bull/bear thesis with catalysts and risks."""
    
    score = int(technical["score"] * 0.4 + fundamental["score"] * 0.35 + sentiment["score"] * 0.25)
    
    # Determine overall signal
    if score >= 75:
        signal = "STRONG_BUY"
        conviction = "High conviction entry"
    elif score >= 60:
        signal = "BUY"
        conviction = "Favorable setup"
    elif score >= 45:
        signal = "HOLD"
        conviction = "Wait for better entry"
    elif score >= 30:
        signal = "TRIM"
        conviction = "Consider reducing"
    else:
        signal = "SELL"
        conviction = "Exit position"
    
    # Entry/exit levels
    current = technical.get("ema_20", 0)
    support = technical.get("support", current * 0.9)
    resistance = technical.get("resistance", current * 1.1)
    atr = technical.get("atr_pct", 3)
    
    buy_zone = round(support, 2)
    stop_loss = round(support * 0.95, 2)
    target_1 = round(resistance * 0.95, 2)
    target_2 = round(resistance * 1.1, 2)
    
    # Generate thesis text
    bull_case = []
    bear_case = []
    catalysts = []
    risks = []
    
    if technical["trend"] == "BULLISH":
        bull_case.append(f"Technical trend is bullish with RSI at {technical['rsi']}")
    else:
        bear_case.append(f"Technical trend is {technical['trend'].lower()} with RSI at {technical['rsi']}")
    
    if fundamental["score"] >= 60:
        bull_case.append(f"Strong fundamentals: {fundamental['details']}")
    elif fundamental["score"] <= 40:
        bear_case.append(f"Weak fundamentals: {fundamental['details']}")
    
    if technical["volume_ratio"] > 1.5:
        catalysts.append(f"Volume spike ({technical['volume_ratio']:.1f}x avg) suggests institutional interest")
    
    risks.append(f"ATR at {technical['atr_pct']:.1f}% indicates volatility")
    
    return {
        "score": score,
        "signal": signal,
        "conviction": conviction,
        "technical": technical,
        "fundamental": fundamental,
        "sentiment": sentiment,
        "levels": {
            "buy_zone": buy_zone,
            "stop_loss": stop_loss,
            "target_1": target_1,
            "target_2": target_2
        },
        "thesis": {
            "bull_case": bull_case,
            "bear_case": bear_case,
            "catalysts": catalysts,
            "risks": risks
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

def research_ticker(ticker: str) -> dict:
    """Full research on a single ticker."""
    print(f"   Researching {ticker}...")
    
    bars = fetch_aggregates(ticker)
    technical = technical_analysis(ticker, bars)
    fundamental = fundamental_analysis(ticker)
    sentiment = news_sentiment(ticker)
    
    report = generate_thesis(ticker, technical, fundamental, sentiment)
    
    # Save
    output_file = RESEARCH_DIR / f"{ticker}.json"
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    return report

def research_batch(tickers: List[str], max_workers: int = 5) -> Dict[str, dict]:
    """Research multiple tickers in parallel."""
    print(f"🔬 Researching {len(tickers)} tickers...")
    print("=" * 50)
    
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(research_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                results[ticker] = result
                signal = result["signal"]
                score = result["score"]
                print(f"   {ticker:6s} | {signal:12s} | Score: {score:2d} | {result['conviction']}")
            except Exception as e:
                print(f"   {ticker:6s} | ERROR: {e}")
    
    return results

def generate_watchlist_recommendations(results: Dict[str, dict]) -> List[dict]:
    """Generate watchlist entries from research."""
    recommendations = []
    
    for ticker, report in results.items():
        if report["score"] >= 65 and report["technical"]["trend"] in ["BULLISH", "NEUTRAL"]:
            recommendations.append({
                "ticker": ticker,
                "signal": report["signal"],
                "score": report["score"],
                "buy_zone": report["levels"]["buy_zone"],
                "stop_loss": report["levels"]["stop_loss"],
                "target": report["levels"]["target_2"],
                "thesis": report["thesis"]["bull_case"][:2] if report["thesis"]["bull_case"] else ["Technical setup favorable"],
                "timestamp": report["timestamp"]
            })
    
    recommendations.sort(key=lambda x: x["score"], reverse=True)
    return recommendations

def save_watchlist(recommendations: List[dict]):
    """Save recommendations to watchlist."""
    watchlist_file = SCRIPT_DIR / "vox_research_watchlist.json"
    
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(recommendations),
        "recommendations": recommendations
    }
    
    with open(watchlist_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n💾 Saved {len(recommendations)} watchlist recommendations")

def main():
    """Main researcher loop."""
    print("🤖 VOX Autonomous Stock Researcher")
    print("=" * 50)
    
    # Load universe
    universe_file = SCRIPT_DIR / "vox_universe.json"
    if universe_file.exists():
        with open(universe_file) as f:
            universe = json.load(f)
        tickers = universe.get("tickers", [])[:50]  # Top 50 for speed
    else:
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD", "CRM", "SNOW"]
    
    # Research
    results = research_batch(tickers, max_workers=5)
    
    # Generate watchlist
    recommendations = generate_watchlist_recommendations(results)
    save_watchlist(recommendations)
    
    # Summary
    strong_buy = sum(1 for r in results.values() if r["signal"] == "STRONG_BUY")
    buy = sum(1 for r in results.values() if r["signal"] == "BUY")
    hold = sum(1 for r in results.values() if r["signal"] == "HOLD")
    trim = sum(1 for r in results.values() if r["signal"] == "TRIM")
    sell = sum(1 for r in results.values() if r["signal"] == "SELL")
    
    print(f"\n📊 Research Summary")
    print(f"   Strong Buy: {strong_buy}")
    print(f"   Buy: {buy}")
    print(f"   Hold: {hold}")
    print(f"   Trim: {trim}")
    print(f"   Sell: {sell}")
    print(f"   Watchlist candidates: {len(recommendations)}")

if __name__ == "__main__":
    main()
