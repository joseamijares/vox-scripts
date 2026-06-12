#!/usr/bin/env python3
"""
VOX Universe Expansion
Expands coverage beyond current 141 positions to include:
- Top 500 US stocks
- Major crypto (BTC, ETH, SOL, etc.)
- International markets (EU, Asia, LatAm)
- Commodities (gold, oil, copper)

Generates: universe.json with all trackable tickers
"""

import json
from pathlib import Path

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

# Expanded universe
UNIVERSE = {
    "us_large_cap": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
        "UNH", "JPM", "V", "JNJ", "WMT", "PG", "MA", "HD", "CVX", "MRK",
        "LLY", "PEP", "KO", "ABBV", "BAC", "AVGO", "PFE", "COST", "TMO",
        "DIS", "ABT", "ACN", "WFC", "DHR", "VZ", "NKE", "TXN", "NEE",
        "BMY", "QCOM", "RTX", "HON", "PM", "UPS", "LOW", "ORCL", "UNP",
        "IBM", "INTC", "GS", "CAT", "ELV", "SPGI", "MDT", "BKNG", "LMT",
        "T", "DE", "GILD", "AMGN", "SBUX", "ADI", "PLD", "MS", "BLK",
        "MDLZ", "SYK", "TJX", "C", "AMAT", "ADP", "MMC", "CVS", "TMUS",
        "DUK", "SO", "CI", "MO", "REGN", "PGR", "BSX", "SLB", "ZTS",
        "FI", "AON", "ETN", "COP", "EOG", "PSX", "MPC", "VLO", "OXY",
        "DVN", "FANG", "MRO", "PXD", "CLR", "HES", "MUR", "RRC", "SWN",
        "EQT", "CTRA", "CNX", "GPOR", "MTDR", "PE", "WPX", "XEC", "NBL"
    ],
    "us_mid_cap": [
        "SNOW", "ZM", "ROKU", "SQ", "SHOP", "CRWD", "OKTA", "DDOG",
        "NET", "FSLY", "TWLO", "PLTR", "RBLX", "U", "DOCN", "ASAN",
        "MDB", "ESTC", "SPLK", "NOW", "VEEV", "TDOC", "TELEDOC",
        "Z", "OPEN", "RDFN", "COMP", "MTTR", "EXPI", "LE", "WSM"
    ],
    "crypto": [
        "BTC", "ETH", "SOL", "ADA", "DOT", "AVAX", "MATIC", "LINK",
        "UNI", "AAVE", "MKR", "COMP", "YFI", "SNX", "CRV", "SUSHI",
        "1INCH", "DYDX", "GRT", "RNDR", "FIL", "AR", "STORJ", "HNT",
        "XRP", "LTC", "BCH", "XLM", "ALGO", "VET", "TRX", "ETC",
        "XTZ", "EOS", "ATOM", "NEAR", "FTM", "ONE", "ICP", "FLOW"
    ],
    "international": [
        "TSM", "ASML", "SAP", "SONY", "NTES", "BABA", "JD", "PDD",
        "BIDU", "TCEHY", "MELI", "SE", "NU", "GLOB", "STNE", "PAGS",
        "DLO", "FOX", "DESP", "GOL", "AZUL", "CPA", "AVH", "VLRS",
        "TM", "HMC", "NSANY", "HYMTF", "VWAGY", "BMWYY", "DDAIF",
        "SAN", "BBVA", "ING", "DB", "UBS", "CS", "HSBC", "BCS"
    ],
    "commodities": [
        "GLD", "SLV", "USO", "UNG", "DBA", "DBB", "DBC", "GSG",
        "PALL", "PLTM", "COPX", "LIT", "URA", "NLR", "WOOD", "MOO"
    ],
    "thematic": [
        "ARKK", "ARKQ", "ARKW", "ARKG", "ARKF", "ARKX",
        "BOTZ", "ROBT", "AIQ", "CHAT", "IRBO", "ROBO",
        "SMH", "SOXX", "XSD", "PSI", "FTXL",
        "ICLN", "PBW", "QCLN", "PBD", "ACES",
        "XBI", "IBB", "ARKG", "LABU", "PPH"
    ]
}

def expand_universe():
    """Generate expanded universe file."""
    print("🌌 VOX Universe Expansion")
    print("=" * 50)
    
    all_tickers = []
    for category, tickers in UNIVERSE.items():
        print(f"   {category}: {len(tickers)} tickers")
        all_tickers.extend(tickers)
    
    # Remove duplicates
    unique_tickers = list(set(all_tickers))
    
    universe_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_tickers": len(unique_tickers),
        "categories": {k: len(v) for k, v in UNIVERSE.items()},
        "tickers": unique_tickers,
        "by_category": UNIVERSE
    }
    
    output_file = SCRIPT_DIR / "vox_universe.json"
    with open(output_file, 'w') as f:
        json.dump(universe_data, f, indent=2)
    
    print(f"\n✅ Universe expanded: {len(unique_tickers)} total tickers")
    print(f"   US Large Cap: {len(UNIVERSE['us_large_cap'])}")
    print(f"   US Mid Cap: {len(UNIVERSE['us_mid_cap'])}")
    print(f"   Crypto: {len(UNIVERSE['crypto'])}")
    print(f"   International: {len(UNIVERSE['international'])}")
    print(f"   Commodities: {len(UNIVERSE['commodities'])}")
    print(f"   Thematic ETFs: {len(UNIVERSE['thematic'])}")
    print(f"\n💾 Saved to {output_file}")
    
    return universe_data

if __name__ == "__main__":
    from datetime import datetime, timezone
    expand_universe()
