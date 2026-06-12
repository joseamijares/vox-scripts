#!/usr/bin/env python3
"""
VOX Discovery Agent v1
Auto-discovers stocks from multiple sources:
- X/Twitter trending mentions
- Reddit ticker extraction
- News headlines
- Sector momentum anomalies (parallel, ~20s for 300 tickers)

Generates: vox_discovered_tickers.json, vox_hypotheses.json, vox_sector_opportunities.json
"""

import json
import urllib.request
import urllib.parse
import re
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

COMMON_WORDS = {'THE', 'AND', 'FOR', 'ARE', 'BUT', 'NOT', 'YOU', 'ALL', 'ANY', 'CAN', 'HAD', 'HER', 'WAS', 'ONE', 'OUR', 'OUT', 'DAY', 'GET', 'HAS', 'HIM', 'HIS', 'HOW', 'MAN', 'NEW', 'NOW', 'OLD', 'SEE', 'TWO', 'WAY', 'WHO', 'BOY', 'DID', 'ITS', 'LET', 'PUT', 'SAY', 'SHE', 'TOO', 'USE', 'DOW', 'NASDAQ', 'NYSE', 'ETF', 'IPO', 'CEO', 'CFO', 'COO', 'USA', 'GDP', 'CPI', 'FED', 'IRS', 'SEC', 'AI', 'ML', 'API', 'GPU', 'CPU', 'RAM', 'SSD', 'SPAC', 'NAV', 'AUM', 'EPS', 'EV', 'EBITDA'}

SECTOR_UNIVERSE = {
    "energy": {
        "majors": ["XOM", "CVX", "COP", "EOG", "MPC", "VLO", "PSX", "OXY", "DVN", "FANG", "MRO", "PXD"],
        "renewables": ["NEE", "ENPH", "SEDG", "FSLR", "RUN", "SPWR", "CSIQ", "JKS", "DQ", "MAXN", "ARRY", "SHLS"],
        "nuclear": ["CCJ", "URA", "SMR", "OKLO", "BWXT", "LEU", "NLR", "NNE"],
        "clean_tech": ["PLUG", "BE", "BLDP", "FCEL", "ICLN", "PBW", "QCLN", "ACES"],
        "oil_services": ["SLB", "HAL", "BKR", "NOV", "FTI", "HP", "PTEN", "NBR"],
        "midstream": ["ET", "MPLX", "WMB", "KMI", "EPD", "ENB", "TRP", "OKE"],
        "lng": ["LNG", "TELL", "GLNG", "FLNG", "GMLP"],
    },
    "ai_supply_chain": {
        "hyperscalers": ["NVDA", "AMD", "AVGO", "MRVL", "QCOM", "INTC", "ARM"],
        "datacenters": ["DELL", "SMCI", "HPE", "STX", "WDC", "NTAP", "PSTG", "SNOW", "PLTR"],
        "power": ["VST", "CEG", "NRG", "AEP", "SO", "D", "EXC", "XEL", "PEG", "ED"],
        "cooling": ["VRT", "MOD", "AQUA", "CWST"],
        "networking": ["ANET", "CSCO", "JNPR", "FFIV", "CIEN", "LITE", "NOK", "INFN"],
        "memory": ["MU", "HMC", "SKHYNIX"],
        "miners_turned_ai": ["IREN", "CORZ", "WULF", "BTDR", "CLSK", "HIVE", "RIOT", "MARA", "APLD", "TE", "CRWV", "KEEL", "SHAZ", "SNDK"],
    },
    "big_tech": {
        "magnificent_7": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
        "semis": ["TSM", "ASML", "AVGO", "QCOM", "TXN", "ADI", "KLAC", "LRCX", "AMAT", "MCHP", "NXPI", "ON"],
        "software": ["CRM", "NOW", "ADBE", "INTU", "PANW", "CRWD", "NET", "DDOG", "SNOW", "PLTR", "U", "DOCN", "HCP"],
        "cloud": ["AMZN", "MSFT", "GOOGL", "ORCL", "IBM", "SNOW", "NET", "CFLT", "MDB"],
    },
    "futuristic": {
        "quantum": ["IONQ", "RGTI", "QBTS", "QUBT", "INFQ", "ARQQ", "LAES", "IBM", "GOOGL", "MSFT", "AMZN", "NVDA", "INTC", "HON", "BAH"],
        "space": ["RKLB", "RDW", "LUNR", "ASTS", "PL", "SPIR", "BKSY", "VOYG", "FLY", "MNTS", "SIDU", "IRDM", "GSAT", "VSAT", "TSAT", "SATS", "HON", "HWM", "ATI", "CPSH", "VLD", "DDD", "UFO", "NASA"],
        "robotics": ["ISRG", "SYK", "ZBH", "RHHVF", "TRMB", "TER", "CGNX", "ROBO", "BOTZ", "KARS"],
        "autonomous": ["TSLA", "GOOGL", "AMZN", "AUR", "MBLY", "LAZR", "MVIS", "AEYE"],
        "biotech_revolution": ["CRSP", "EDIT", "NTLA", "BEAM", "VRTX", "LLY", "NVO", "REGN", "GILD", "BIIB", "MRNA", "BNTX", "ARCT", "DNA", "TWST"],
    },
    "defense_geopolitical": {
        "prime": ["LMT", "RTX", "NOC", "GD", "BA", "LHX", "TDG", "HII", "KTOS", "BWXT"],
        "drone": ["AVAV", "KRAT", "EH", "UAVS", "DPRO"],
        "cyber": ["CRWD", "PANW", "FTNT", "CYBR", "S", "OKTA", "ZS", "GEN", "RDWR"],
        "space_defense": ["RKLB", "RDW", "LUNR", "ASTS", "SPIR", "BKSY", "PL"],
    },
    "emerging_markets": {
        "china_tech": ["BABA", "JD", "PDD", "NTES", "BIDU", "TCEHY", "MELI", "SE", "GRAB", "DASH"],
        "india": ["INFY", "WIT", "HDB", "IBN", "MMYT"],
        "frontier": ["EWZ", "EWW", "EWC", "EWY", "EWG", "EWQ", "EWP", "EWN", "EWI", "EWD"],
    },
    "commodities_materials": {
        "gold": ["GLD", "GDX", "GDXJ", "NEM", "GOLD", "AEM", "WPM", "FNV", "RGLD", "KGC"],
        "silver": ["SLV", "SIL", "PAAS", "HL", "EXK", "FSM", "MAG"],
        "copper": ["FCX", "SCCO", "TECK"],
        "lithium": ["ALB", "SQM", "LTHM", "LAC", "PLL", "LIT"],
        "rare_earth": ["MP", "LYSCF", "UURAF", "REEMF"],
        "uranium": ["CCJ", "URA", "UUUU", "DNN", "LEU", "UROY"],
    },
}

ALL_KNOWN_TICKERS = set()
for sector, groups in SECTOR_UNIVERSE.items():
    for group, tickers in groups.items():
        ALL_KNOWN_TICKERS.update(tickers)

# --- HELPERS ---

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

def fetch_polygon(ticker: str) -> dict:
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    url = 'https://api.polygon.io/v2/aggs/ticker/' + ticker + '/prev?apiKey=' + api_key
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}

def extract_tickers_from_text(text: str) -> list:
    tickers = re.findall(r'\$([A-Z]{1,5})', text)
    standalone = re.findall(r'\b([A-Z]{2,5})\b', text)
    standalone = [t for t in standalone if t not in COMMON_WORDS and len(t) >= 2]
    return list(set(tickers + standalone))

# --- DISCOVERY SOURCES ---

def scan_x_for_tickers() -> dict:
    env = load_env()
    bearer = env.get("X_BEARER_TOKEN", "")
    if not bearer:
        return {}
    
    queries = [
        "stock pick OR stock idea OR buy signal OR breakout OR undervalued",
        "AI stock OR quantum stock OR space stock OR energy stock",
        "13F filing OR institutional buying OR hedge fund position",
        "earnings beat OR revenue growth OR guidance raised",
    ]
    
    all_tickers = {}
    
    for query in queries:
        try:
            url = f"https://api.twitter.com/2/tweets/search/recent?query={urllib.parse.quote(query)}&max_results=50&tweet.fields=created_at,public_metrics,author_id"
            headers = {"Authorization": f"Bearer {bearer}"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
                for tweet in data.get("data", []):
                    text = tweet.get("text", "")
                    metrics = tweet.get("public_metrics", {})
                    engagement = metrics.get("like_count", 0) + metrics.get("retweet_count", 0)
                    tickers = extract_tickers_from_text(text)
                    for t in tickers:
                        if t not in COMMON_WORDS and len(t) <= 5:
                            if t not in all_tickers:
                                all_tickers[t] = {"mentions": 0, "engagement": 0, "sources": []}
                            all_tickers[t]["mentions"] += 1
                            all_tickers[t]["engagement"] += engagement
                            if len(all_tickers[t]["sources"]) < 2:
                                all_tickers[t]["sources"].append(text[:100])
        except Exception:
            pass
    
    return all_tickers

def scan_reddit_for_tickers() -> dict:
    subreddits = ["wallstreetbets", "stocks", "investing", "wallstreetbetsOGs", "pennystocks", "SPACs", "SecurityAnalysis"]
    all_tickers = {}
    
    for subreddit in subreddits:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=25"
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
                for post in data.get("data", {}).get("children", []):
                    p = post.get("data", {})
                    text = p.get("title", "") + " " + p.get("selftext", "")[:300]
                    upvotes = p.get("ups", 0)
                    tickers = extract_tickers_from_text(text)
                    for t in tickers:
                        if len(t) <= 5:
                            if t not in all_tickers:
                                all_tickers[t] = {"mentions": 0, "upvotes": 0, "sources": []}
                            all_tickers[t]["mentions"] += 1
                            all_tickers[t]["upvotes"] += upvotes
                            if len(all_tickers[t]["sources"]) < 2:
                                all_tickers[t]["sources"].append(p.get("title", "")[:100])
        except Exception:
            pass
    
    return all_tickers

def scan_news_for_tickers() -> dict:
    rss_feeds = [
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC,%5EIXIC,%5EDJI&region=US&lang=en-US",
    ]
    
    all_tickers = {}
    
    for feed in rss_feeds:
        try:
            req = urllib.request.Request(feed, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read().decode('utf-8', errors='ignore')
                tickers = extract_tickers_from_text(content)
                for t in tickers:
                    if len(t) <= 5:
                        if t not in all_tickers:
                            all_tickers[t] = {"mentions": 0, "sources": []}
                        all_tickers[t]["mentions"] += 1
                        if len(all_tickers[t]["sources"]) < 2:
                            all_tickers[t]["sources"].append("News mention")
        except Exception:
            pass
    
    return all_tickers

# --- SECTOR MOMENTUM (PARALLEL) ---

def analyze_sector_momentum() -> dict:
    """Analyze all known tickers for momentum anomalies — parallel fetch."""
    
    # Flatten all tickers
    all_tickers = []
    for sector, groups in SECTOR_UNIVERSE.items():
        for group, tickers in groups.items():
            all_tickers.extend(tickers)
    all_tickers = list(set(all_tickers))
    
    # Parallel fetch all
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        raw_results = list(executor.map(fetch_polygon, all_tickers))
    
    # Build lookup
    price_data = {}
    for r in raw_results:
        if r.get("results"):
            t = r.get("ticker", "").replace("O:", "").replace("X:", "")
            res = r["results"][0]
            price = res.get("c", 0)
            open_p = res.get("o", 0)
            change_pct = ((price - open_p) / open_p * 100) if open_p else 0
            volume = res.get("v", 0)
            price_data[t] = {"price": price, "change_pct": change_pct, "volume": volume}
    
    # Build sector results
    results = {}
    for sector, groups in SECTOR_UNIVERSE.items():
        for group, tickers in groups.items():
            group_data = []
            for ticker in tickers:
                if ticker in price_data:
                    d = price_data[ticker]
                    group_data.append({
                        "ticker": ticker,
                        "price": d["price"],
                        "change_pct": d["change_pct"],
                        "volume": d["volume"]
                    })
            
            if group_data:
                avg_change = sum(d["change_pct"] for d in group_data) / len(group_data)
                movers = [d for d in group_data if abs(d["change_pct"]) >= 5]
                results[f"{sector}.{group}"] = {
                    "tickers": group_data,
                    "avg_change_pct": round(avg_change, 2),
                    "movers": movers,
                    "mover_count": len(movers)
                }
    
    return results

# --- HYPOTHESIS GENERATION ---

def generate_hypotheses(sector_momentum: dict, discovered: dict) -> list:
    hypotheses = []
    
    for key, data in sector_momentum.items():
        if data["avg_change_pct"] > 3:
            hypotheses.append({
                "type": "sector_momentum",
                "theme": key,
                "hypothesis": f"{key} showing broad strength (+{data['avg_change_pct']:.1f}% avg). Consider basket exposure.",
                "confidence": min(100, 60 + abs(data["avg_change_pct"]) * 5),
                "tickers": [d["ticker"] for d in data["movers"][:5]],
                "action": "BUY_BASKET"
            })
        elif data["avg_change_pct"] < -3:
            hypotheses.append({
                "type": "sector_weakness",
                "theme": key,
                "hypothesis": f"{key} under pressure ({data['avg_change_pct']:.1f}% avg). Potential dip-buy or avoid.",
                "confidence": min(100, 60 + abs(data["avg_change_pct"]) * 5),
                "tickers": [d["ticker"] for d in data["tickers"][:5]],
                "action": "WATCH_DIP"
            })
    
    for key, data in sector_momentum.items():
        for mover in data["movers"]:
            if mover["change_pct"] > 10:
                hypotheses.append({
                    "type": "breakout",
                    "theme": key,
                    "hypothesis": f"${mover['ticker']} breaking out +{mover['change_pct']:.1f}% in {key}. Momentum play.",
                    "confidence": min(100, 70 + mover["change_pct"]),
                    "tickers": [mover["ticker"]],
                    "action": "MOMENTUM_BUY"
                })
    
    for ticker, data in discovered.items():
        if data["mentions"] >= 5 and data.get("engagement", 0) > 50:
            hypotheses.append({
                "type": "social_emerging",
                "theme": "social_discovery",
                "hypothesis": f"${ticker} gaining social traction ({data['mentions']} mentions, {data.get('engagement', 0)} engagement). Early awareness.",
                "confidence": min(100, 50 + data["mentions"] * 3),
                "tickers": [ticker],
                "action": "RESEARCH"
            })
    
    hypotheses.sort(key=lambda x: x["confidence"], reverse=True)
    return hypotheses

# --- MAIN ---

def run_discovery():
    # 1. Scan all sources
    x_tickers = scan_x_for_tickers()
    reddit_tickers = scan_reddit_for_tickers()
    news_tickers = scan_news_for_tickers()
    
    # Merge discoveries
    discovered = {}
    for source, tickers in [("x", x_tickers), ("reddit", reddit_tickers), ("news", news_tickers)]:
        for ticker, data in tickers.items():
            if ticker not in discovered:
                discovered[ticker] = {"mentions": 0, "engagement": 0, "sources": []}
            discovered[ticker]["mentions"] += data.get("mentions", 0)
            discovered[ticker]["engagement"] += data.get("engagement", data.get("upvotes", 0))
            discovered[ticker]["sources"].extend(data.get("sources", [])[:2])
    
    interesting = {t: d for t, d in discovered.items() if d["mentions"] >= 3 and t not in COMMON_WORDS}
    
    # 2. Analyze sector momentum (parallel, ~20s)
    sector_momentum = analyze_sector_momentum()
    
    # 3. Generate hypotheses
    hypotheses = generate_hypotheses(sector_momentum, interesting)
    
    # 4. Find new tickers not in known universe
    new_tickers = {t: d for t, d in interesting.items() if t not in ALL_KNOWN_TICKERS}
    
    # 5. Save outputs
    timestamp = datetime.now(timezone.utc).isoformat()
    
    with open(SCRIPT_DIR / "vox_discovered_tickers.json", 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "total_discovered": len(interesting),
            "new_tickers": len(new_tickers),
            "tickers": dict(interesting)
        }, f, indent=2)
    
    with open(SCRIPT_DIR / "vox_hypotheses.json", 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "hypothesis_count": len(hypotheses),
            "hypotheses": hypotheses[:20]
        }, f, indent=2)
    
    with open(SCRIPT_DIR / "vox_sector_opportunities.json", 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "sectors_analyzed": len(sector_momentum),
            "opportunities": sector_momentum
        }, f, indent=2)
    
    # 6. Print only if actionable
    should_print = len(hypotheses) > 0 or len(new_tickers) > 0
    
    if should_print:
        if new_tickers:
            print(f"🔍 DISCOVERY — {len(new_tickers)} new tickers detected")
            for t, d in list(new_tickers.items())[:5]:
                print(f"   👀 ${t}: {d['mentions']} mentions, {d['engagement']} engagement")
        
        if hypotheses:
            print(f"🧠 HYPOTHESES — {len(hypotheses)} generated")
            for h in hypotheses[:5]:
                emoji = {"BUY_BASKET": "📦", "MOMENTUM_BUY": "🚀", "WATCH_DIP": "👀", "RESEARCH": "🔬"}.get(h["action"], "💡")
                print(f"   {emoji} {h['hypothesis'][:80]}... (conf: {h['confidence']:.0f})")
        
        top_sectors = sorted(sector_momentum.items(), key=lambda x: x[1]["avg_change_pct"], reverse=True)[:3]
        if top_sectors and top_sectors[0][1]["avg_change_pct"] > 2:
            print(f"📊 TOP SECTORS")
            for name, data in top_sectors:
                print(f"   {name}: {data['avg_change_pct']:+.1f}% ({data['mover_count']} movers)")

if __name__ == "__main__":
    run_discovery()
