#!/usr/bin/env python3
"""
VOX Sector Analysis Agent
Monitors: Sector rotation, relative strength, momentum
Generates: Sector rankings and rotation signals
"""

import json
import urllib.request
import concurrent.futures
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

SECTORS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discretionary",
    "XLB": "Materials",
    "XLU": "Utilities",
    "XLRE": "Real Estate",
    "XLV": "Health Care",
    "XLC": "Communication Services"
}

# Space sector watchlist from X posts (SpaceX IPO catalyst)
SPACE_SECTOR = {
    # Direct SpaceX Supply Chain
    "STM": "STMicroelectronics (SpaceX supply chain)",
    "TSLA": "Tesla (SpaceX sister company)",
    "VLD": "Velo3D (additive manufacturing)",
    "RDW": "Redwire Corporation (in-orbit hardware manufacturing)",
    # Launch & Space Infrastructure
    "RKLB": "Rocket Lab USA (launch services — SpaceX comp)",
    "LUNR": "Intuitive Machines (lunar infrastructure)",
    "MDA": "MDA Space (robotics & satellites)",
    "VOYG": "Voyager Technologies (next-gen commercial space station)",
    "FLY": "Firefly Aerospace (launch + lunar/orbital services)",
    "MNTS": "Momentus (in-space transportation)",
    "SIDU": "Sidus Space (satellite-as-a-service)",
    # Satellite Imagery / Earth Observation
    "PL": "Planet Labs (largest commercial Earth imaging)",
    "SATL": "Satellogic (lower-cost imaging constellation)",
    "BKSY": "BlackSky Technology (radar imaging — sees through clouds)",
    "SPIR": "Spire Global (RF data — maritime, aviation, weather)",
    # Satellite Communications
    "ASTS": "AST SpaceMobile (direct-to-phone satellite cellular)",
    "IRDM": "Iridium Communications (satellite comms)",
    "GSAT": "Globalstar (satellite services)",
    "SATS": "EchoStar (satellite broadband)",
    "TSAT": "Telesat (satellite operator)",
    "VSAT": "Viasat (satellite internet)",
    # Aerospace & Defense
    "HON": "Honeywell International (aerospace systems)",
    "HWM": "Howmet Aerospace (engine components)",
    # Materials, Alloys & Advanced Manufacturing
    "ATI": "ATI Inc. (aerospace alloys)",
    "CRS": "Carpenter Technology (specialty alloys)",
    "MTRN": "Materion (advanced materials)",
    "HXL": "Hexcel (composites)",
    "CPSH": "CPS Technologies (AlSiC hermetic packaging — NASA/Space Force)",
    "DDD": "3D Systems (aerospace 3D printing)",
    # Space ETF
    "UFO": "Procure Space ETF (broad space exposure)",
    "NASA": "NASA ETF (space basket incl. SpaceX SPV exposure)",
}

# AI Infrastructure — Leopold Aschenbrenner / Situational Awareness 13F
AI_INFRA_SECTOR = {
    # Core AI infrastructure (ex-Bitcoin miners turned AI)
    "TE": "TecnoGlass (AI infrastructure)",
    "HIVE": "HIVE Digital Technologies (AI compute)",
    "CLSK": "CleanSpark (AI infrastructure)",
    "SHAZ": "Shazam (AI infrastructure)",
    "KEEL": "Keel (AI infrastructure)",
    "SNDK": "SanDisk (AI storage)",
    "IREN": "Iris Energy (AI data centers)",
    "APLD": "Applied Digital (AI infrastructure)",
    "BTDR": "Bitdeer (AI compute)",
    "CRWV": "Caraway (AI infrastructure)",
    "RIOT": "Riot Platforms (AI infrastructure)",
    "WYFI": "WyFi (AI infrastructure — community mention)",
    "DGXX": "Digix (AI infrastructure — community mention)",
}

# Quantum Computing Sector — @InvestmentGuru_ sector map
QUANTUM_SECTOR = {
    # Pure-Play Quantum
    "IONQ": "IonQ (trapped-ion quantum, 256-qubit demo 2026)",
    "RGTI": "Rigetti Computing (superconducting, highest beta)",
    "QBTS": "D-Wave Quantum (annealing, commercially de-risked)",
    "QUBT": "Quantum Computing Inc (photonic, $39K→$3.7M rev)",
    "INFQ": "Infleqtion (neutral-atom + sensing, early)",
    "ARQQ": "Arqit Quantum (quantum encryption, national security)",
    "LAES": "LakeShore Acquisition II (quantum-resistant chips)",
    # Big Tech Quantum
    "IBM": "IBM (1000+ qubit processors, fault-tolerant ~2029)",
    "GOOGL": "Alphabet (Willow chip, quantum error correction)",
    "MSFT": "Microsoft (topological qubits, Azure Quantum)",
    "AMZN": "Amazon (AWS Braket, quantum-as-a-service)",
    "NVDA": "NVIDIA (CUDA for quantum, AI-quantum stack)",
    "INTC": "Intel (silicon-spin qubit, CMOS scalable)",
    "HON": "Honeywell (Quantinuum majority stake, IPO catalyst)",
    "BAH": "Booz Allen Hamilton (govt quantum contracts)",
    # Semiconductor & Infrastructure
    "GFS": "GlobalFoundries (quantum chip fab)",
    "MU": "Micron (memory + quantum infrastructure)",
    "AMD": "AMD (HPC + quantum ecosystem)",
    "TSM": "TSMC (quantum fabrication foundation)",
    "ASML": "ASML (EUV lithography, irreplaceable chokepoint)",
    # Quantum Networking / Optical / Security
    "CIEN": "Ciena (optical networking + quantum research)",
    "NOK": "Nokia (quantum-safe telecom)",
    "LITE": "Lumentum (photonics + quantum)",
    "AAOI": "Applied Optoelectronics (optical connectivity)",
    "COHR": "Coherent (photonics + laser systems)",
    # Community mentions
    "GRRR": "Gorilla Technology (quantum cryptography MOU)",
}

# Cybersecurity Sector
CYBER_SECTOR = {
    # Endpoint & Cloud Security
    "CRWD": "CrowdStrike (endpoint security, XDR)",
    "PANW": "Palo Alto Networks (SASE, cloud security)",
    "FTNT": "Fortinet (firewall + SD-WAN)",
    "CYBR": "CyberArk (privileged access management)",
    "S": "SentinelOne (AI-powered endpoint)",
    "OKTA": "Okta (identity & access management)",
    "ZS": "Zscaler (cloud-native security)",
    "GEN": "Gen Digital (consumer cybersecurity)",
    "RDWR": "Radware (DDoS + app security)",
    # Identity & Zero Trust
    "DUOL": "Duo Security / Cisco (zero trust)",
    "NET": "Cloudflare (edge security + CDN)",
    "AKAM": "Akamai (edge security + CDN)",
    # Threat Intelligence
    "MNDT": "Mandiant / Google (threat intel)",
    "TENB": "Tenable (vulnerability management)",
    "QLYS": "Qualys (cloud security + compliance)",
    "RPD": "Rapid7 (security analytics)",
    # Quantum-Safe / Post-Quantum
    "ARQQ": "Arqit Quantum (quantum encryption)",
    "GRRR": "Gorilla Technology (quantum cryptography)",
    # Cyber ETFs
    "CIBR": "First Trust NASDAQ Cybersecurity ETF",
    "HACK": "ETFMG Prime Cyber Security ETF",
    "BUG": "Global X Cybersecurity ETF",
}

# Banking & Financial Services Sector
BANK_SECTOR = {
    # Money Center Banks
    "JPM": "JPMorgan Chase (largest US bank)",
    "BAC": "Bank of America (consumer + investment)",
    "WFC": "Wells Fargo (consumer lending recovery)",
    "C": "Citigroup (global restructuring)",
    "GS": "Goldman Sachs (investment banking + trading)",
    "MS": "Morgan Stanley (wealth management)",
    # Regional Banks
    "PNC": "PNC Financial (regional leader)",
    "USB": "US Bancorp (regional)",
    "TFC": "Truist Financial (regional)",
    "COF": "Capital One (credit cards + digital)",
    "SCHW": "Charles Schwab (brokerage + banking)",
    "IBKR": "Interactive Brokers (global brokerage)",
    # Fintech / Digital Banks
    "SOFI": "SoFi (digital banking + lending)",
    "HOOD": "Robinhood (retail brokerage)",
    "NU": "Nubank (Latin America digital bank)",
    "AFRM": "Affirm (BNPL)",
    "SQ": "Block / Square (payments + Cash App)",
    "PYPL": "PayPal (digital payments)",
    "ADYEN": "Adyen (global payments)",
    # Insurance
    "BRK.B": "Berkshire Hathaway (conglomerate + insurance)",
    "PGR": "Progressive (auto insurance)",
    "TRV": "Travelers (property & casualty)",
    "AIG": "AIG (global insurance)",
    # Financial ETFs
    "XLF": "Financial Select Sector SPDR",
    "KRE": "SPDR S&P Regional Banking ETF",
    "KBE": "SPDR S&P Bank ETF",
}

# Emerging Markets Sector
EMERGING_SECTOR = {
    # China Tech
    "BABA": "Alibaba (e-commerce + cloud)",
    "JD": "JD.com (e-commerce + logistics)",
    "PDD": "PDD Holdings / Temu (discount e-commerce)",
    "NTES": "NetEase (gaming)",
    "BIDU": "Baidu (search + AI)",
    "TCEHY": "Tencent (gaming + social + fintech)",
    "DIDI": "DiDi (ride-sharing)",
    "LI": "Li Auto (EV)",
    "NIO": "NIO (EV)",
    "XPEV": "XPeng (EV)",
    # Latin America
    "MELI": "MercadoLibre (e-commerce + fintech)",
    "NU": "Nubank (digital banking)",
    "GRAB": "Grab (super-app SE Asia)",
    "SE": "Sea Limited (gaming + e-commerce)",
    # India
    "INFY": "Infosys (IT services)",
    "WIT": "Wipro (IT services)",
    "HDB": "HDFC Bank (largest private bank)",
    "IBN": "ICICI Bank (private bank)",
    "MMYT": "MakeMyTrip (travel)",
    "RELIANCE": "Reliance Industries (conglomerate)",
    # Frontier / Broad
    "EWZ": "Brazil ETF",
    "EWW": "Mexico ETF",
    "EWC": "Canada ETF",
    "EWY": "South Korea ETF",
    "EWG": "Germany ETF",
    "EWQ": "France ETF",
    "EWP": "Spain ETF",
    "EWN": "Netherlands ETF",
    "EWI": "Italy ETF",
    "EWD": "Sweden ETF",
    "VWO": "Vanguard Emerging Markets ETF",
    "IEMG": "iShares Core EM ETF",
}

# Aeronautics & Aerospace Sector
AERO_SECTOR = {
    # Commercial Aviation
    "BA": "Boeing (commercial aircraft)",
    "AIR.PA": "Airbus (European commercial)",
    "GE": "GE Aerospace (jet engines)",
    "RTX": "RTX / Pratt & Whitney (engines)",
    "SAFRAN": "Safran (engines + equipment)",
    "SPR": "Spirit AeroSystems (aero structures)",
    "TDG": "TransDigm (aerospace components)",
    "HWM": "Howmet Aerospace (engine components)",
    "ATRO": "Astronics (aircraft electronics)",
    # Defense & Military Aviation
    "LMT": "Lockheed Martin (F-35, defense)",
    "NOC": "Northrop Grumman (stealth, drones)",
    "GD": "General Dynamics (Gulfstream + defense)",
    "LHX": "L3Harris (C4ISR + avionics)",
    "HII": "Huntington Ingalls (naval)",
    "KTOS": "Kratos Defense (drones + hypersonics)",
    # Urban Air Mobility / eVTOL
    "ACHR": "Archer Aviation (eVTOL)",
    "JOBY": "Joby Aviation (eVTOL)",
    "LILM": "Lilium (eVTOL)",
    "EH": "EHang (autonomous aerial vehicles)",
    "EVTL": "Vertical Aerospace (eVTOL)",
    # Drones / UAV
    "AVAV": "AeroVironment (tactical drones)",
    "KRAT": "Kratos (combat drones)",
    "UAVS": "AgEagle Aerial Systems (agriculture drones)",
    "DPRO": "Draganfly (commercial drones)",
    # Aerospace ETFs
    "ITA": "iShares US Aerospace & Defense ETF",
    "XAR": "SPDR S&P Aerospace & Defense ETF",
    "PPA": "Invesco Aerospace & Defense ETF",
}

# All sectors combined for the agent
ALL_SECTORS = {
    "space": SPACE_SECTOR,
    "ai_infra": AI_INFRA_SECTOR,
    "quantum": QUANTUM_SECTOR,
    "cyber": CYBER_SECTOR,
    "banks": BANK_SECTOR,
    "emerging": EMERGING_SECTOR,
    "aero": AERO_SECTOR,
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

def fetch_polygon(ticker: str) -> dict:
    env = load_env()
    api_key = env.get("POLYGON_API_KEY", "")
    if not api_key:
        return {}
    
    url = 'https://api.polygon.io/v2/aggs/ticker/' + ticker + '/prev?apiKey=' + api_key
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VOX/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception:
        return {}

def analyze_sectors() -> dict:
    """Analyze all sectors and rank by momentum. Also track space sector."""
    
    sector_data = []
    
    for ticker, name in SECTORS.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            sector_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume,
                "momentum": change_pct  # Simple momentum = daily change
            })
    
    # Sort by momentum
    sector_data.sort(key=lambda x: x["momentum"], reverse=True)
    
    # --- SPACE SECTOR TRACKING ---
    space_data = []
    space_movers = []
    for ticker, name in SPACE_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            space_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                space_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    space_data.sort(key=lambda x: x["change_pct"], reverse=True)
    space_avg_change = sum(s["change_pct"] for s in space_data) / len(space_data) if space_data else 0
    
    # --- AI INFRASTRUCTURE SECTOR TRACKING ---
    ai_data = []
    ai_movers = []
    for ticker, name in AI_INFRA_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            ai_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                ai_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    ai_data.sort(key=lambda x: x["change_pct"], reverse=True)
    ai_avg_change = sum(s["change_pct"] for s in ai_data) / len(ai_data) if ai_data else 0
    
    # --- QUANTUM SECTOR TRACKING ---
    quantum_data = []
    quantum_movers = []
    for ticker, name in QUANTUM_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            quantum_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                quantum_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    quantum_data.sort(key=lambda x: x["change_pct"], reverse=True)
    quantum_avg_change = sum(s["change_pct"] for s in quantum_data) / len(quantum_data) if quantum_data else 0
    
    # --- CYBERSECURITY SECTOR TRACKING ---
    cyber_data = []
    cyber_movers = []
    for ticker, name in CYBER_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            cyber_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                cyber_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    cyber_data.sort(key=lambda x: x["change_pct"], reverse=True)
    cyber_avg_change = sum(s["change_pct"] for s in cyber_data) / len(cyber_data) if cyber_data else 0
    
    # --- BANKING SECTOR TRACKING ---
    bank_data = []
    bank_movers = []
    for ticker, name in BANK_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            bank_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                bank_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    bank_data.sort(key=lambda x: x["change_pct"], reverse=True)
    bank_avg_change = sum(s["change_pct"] for s in bank_data) / len(bank_data) if bank_data else 0
    
    # --- EMERGING MARKETS SECTOR TRACKING ---
    emerging_data = []
    emerging_movers = []
    for ticker, name in EMERGING_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            emerging_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                emerging_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    emerging_data.sort(key=lambda x: x["change_pct"], reverse=True)
    emerging_avg_change = sum(s["change_pct"] for s in emerging_data) / len(emerging_data) if emerging_data else 0
    
    # --- AERONAUTICS SECTOR TRACKING ---
    aero_data = []
    aero_movers = []
    for ticker, name in AERO_SECTOR.items():
        data = fetch_polygon(ticker)
        if data.get("results"):
            r = data["results"][0]
            price = r.get("c", 0)
            open_price = r.get("o", 0)
            change_pct = ((price - open_price) / open_price * 100) if open_price else 0
            volume = r.get("v", 0)
            
            aero_data.append({
                "ticker": ticker,
                "name": name,
                "price": price,
                "change_pct": change_pct,
                "volume": volume
            })
            
            if abs(change_pct) >= 5:
                aero_movers.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": change_pct,
                    "price": price
                })
    
    aero_data.sort(key=lambda x: x["change_pct"], reverse=True)
    aero_avg_change = sum(s["change_pct"] for s in aero_data) / len(aero_data) if aero_data else 0
    
    # Determine rotation signal
    top3 = sector_data[:3]
    bottom3 = sector_data[-3:]
    
    # Check for rotation (tech vs energy vs staples)
    tech_rank = next((i for i, s in enumerate(sector_data) if s["ticker"] == "XLK"), 5)
    energy_rank = next((i for i, s in enumerate(sector_data) if s["ticker"] == "XLE"), 5)
    staples_rank = next((i for i, s in enumerate(sector_data) if s["ticker"] == "XLP"), 5)
    
    if tech_rank <= 2 and staples_rank >= 8:
        rotation = "RISK_ON"
    elif staples_rank <= 2 and tech_rank >= 8:
        rotation = "RISK_OFF"
    elif energy_rank <= 2:
        rotation = "INFLATION"
    else:
        rotation = "NEUTRAL"
    
    analysis = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rotation": rotation,
        "sectors": sector_data,
        "top3": [{"ticker": s["ticker"], "name": s["name"], "change": s["change_pct"]} for s in top3],
        "bottom3": [{"ticker": s["ticker"], "name": s["name"], "change": s["change_pct"]} for s in bottom3],
        "space_sector": {
            "tickers": space_data,
            "movers": space_movers,
            "avg_change_pct": round(space_avg_change, 2),
            "top_mover": space_data[0] if space_data else None,
            "catalyst": "SpaceX IPO ($SPCX) expected next month — sector rerating"
        },
        "ai_infra_sector": {
            "tickers": ai_data,
            "movers": ai_movers,
            "avg_change_pct": round(ai_avg_change, 2),
            "top_mover": ai_data[0] if ai_data else None,
            "catalyst": "Leopold Aschenbrenner AI infrastructure 13F — ex-miners turned AI compute"
        },
        "quantum_sector": {
            "tickers": quantum_data,
            "movers": quantum_movers,
            "avg_change_pct": round(quantum_avg_change, 2),
            "top_mover": quantum_data[0] if quantum_data else None,
            "catalyst": "Quantum computing sector map — IONQ 256-qubit demo, Quantinuum IPO, QUBT $3.7M revenue"
        },
        "cyber_sector": {
            "tickers": cyber_data,
            "movers": cyber_movers,
            "avg_change_pct": round(cyber_avg_change, 2),
            "top_mover": cyber_data[0] if cyber_data else None,
            "catalyst": "Cybersecurity — AI-driven threats, zero-trust mandates, quantum-safe encryption"
        },
        "bank_sector": {
            "tickers": bank_data,
            "movers": bank_movers,
            "avg_change_pct": round(bank_avg_change, 2),
            "top_mover": bank_data[0] if bank_data else None,
            "catalyst": "Banking — rate cycle, fintech disruption, regional bank M&A"
        },
        "emerging_sector": {
            "tickers": emerging_data,
            "movers": emerging_movers,
            "avg_change_pct": round(emerging_avg_change, 2),
            "top_mover": emerging_data[0] if emerging_data else None,
            "catalyst": "Emerging Markets — China stimulus, India growth, LatAm fintech"
        },
        "aero_sector": {
            "tickers": aero_data,
            "movers": aero_movers,
            "avg_change_pct": round(aero_avg_change, 2),
            "top_mover": aero_data[0] if aero_data else None,
            "catalyst": "Aeronautics — Boeing recovery, eVTOL commercialization, defense spending"
        },
        "implications": {
            "RISK_ON": "Favor growth stocks, tech, crypto",
            "RISK_OFF": "Favor defensive, staples, bonds, cash",
            "INFLATION": "Favor energy, materials, real assets",
            "NEUTRAL": "No clear rotation, stock-picking matters"
        }[rotation]
    }
    
    output_file = SCRIPT_DIR / "vox_sector_analysis.json"
    with open(output_file, 'w') as f:
        json.dump(analysis, f, indent=2)
    
    # Only print if rotation is not neutral OR any sector has big movers
    should_print = rotation != "NEUTRAL" or len(space_movers) > 0 or len(ai_movers) > 0 or len(quantum_movers) > 0 or len(cyber_movers) > 0 or len(bank_movers) > 0 or len(emerging_movers) > 0 or len(aero_movers) > 0
    
    if should_print:
        if rotation != "NEUTRAL":
            print(f"🏭 Sector Rotation: {rotation}")
            print(f"   Top: {', '.join([s['name'] for s in top3])}")
            print(f"   Bottom: {', '.join([s['name'] for s in bottom3])}")
        
        if space_movers:
            print(f"🚀 SPACE SECTOR — {len(space_movers)} movers ≥5% (avg: {space_avg_change:+.1f}%)")
            for s in space_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if space_data:
                print(f"   Leader: ${space_data[0]['ticker']} ({space_data[0]['name'][:30]})")
        
        if ai_movers:
            print(f"🤖 AI INFRA — {len(ai_movers)} movers ≥5% (avg: {ai_avg_change:+.1f}%)")
            for s in ai_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if ai_data:
                print(f"   Leader: ${ai_data[0]['ticker']} ({ai_data[0]['name'][:30]})")
        
        if quantum_movers:
            print(f"⚛️ QUANTUM — {len(quantum_movers)} movers ≥5% (avg: {quantum_avg_change:+.1f}%)")
            for s in quantum_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if quantum_data:
                print(f"   Leader: ${quantum_data[0]['ticker']} ({quantum_data[0]['name'][:30]})")
        
        if cyber_movers:
            print(f"🔒 CYBER — {len(cyber_movers)} movers ≥5% (avg: {cyber_avg_change:+.1f}%)")
            for s in cyber_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if cyber_data:
                print(f"   Leader: ${cyber_data[0]['ticker']} ({cyber_data[0]['name'][:30]})")
        
        if bank_movers:
            print(f"🏦 BANKS — {len(bank_movers)} movers ≥5% (avg: {bank_avg_change:+.1f}%)")
            for s in bank_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if bank_data:
                print(f"   Leader: ${bank_data[0]['ticker']} ({bank_data[0]['name'][:30]})")
        
        if emerging_movers:
            print(f"🌍 EMERGING — {len(emerging_movers)} movers ≥5% (avg: {emerging_avg_change:+.1f}%)")
            for s in emerging_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if emerging_data:
                print(f"   Leader: ${emerging_data[0]['ticker']} ({emerging_data[0]['name'][:30]})")
        
        if aero_movers:
            print(f"✈️ AERO — {len(aero_movers)} movers ≥5% (avg: {aero_avg_change:+.1f}%)")
            for s in aero_movers[:5]:
                emoji = "🚀" if s['change_pct'] > 0 else "📉"
                print(f"   {emoji} ${s['ticker']}: {s['change_pct']:+.1f}%")
            if aero_data:
                print(f"   Leader: ${aero_data[0]['ticker']} ({aero_data[0]['name'][:30]})")
    
    return analysis

if __name__ == "__main__":
    analyze_sectors()
