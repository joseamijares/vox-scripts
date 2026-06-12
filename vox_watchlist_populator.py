#!/usr/bin/env python3
"""
VOX Watchlist Populator
Populates watchlist with high-conviction tickers across all sectors
Uses: technical grades, sector rotation, momentum, analyst ratings
"""

import json
from datetime import datetime, timezone
from vox_supabase_sync import get_client

# High-conviction watchlist by sector
WATCHLIST_UNIVERSE = [
    # AI / Semiconductor
    {"ticker": "AVGO", "name": "Broadcom", "sector": "Technology", "thesis": "AI chip leader, VMware integration, dividend aristocrat"},
    {"ticker": "MRVL", "name": "Marvell Technology", "sector": "Technology", "thesis": "AI custom silicon, data center growth, 800G networking"},
    {"ticker": "COHR", "name": "Coherent", "sector": "Technology", "thesis": "AI photonics, laser systems, beaten down recovery play"},
    {"ticker": "LRCX", "name": "Lam Research", "sector": "Technology", "thesis": "Semiconductor equipment, etch dominance, AI capex cycle"},
    
    # Nuclear / Clean Energy
    {"ticker": "OKLO", "name": "Oklo", "sector": "Energy", "thesis": "SMR nuclear pioneer, DOE contracts, AI power demand"},
    {"ticker": "BWXT", "name": "BWX Technologies", "sector": "Energy", "thesis": "Naval nuclear reactors, medical isotopes, government backlog"},
    {"ticker": "SMR", "name": "NuScale Power", "sector": "Energy", "thesis": "SMR technology, first-mover advantage, regulatory progress"},
    
    # Space / Defense
    {"ticker": "RKLB", "name": "Rocket Lab", "sector": "Industrials", "thesis": "Space launch cadence, Neutron rocket, satellite manufacturing"},
    {"ticker": "ASTS", "name": "AST SpaceMobile", "sector": "Technology", "thesis": "Satellite-to-cell, AT&T partnership, global coverage"},
    {"ticker": "PLTR", "name": "Palantir", "sector": "Technology", "thesis": "AI defense contracts, AIP platform, government sticky"},
    
    # Biotech / Pharma
    {"ticker": "VKTX", "name": "Viking Therapeutics", "sector": "Healthcare", "thesis": "GLP-1/GIP dual agonist, obesity market, Phase 2 data"},
    {"ticker": "LLY", "name": "Eli Lilly", "sector": "Healthcare", "thesis": "GLP-1 leader, Mounjaro/Zepbound, manufacturing scale"},
    {"ticker": "NVO", "name": "Novo Nordisk", "sector": "Healthcare", "thesis": "Wegovy/Ozempic, obesity megatrend, European pharma"},
    {"ticker": "EXAS", "name": "Exact Sciences", "sector": "Healthcare", "thesis": "Cologuard screening, multi-cancer blood test, Medicare coverage"},
    
    # Fintech / Payments
    {"ticker": "SOFI", "name": "SoFi Technologies", "sector": "Financials", "thesis": "Digital banking, student loans, Galileo platform, profitability"},
    {"ticker": "HOOD", "name": "Robinhood", "sector": "Financials", "thesis": "Gold subscription, credit card, UK expansion, crypto trading"},
    {"ticker": "NU", "name": "Nu Holdings", "sector": "Financials", "thesis": "Latin American digital bank, Nubank growth, Brazil exposure"},
    
    # Crypto / Blockchain
    {"ticker": "COIN", "name": "Coinbase", "sector": "Financials", "thesis": "Crypto exchange leader, Base L2, institutional custody"},
    {"ticker": "MSTR", "name": "MicroStrategy", "sector": "Technology", "thesis": "Bitcoin treasury play, leveraged BTC exposure, software cash flow"},
    {"ticker": "RIOT", "name": "Riot Platforms", "sector": "Technology", "thesis": "Bitcoin mining, power strategy, hash rate growth"},
    
    # EV / Mobility
    {"ticker": "TSLA", "name": "Tesla", "sector": "Consumer Discretionary", "thesis": "Robotaxi event, FSD v12, energy storage, Optimus robot"},
    {"ticker": "RIVN", "name": "Rivian", "sector": "Consumer Discretionary", "thesis": "EV delivery vans, VW partnership, cost reduction"},
    
    # Cybersecurity
    {"ticker": "CRWD", "name": "CrowdStrike", "sector": "Technology", "thesis": "Endpoint security, Falcon platform, AI threat detection"},
    {"ticker": "PANW", "name": "Palo Alto Networks", "sector": "Technology", "thesis": "Platformization strategy, SASE leader, AI security"},
    {"ticker": "NET", "name": "Cloudflare", "sector": "Technology", "thesis": "Edge computing, AI inference, Workers platform, cybersecurity"},
    
    # Cloud / SaaS
    {"ticker": "SNOW", "name": "Snowflake", "sector": "Technology", "thesis": "Data cloud, AI workloads, Cortex AI, consumption model"},
    {"ticker": "DDOG", "name": "Datadog", "sector": "Technology", "thesis": "Observability platform, AI monitoring, cloud-native"},
    {"ticker": "MDB", "name": "MongoDB", "sector": "Technology", "thesis": "Document database, Atlas cloud, AI vector search"},
    
    # Consumer / Retail
    {"ticker": "AMZN", "name": "Amazon", "sector": "Consumer Discretionary", "thesis": "AWS AI, Prime growth, advertising, logistics moat"},
    {"ticker": "COST", "name": "Costco", "sector": "Consumer Staples", "thesis": "Membership model, inflation hedge, international expansion"},
    {"ticker": "LULU", "name": "Lululemon", "sector": "Consumer Discretionary", "thesis": "Athleisure brand, Mirror write-down recovery, China growth"},
    
    # Industrials / Manufacturing
    {"ticker": "GE", "name": "GE Aerospace", "sector": "Industrials", "thesis": "Aerospace aftermarket, LEAP engine, spin-off pure-play"},
    {"ticker": "RTX", "name": "RTX Corporation", "sector": "Industrials", "thesis": "Defense spending, Pratt engines, missile systems"},
    {"ticker": "NUE", "name": "Nucor", "sector": "Materials", "thesis": "Steel mini-mills, infrastructure bill, reshoring"},
    
    # Commodities / Materials
    {"ticker": "FCX", "name": "Freeport-McMoRan", "sector": "Materials", "thesis": "Copper demand, EV electrification, supply deficit"},
    {"ticker": "ALB", "name": "Albemarle", "sector": "Materials", "thesis": "Lithium producer, EV battery demand, oversold recovery"},
    {"ticker": "URNM", "name": "Sprott Uranium Miners ETF", "sector": "Materials", "thesis": "Nuclear renaissance, uranium supply squeeze, SMR demand"},
    
    # REITs / Real Estate
    {"ticker": "DLR", "name": "Digital Realty", "sector": "Real Estate", "thesis": "Data center REIT, AI cloud demand, interconnection"},
    {"ticker": "AMT", "name": "American Tower", "sector": "Real Estate", "thesis": "Cell tower REIT, 5G rollout, international towers"},
    
    # International / Emerging
    {"ticker": "BABA", "name": "Alibaba", "sector": "Consumer Discretionary", "thesis": "China e-commerce, cloud division, undervalued vs US peers"},
    {"ticker": "PDD", "name": "PDD Holdings", "sector": "Consumer Discretionary", "thesis": "Temu growth, discount e-commerce, China consumption"},
    {"ticker": "TSM", "name": "Taiwan Semiconductor", "sector": "Technology", "thesis": "Foundry monopoly, AI chip demand, 3nm process"},
]

def populate_watchlist():
    sb = get_client()
    
    print("🎯 VOX Watchlist Populator")
    print(f"Adding {len(WATCHLIST_UNIVERSE)} tickers across sectors...")
    print("=" * 60)
    
    added = 0
    skipped = 0
    
    for item in WATCHLIST_UNIVERSE:
        try:
            # Check if already exists
            existing = sb.table('watchlist').select('ticker').eq('ticker', item['ticker']).execute()
            if existing.data:
                print(f"  ⏭️  {item['ticker']:6s} already exists")
                skipped += 1
                continue
            
            # Insert
            record = {
                "ticker": item["ticker"],
                "name": item["name"],
                "sector": item["sector"],
                "thesis": item["thesis"],
                "status": "watching",
                "grade": None,
                "council": None,
                "entry_price": None,
                "target_price": None,
                "stop_loss": None,
                "added_at": datetime.now(timezone.utc).isoformat()
            }
            
            sb.table('watchlist').insert(record).execute()
            print(f"  ✅ {item['ticker']:6s} | {item['sector']:25s} | {item['name']}")
            added += 1
            
        except Exception as e:
            print(f"  ❌ {item['ticker']:6s} | ERROR: {e}")
    
    print("=" * 60)
    print(f"Added: {added} | Skipped: {skipped} | Total: {added + skipped}")
    
    # Show sector breakdown
    result = sb.table('watchlist').select('*').execute()
    sectors = {}
    for w in result.data:
        s = w.get('sector', 'Unknown')
        sectors[s] = sectors.get(s, 0) + 1
    
    print(f"\n📊 Sector Breakdown:")
    for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
        print(f"   {sector:30s} | {count:2d} tickers")

if __name__ == "__main__":
    populate_watchlist()
