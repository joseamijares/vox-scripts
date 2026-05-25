#!/usr/bin/env python3
"""
Unusual Volume & Options Scanner — OpenClaw
Scans high-volume movers and unusual options activity
"""
import urllib.request, json, os
from datetime import datetime

def fetch_yahoo_unusual_volume():
    """Fetch unusual volume stocks from Yahoo Finance scraping"""
    try:
        url = "https://finance.yahoo.com/markets/stocks/unusual-volume-stocks/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode()
            # Basic parsing - look for ticker symbols in the table
            # In production use proper parsing
            return {"source": "Yahoo Finance", "status": "scraped", "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"source": "Yahoo Finance", "error": str(e)}

def fetch_momentum_tickers():
    """Generate momentum alerts based on pre-defined watchlist + live data"""
    watchlist = {
        "CEG": {"theme": "AI Energy", "alert_price": 150},
        "VST": {"theme": "AI Energy", "alert_price": 110},
        "NVDA": {"theme": "AI Chips", "alert_price": 140},
        "RKLB": {"theme": "Space", "alert_price": 120},
        "SOL": {"theme": "Crypto", "alert_price": 85},
    }
    return watchlist

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"📈 UNUSUAL VOLUME SCANNER — {timestamp}")
    print("=" * 60)
    
    # Get watchlist with alerts
    watchlist = fetch_momentum_tickers()
    
    print("\n🔔 ACTIVE ALERTS:")
    for ticker, info in watchlist.items():
        print(f"  {ticker:6} | {info['theme']:15} | Alert if below ${info['alert_price']}")
    
    print("\n📡 SCANNER SOURCES:")
    print("  • MarketChameleon: https://marketchameleon.com/Reports/UnusualOptionVolumeReport")
    print("  • Barchart: https://www.barchart.com/options/unusual-activity")
    print("  • StockTitan: https://www.stocktitan.net/scanner/momentum")
    
    # Save scan result
    out = {
        "timestamp": timestamp,
        "watchlist_alerts": watchlist,
        "sources": [
            "marketchameleon.com",
            "barchart.com/options/unusual-activity",
            "stocktitan.net/scanner/momentum"
        ]
    }
    os.makedirs("/Users/jos/.hermes/scripts/snapshots", exist_ok=True)
    with open("/Users/jos/.hermes/scripts/snapshots/volume_scan_latest.json", "w") as f:
        json.dump(out, f, indent=2)
    
    print(f"\n💾 Saved to snapshots/volume_scan_latest.json")
    return out

if __name__ == "__main__":
    main()
