#!/usr/bin/env python3
"""
VOX Supply Chain Agent v2
Monitors: Shipping costs (BDI), commodity prices, port congestion, freight rates
Sources: TradingEconomics (free, no key), Polygon.io (existing key)
Impacts: Retail (AMZN, WMT, TGT), Manufacturing (CAT, DE), Shipping (ZIM, MATX)

v2: Writes to Railway Postgres commodity_prices table
"""

import json, urllib.request, re, os
from pathlib import Path
from datetime import datetime, timezone

# Database config (same as other VOX cron scripts)
DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "railway")

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Portfolio tickers sensitive to supply chain
SUPPLY_SENSITIVE = {
    "AMZN": "retail_shipping", "WMT": "retail_shipping", "TGT": "retail_shipping",
    "COST": "retail_shipping", "HD": "retail_shipping", "LOW": "retail_shipping",
    "CAT": "manufacturing", "DE": "manufacturing", "EMR": "manufacturing",
    "ZIM": "shipping", "MATX": "shipping", "DAC": "shipping",
    "FDX": "logistics", "UPS": "logistics",
    "TSM": "semiconductor_supply", "NVDA": "semiconductor_supply", "AMD": "semiconductor_supply",
    "AAPL": "consumer_electronics", "TSLA": "auto_supply",
    "NKE": "apparel_supply", "LULU": "apparel_supply",
}

# Commodity futures we can track via Polygon (existing key)
POLYGON_COMMODITIES = {
    "CL": {"name": "WTI Crude Oil", "unit": "$/bbl", "category": "energy"},
    "NG": {"name": "Natural Gas", "unit": "$/MMBtu", "category": "energy"},
    "HG": {"name": "Copper", "unit": "¢/lb", "category": "metals"},
    "ALI": {"name": "Aluminum", "unit": "¢/lb", "category": "metals"},
    "ZS": {"name": "Soybeans", "unit": "¢/bushel", "category": "agriculture"},
    "SI": {"name": "Silver", "unit": "$/oz", "category": "metals"},
    "PL": {"name": "Platinum", "unit": "$/oz", "category": "metals"},
    "PA": {"name": "Palladium", "unit": "$/oz", "category": "metals"},
    "ZL": {"name": "Soybean Oil", "unit": "$/lb", "category": "agriculture"},
}

# Equity tickers for supply chain sectors (stock prices, not futures)
POLYGON_EQUITIES = {
    "LIT": {"name": "Global X Lithium ETF", "unit": "$", "category": "batteries", "alerts": True},
    "ALB": {"name": "Albemarle (Lithium)", "unit": "$", "category": "batteries", "alerts": True},
    "SQM": {"name": "SQM (Lithium)", "unit": "$", "category": "batteries", "alerts": True},
    "LAC": {"name": "Lithium Americas", "unit": "$", "category": "batteries", "alerts": False},
    "MT": {"name": "ArcelorMittal (Steel)", "unit": "$", "category": "steel", "alerts": True},
    "NUE": {"name": "Nucor (Steel)", "unit": "$", "category": "steel", "alerts": True},
    "STLD": {"name": "Steel Dynamics", "unit": "$", "category": "steel", "alerts": False},
    "WOOD": {"name": "iShares Global Timber", "unit": "$", "category": "lumber", "alerts": True},
    "WY": {"name": "Weyerhaeuser (Lumber/REIT)", "unit": "$", "category": "lumber", "alerts": True},
    "CCJ": {"name": "Cameco (Uranium)", "unit": "$", "category": "energy", "alerts": True},
    "URA": {"name": "Global X Uranium ETF", "unit": "$", "category": "energy", "alerts": True},
}

# TradingEconomics commodities (free, no key needed)
TE_COMMODITIES = {
    "baltic": {"name": "Baltic Dry Index", "unit": "pts"},
    "wheat": {"name": "Wheat", "unit": "¢/bushel"},
    "corn": {"name": "Corn", "unit": "¢/bushel"},
    "cotton": {"name": "Cotton", "unit": "¢/lb"},
    "coffee": {"name": "Coffee", "unit": "¢/lb"},
    "cocoa": {"name": "Cocoa", "unit": "$/ton"},
}

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

def fetch_polygon(ticker):
    """Fetch from Polygon.io (existing key)."""
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return None
    url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev?apiKey={api_key}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("results"):
                r = data["results"][0]
                return {
                    "price": r.get("c", 0),
                    "open": r.get("o", 0),
                    "change_pct": ((r.get("c", 0) - r.get("o", 0)) / r.get("o", 1)) * 100 if r.get("o") else 0,
                    "volume": r.get("v", 0)
                }
    except:
        pass
    return None

def fetch_tradingeconomics(commodity):
    """Scrape current price from TradingEconomics (free, no key)."""
    url = f"https://tradingeconomics.com/commodity/{commodity}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            text = resp.read().decode('utf-8', errors='ignore')
            
            price_match = re.search(r'(?:fell to|traded at|reached|at)\s+([\d,]+\.?\d*)\s+USD', text)
            if price_match:
                price = float(price_match.group(1).replace(',', ''))
                return {"price": price, "source": "tradingeconomics"}
            
            price_match2 = re.search(r'"price":\s*"?([\d,]+\.?\d*)"?', text)
            if price_match2:
                price = float(price_match2.group(1).replace(',', ''))
                return {"price": price, "source": "tradingeconomics"}
            
            return None
    except:
        return None

def get_db():
    """Get database connection using same pattern as other VOX scripts."""
    if DATABASE_URL:
        import psycopg2
        return psycopg2.connect(DATABASE_URL)
    if DB_PASSWORD:
        import psycopg2
        return psycopg2.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER,
            password=DB_PASSWORD, dbname=DB_NAME, sslmode="require"
        )
    return None

def save_to_postgres(commodities, alerts):
    """Save commodity prices to Railway Postgres."""
    conn = get_db()
    if not conn:
        print("[Supply Chain] No DB credentials available")
        return False
    
    try:
        cur = conn.cursor()
        
        # Ensure table exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS commodity_prices (
                id SERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT,
                price NUMERIC,
                change_pct NUMERIC,
                unit TEXT,
                category TEXT,
                source TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Insert current prices
        for symbol, data in commodities.items():
            cur.execute("""
                INSERT INTO commodity_prices (symbol, name, price, change_pct, unit, category, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol,
                data.get("name", ""),
                data.get("price"),
                data.get("change_pct", 0),
                data.get("unit", ""),
                data.get("category", ""),
                data.get("source", "polygon")
            ))
        
        # Clean old data (keep last 30 days) - only if created_at column exists
        try:
            cur.execute("""
                DELETE FROM commodity_prices 
                WHERE created_at < NOW() - INTERVAL '30 days'
            """)
        except Exception as e:
            print(f"[Supply Chain] Note: Could not clean old data: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"[Supply Chain] Saved {len(commodities)} prices to Postgres")
        return True
    except Exception as e:
        print(f"[Supply Chain] Postgres save failed: {e}")
        return False

def analyze_supply_chain():
    """Analyze supply chain indicators."""
    results = {}
    alerts = []
    
    # Fetch Polygon commodities
    for ticker, info in POLYGON_COMMODITIES.items():
        data = fetch_polygon(ticker)
        if data:
            results[ticker] = {
                **info,
                **data,
                "source": "polygon"
            }
            if abs(data["change_pct"]) >= 3:
                alerts.append({
                    "type": "COMMODITY_MOVE",
                    "ticker": ticker,
                    "name": info["name"],
                    "change_pct": data["change_pct"],
                    "price": data["price"],
                    "message": f"{info['name']} moved {data['change_pct']:+.1f}%",
                    "priority": "HIGH" if abs(data["change_pct"]) >= 5 else "MEDIUM"
                })
    
    # Fetch Polygon equities (supply chain stocks/ETFs)
    for ticker, info in POLYGON_EQUITIES.items():
        if not info.get("alerts"):
            continue
        data = fetch_polygon(ticker)
        if data:
            results[ticker] = {
                **info,
                **data,
                "source": "polygon"
            }
            if abs(data["change_pct"]) >= 5:
                alerts.append({
                    "type": "SUPPLY_EQUITY_MOVE",
                    "ticker": ticker,
                    "name": info["name"],
                    "change_pct": data["change_pct"],
                    "price": data["price"],
                    "message": f"{info['name']} ({ticker}) moved {data['change_pct']:+.1f}% — supply chain signal",
                    "priority": "HIGH" if abs(data["change_pct"]) >= 8 else "MEDIUM"
                })
    
    # Fetch TradingEconomics commodities
    for slug, info in TE_COMMODITIES.items():
        data = fetch_tradingeconomics(slug)
        if data:
            results[slug] = {
                **info,
                **data
            }
    
    # BDI specific alert logic
    bdi = results.get("baltic", {})
    if bdi and bdi.get("price"):
        price = bdi["price"]
        if price > 4000:
            alerts.append({
                "type": "SHIPPING_COST",
                "name": "Baltic Dry Index",
                "price": price,
                "message": "Shipping costs elevated — pressure on retail margins",
                "priority": "HIGH"
            })
        elif price < 1000:
            alerts.append({
                "type": "SHIPPING_COST",
                "name": "Baltic Dry Index",
                "price": price,
                "message": "Shipping costs low — potential demand weakness",
                "priority": "MEDIUM"
            })
    
    # Oil price alert
    oil = results.get("CL", {})
    if oil and oil.get("price"):
        if oil["price"] > 100:
            alerts.append({
                "type": "ENERGY_COST",
                "name": "WTI Crude Oil",
                "price": oil["price"],
                "message": "Oil above $100 — inflation risk, transport cost pressure",
                "priority": "HIGH"
            })
        elif oil["price"] < 60:
            alerts.append({
                "type": "ENERGY_COST",
                "name": "WTI Crude Oil",
                "price": oil["price"],
                "message": "Oil below $60 — potential demand weakness signal",
                "priority": "MEDIUM"
            })
    
    # Save to Postgres
    pg_success = save_to_postgres(results, alerts)
    
    # Save to JSON (always)
    output = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "commodities": results,
        "alerts": alerts,
        "affected_tickers": list(SUPPLY_SENSITIVE.keys()),
        "postgres_sync": pg_success
    }
    
    with open(SCRIPT_DIR / "vox_supply_chain.json", 'w') as f:
        json.dump(output, f, indent=2)
    
    # Only print if there are alerts
    if alerts:
        critical = [a for a in alerts if a["priority"] == "HIGH"]
        medium = [a for a in alerts if a["priority"] == "MEDIUM"]
        
        if critical:
            print(f"🔗 SUPPLY CHAIN ALERT — {len(critical)} critical")
            for a in critical:
                emoji = "🛢️" if "Oil" in a.get("name", "") else "🚢" if "BDI" in a.get("name", "") else "📦"
                print(f"   {emoji} {a['name']}: {a.get('price', 'N/A')} ({a.get('change_pct', 0):+.1f}%)")
                print(f"      {a['message']}")
        
        if medium and not critical:
            print(f"🔗 SUPPLY CHAIN — {len(medium)} watch items")
            for a in medium[:2]:
                print(f"   📦 {a['name']}: {a.get('price', 'N/A')} — {a['message'][:60]}")
    
    return output

if __name__ == "__main__":
    analyze_supply_chain()
