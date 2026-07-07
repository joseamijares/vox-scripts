#!/usr/bin/env python3
"""
VOX Market News Brief v1.0

Pulls market-moving news headlines from free RSS/HTTP sources and uses a cheap
OpenRouter model (deepseek/deepseek-v4-flash or gemini-3.1-flash-lite) to answer:
- Why is the market up/down today?
- What are the top stock and crypto news items?
- Any Trump/policy news moving markets?

Runs cheaply twice daily: 8:00 AM CT (premarket open) and 5:00 PM CT (post-close wrap).
Cost target: < $0.05 per run.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import re
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from html import unescape
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parent))
import vox_utils as vu

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
FALLBACK_MODEL = "google/gemini-3.1-flash-lite"

NEWS_SOURCES = {
    "Yahoo Finance": "https://www.yahoo.com/news/rss",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Investing.com": "https://www.investing.com/rss/news.rss",
    "CryptoCompare": "https://www.cryptocompare.com/api/data/news/?lang=EN",
    "CoinDesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "Reuters": "https://www.reutersagency.com/feed/?best-topics=business-news",
}


def fetch_rss(url: str, max_items: int = 10) -> list:
    """Fetch and parse RSS feed into list of {title, link, published}."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item"):
            title = item.findtext("title", default="")
            link = item.findtext("link", default="")
            pub = item.findtext("pubDate", default="")
            if title:
                items.append({"title": unescape(title).strip(), "link": link, "published": pub})
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        return []


def fetch_cryptocompare(max_items: int = 10) -> list:
    """Fetch CryptoCompare news API."""
    try:
        r = requests.get(NEWS_SOURCES["CryptoCompare"], timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        items = []
        for article in data.get("Data", [])[:max_items]:
            title = article.get("title", "")
            url = article.get("url", "")
            published = article.get("published_on", "")
            if title:
                items.append({"title": unescape(title).strip(), "link": url, "published": str(published)})
        return items
    except Exception:
        return []


def gather_headlines() -> dict:
    """Gather headlines from all sources."""
    headlines = {}
    for name, url in NEWS_SOURCES.items():
        if name == "CryptoCompare":
            headlines[name] = fetch_cryptocompare(max_items=10)
        else:
            headlines[name] = fetch_rss(url, max_items=10)
    return headlines


def dedupe_and_rank(headlines: dict) -> list:
    """Deduplicate and rank top stories by source diversity."""
    seen = set()
    ranked = []
    for source, items in headlines.items():
        for item in items:
            key = item["title"].lower().strip()
            if key in seen or len(key) < 15:
                continue
            seen.add(key)
            item["source"] = source
            ranked.append(item)
    # Sort by relevance heuristic: prefer stories with market/trump/crypto keywords
    def score(item):
        t = item["title"].lower()
        keywords = ["trump", "market", "stock", "crypto", "bitcoin", "ethereum", "fed", "tariff", "trade", "earnings", "nvidia", "ai", "semiconductor"]
        return sum(1 for kw in keywords if kw in t)
    ranked.sort(key=score, reverse=True)
    return ranked[:30]


def fetch_market_snapshot() -> dict:
    """Fetch basic SPY, QQQ, BTC, ETH snapshot from yfinance."""
    try:
        import yfinance as yf
        snapshot = {}
        for ticker in ["SPY", "QQQ", "BTC-USD", "ETH-USD"]:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="5d")
            if not hist.empty and len(hist) >= 2:
                last = hist["Close"].iloc[-1]
                prev = hist["Close"].iloc[-2]
                change = (last - prev) / prev * 100
                snapshot[ticker] = {"price": round(last, 2), "change_pct": round(change, 2)}
            else:
                snapshot[ticker] = {"price": None, "change_pct": None}
        return snapshot
    except Exception as e:
        return {"error": str(e)}


def build_prompt(headlines: list, market_snapshot: dict) -> str:
    headline_text = "\n".join([f"- {h['title']} ({h['source']})" for h in headlines[:25]])
    market_text = json.dumps(market_snapshot, indent=2)

    return f"""You are a sharp market-news analyst writing an aggressive-growth investor brief.

MARKET SNAPSHOT:
{market_text}

TOP HEADLINES (ranked by relevance):
{headline_text}

INSTRUCTIONS:
- Write 5 bullet points.
- Point 1: Explain why the market is up or down today (SPY/QQQ) in one sentence.
- Point 2: Top 2-3 stock-specific news items and their likely impact.
- Point 3: Top 2 crypto news items and likely impact.
- Point 4: Any Trump / policy / tariff / Fed news that could move markets.
- Point 5: One actionable takeaway for an aggressive growth investor.
- Keep it under 250 words. No fluff. No AI-sounding filler.
- Be direct: say what is happening and why it matters.
"""


def summarize(prompt: str, model: str) -> dict:
    return vu.call_openrouter(
        system_prompt="You are a sharp market-news analyst writing an aggressive-growth investor brief.",
        user_prompt=prompt,
        model=model,
        max_tokens=700,
        temperature=0.6,
        script_name="vox_market_news_brief.py",
        notes=f"Market news brief using {model}",
    )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    print("🌐 VOX Market News Brief")
    print(f"Model: {args.model}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}")
    print("\n=== GATHERING HEADLINES ===")

    headlines = gather_headlines()
    ranked = dedupe_and_rank(headlines)
    market_snapshot = fetch_market_snapshot()

    print(f"Total unique headlines: {len(ranked)}")
    for source, items in headlines.items():
        print(f"  {source}: {len(items)} items")

    if not ranked:
        print("\nNo headlines fetched. Skipping LLM call.")
        return 0

    prompt = build_prompt(ranked, market_snapshot)
    est_input = len(prompt) // 4
    est_output = 180
    print(f"\nEstimated tokens: {est_input} in / {est_output} out")

    if not args.run:
        print("\nDry-run. Add --run to call OpenRouter.")
        print("\n=== PROMPT PREVIEW ===")
        print(prompt[:1500])
        print("\n...")
        return 0

    try:
        result = summarize(prompt, args.model)
    except Exception as e:
        print(f"ERROR with {args.model}: {e}")
        print(f"Trying fallback {FALLBACK_MODEL}...")
        result = summarize(prompt, FALLBACK_MODEL)

    print("\n=== MARKET NEWS BRIEF ===")
    print(result["content"])
    print(f"\nCost: ${result['cost_usd']:.4f} | Tokens: {result['total_tokens']}")

    out_dir = Path.home() / "Documents" / "Obsidian" / "VOX" / "NewsBriefs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"NewsBrief-{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    out_path.write_text(result["content"])
    print(f"Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
