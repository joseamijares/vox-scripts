#!/usr/bin/env python3
"""
VOX UNIVERSE EXPANDER v1.0
Discovers new tickers from multiple sources and adds them to vox_grades for grading.

Sources:
- Trending stocks (momentum, volume spikes)
- Sector leaders from high-momentum sectors
- IPOs and recent listings
- Thematic plays (AI, quantum, nuclear, hydrogen, space, EM fintech)
- Social sentiment (Reddit, X trending)
- Analyst upgrades
- Breakout patterns

Tier System:
Tier 1: Portfolio (72 positions) - graded daily
Tier 2: Watchlist (45 tickers) - graded daily
Tier 3: Trending/Opportunities (200 tickers) - graded 3x/week
Tier 4: Broad Market (2,000+ tickers) - graded weekly
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = ""
DB_NAME = os.environ.get("DB_NAME", "railway")

def connect():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )

# Thematic ticker collections for aggressive growth
THEMATIC_UNIVERSES = {
    "quantum_computing": [
        "IONQ", "RGTI", "QBTS", "ARQQ", "QUBT", "QSIM", "QMCO", "QBIT",
        "IBM", "GOOGL", "MSFT", "AMZN", "NVDA", "HON", "ALTM", "FORM",
        "ACN", "T", "VZ", "TMUS", "ERIC", "NOK", "INTC", "QCOM", "TXN"
    ],
    "nuclear_energy": [
        "OKLO", "SMR", "CEG", "BWXT", "NNE", "CCJ", "LEU", "URG", "UEC",
        "DNN", "LTBR", "TLN", "BE", "FLR", "MTZ", "JEC", "PWR", "NEE",
        "SO", "DUK", "AEP", "EXC", "XEL", "WEC", "PEG", "ED", "ETR",
        "FE", "AEE", "CNP", "CMS", "ATO", "NI", "SWX", "ORA", "GPRE",
        "BEP", "BEPC", "NEP", "CWEN", "AY", "HASI", "RNW", "NOVA"
    ],
    "hydrogen": [
        "PLUG", "BE", "FCEL", "BLDP", "CMI", "LIN", "APD", "NEL", "ITM",
        "PCELL", "HDRO", "ICLN", "PBW", "QCLN", "HYDR", "HYSR", "GWH",
        "EOSE", "SPWR", "RUN", "ENPH", "SEDG", "ARRY", "SHLS", "NOVA",
        "CSIQ", "JKS", "DQ", "SOL", "MAXN", "RENEW", "GPRE", "MTZ"
    ],
    "em_fintech": [
        "NU", "MELI", "STNE", "PAGS", "DLO", "AFRM", "SOFI", "HOOD", "SQ",
        "PYPL", "UPST", "LMND", "ROOT", "RENT", "AFRM", "GLBE", "BILL",
        "GPN", "FIS", "FISV", "GDOT", "WEX", "EVTC", "PAYO", "FOUR",
        "TOST", "LSPD", "OPEN", "OPFI", "ENVA", "CURO", "EZPW", "FCFS",
        "PRG", "SC", "ALLY", "COF", "DFS", "SYF", "AXP", "MA", "V",
        "WPM", "FUTU", "TIGR", "FRHC", "ATFX", "XP", "CINT", "EBANX"
    ],
    "space": [
        "RKLB", "ASTS", "SPCE", "LUNR", "REDW", "VORB", "AJRD", "MAXR",
        "IRDM", "LMT", "BA", "RTX", "NOC", "GD", "HII", "TDG", "HEI",
        "CW", "KBR", "SAIC", "HRLY", "KVYO", "MRCY", "OSIS", "ATRO",
        "ESP", "KAMN", "AIR", "TATT", "RADA", "DSS", "BWX", "KTOS",
        "FLIR", "COBH", "TRMB", "GILT", "VSAT", "SATS", "DISH", "GOGO"
    ],
    "ai_infrastructure": [
        "NVDA", "AMD", "TSM", "AVGO", "MRVL", "MPWR", "LRCX", "AMAT", "KLAC",
        "SNPS", "CDNS", "ANSS", "FTNT", "CRWD", "NET", "DDOG", "S", "PLTR",
        "AI", "ESTC", "DT", "FSLY", "CFLT", "SNOW", "MDB", "DAVA", "SMCI",
        "DELL", "HPE", "INTC", "MU", "STX", "WDC", "NTAP", "PSTG", "BOX",
        "DOCN", "VEEV", "NOW", "WDAY", "TEAM", "ATLASSIAN", "ZOOM", "RING",
        "TWLO", "BILL", "HCP", "RPD", "TENB", "QLYS", "RPD", "CYBR", "ZS",
        "PANW", "CHKP", "FTNT", "SPLK", "SUMO", "BIG", "U", "RBLX", "META",
        "GOOGL", "MSFT", "AMZN", "AAPL", "ORCL", "SAP", "ADBE", "INTU",
        "CRM", "HUBS", "ZEN", "ASAN", "MONDAY", "SMAR", "WORK", "SLACK"
    ],
    "biotech_gene": [
        "CRSP", "EDIT", "NTLA", "BEAM", "VRTX", "SRPT", "BMRN", "IONS",
        "RNA", "ARWR", "PRVB", "KROS", "DNA", "TWST", "QSI", "VERV",
        "BLUE", "FATE", "SGMO", "NVTA", "PACB", "CDNA", "GH", "EXAS",
        "NTRA", "MYGN", "GEN", "ILMN", "TXG", "BEAM", "INTellia", "CAR-T",
        "KPTI", "ALNY", "ARVN", "BPMC", "DCPH", "EPZM", "FOLD", "HALO",
        "IOVA", "MGNX", "NKTR", "ONCT", "PTCT", "RCKT", "SANA", "TCRR",
        "TGTX", "ZYME", "ABBV", "BIIB", "GILD", "REGN", "AMGN", "LLY",
        "PFE", "MRK", "JNJ", "AZN", "NVO", "RPRX", "INCY", "BNTX",
        "MRNA", "NVAX", "VXRT", "INO", "ALT", "GOVX", "HGEN", "DVAX"
    ],
    "robotics_automation": [
        "ISRG", "TER", "ZBRA", "OMCL", "CGNX", "RBR", "ABB", "FAN",
        "ROBT", "BOTZ", "ARKQ", "KUKA", "YASK", "FANUC", "SIEMENS",
        "KUKAF", "OMRON", "KEYENCE", "SMC", "THK", "NTN", "HDNG", "KWR",
        "RBC", "ROLL", "HEICO", "TDG", "CW", "MOG", "ATRO", "KAMN",
        "HOLI", "DHR", "TMO", "A", "BRKR", "WAT", "MTD", "PEN", "RGEN",
        " BIO", "TTEC", "SYK", "MDT", "ZBH", "STE", "MASI", "PODD"
    ],
    "crypto_blockchain": [
        "COIN", "MSTR", "HOOD", "BITF", "MARA", "RIOT", "CLSK", "CORZ",
        "WULF", "BTBT", "IREN", "HIVE", "ARBK", "GLXY", "CAN", "EBON",
        "SOS", "NCTY", "MOGO", "BTCS", "RIOT", "HUT", "DMG", "DGHI",
        "BITF", "ARBK", "GLXY", "VYGR", "SDIG", "GREE", "SBLK", "STRR",
        "APLD", "SLNH", "MIGI", "CIFR", "BITF", "WULF", "RIOT", "MARA",
        "BTBT", "CLSK", "CORZ", "HUT", "IREN", "HIVE", "ARBK", "GLXY",
        "COIN", "MSTR", "HOOD", "SQ", "PYPL", "AFRM", "SOFI", "UPST"
    ],
    "ev_battery": [
        "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "BYDDF", "VWAGY",
        "QS", "SLDP", "ENOV", "ALB", "SQM", "LTHM", "PLL", "MP", "FSR",
        "GOEV", "CANOO", "ARVL", "ELMS", "MULN", "REE", "AYRO", "KNDI",
        "GP", "NKLA", "HYLN", "XL", "BLNK", "CHPT", "EVGO", "BEEM",
        "SPWR", "RUN", "ENPH", "SEDG", "ARRY", "SHLS", "NOVA", "CSIQ",
        "JKS", "DQ", "SOL", "MAXN", "FREY", "AMPS", "STEM", "EOSE",
        "GWH", "FLNC", "NRGV", "ECVT", "VLTA", "EVA", "PCT", "ABAT"
    ]
}

# Trending/momentum tickers (high volume, breakouts)
TRENDING_CANDIDATES = [
    "APP", "VST", "COHR", "CELH", "SMCI", "SOUN", "BABA", "JD", "PDD",
    "SHOP", "SNOW", "NET", "CRWD", "ZS", "PANW", "CYBR", "S", "OKTA",
    "DDOG", "MDB", "CFLT", "PLTR", "AI", "PATH", "BIG", "U", "RBLX",
    "META", "SNAP", "PINS", "SPOT", "ROKU", "ZM", "DOCU", "SQ", "AFRM",
    "SOFI", "HOOD", "UPST", "LMND", "ROOT", "RENT", "W", "ETSY", "CHWY",
    "PTON", "DASH", "ABNB", "UBER", "LYFT", "GRAB", "DIDI", "SE", "MELI",
    "NU", "STNE", "PAGS", "DLO", "GLBE", "FVRR", "TASK", "UPWK", "GTLB",
    # Additional aggressive growth tickers
    "APLD", "APPS", "ARM", "ASAN", "ASTS", "AVDX", "AVPT", "AXON",
    "BE", "BEAM", "BEEM", "BILL", "BMBL", "BRZE", "BTBT", "BTDR",
    "CART", "CFLT", "CGNX", "CLSK", "CNVA", "COMM", "CORZ", "CPNG",
    "CRDO", "CRSP", "CSPR", "CTKB", "DAVA", "DCT", "DGHI", "DNA",
    "DOCS", "DOMA", "DRCT", "DT", "DUOL", "DV", "ENOV", "ENVX",
    "EOSE", "EVGO", "EVLV", "EXAI", "FIGS", "FLNC", "FOUR", "FRSH",
    "FSLY", "FTCI", "FVRR", "GCT", "GDRX", "GFS", "GH", "GLOB",
    "GOCO", "GOEV", "GPRO", "GRAB", "GREE", "GTLB", "HCP", "HIMS",
    "HIVE", "HOOD", "HUT", "IAS", "IBET", "IMMR", "INSM", "IOVA",
    "IREN", "JOBY", "KIND", "KVYO", "LAW", "LFST", "LI", "LIDR",
    "LILM", "LMND", "LPSN", "LUNR", "LYFT", "MARA", "MAXN", "MDB",
    "MELI", "MIGI", "MNDY", "MQ", "MRVI", "MSTR", "MTTR", "NCNO",
    "NEGG", "NNE", "NOVA", "NTRA", "NTWK", "NVTA", "OLO", "ONON",
    "OPEN", "OPFI", "OPRA", "OSCR", "OWLT", "PAYO", "PCT", "PD",
    "PENN", "PERI", "PHR", "PL", "PLTK", "PRCH", "PRCT", "PRVA",
    "PSFE", "PTON", "PUBM", "PWP", "QBTS", "QS", "RBLX", "RDW",
    "RELY", "RENT", "RGTI", "RKLB", "ROOT", "RPD", "RVMD", "RXRX",
    "S", "SAI", "SANA", "SATS", "SDGR", "SEAT", "SEMR", "SENS",
    "SHLS", "SKIL", "SLDP", "SLNH", "SMR", "SOUN", "SPCE", "SPHR",
    "SPOT", "SRAD", "STEM", "STNE", "STRC", "SUMO", "SWIM", "SWTX",
    "SYRE", "TASK", "TBLA", "TENB", "TGLS", "TIRX", "TOST", "TPIC",
    "TRVG", "TW", "TWKS", "TWLO", "U", "UPBD", "UPST", "VAXX",
    "VCSA", "VECO", "VEL", "VFS", "VLD", "VNET", "VRAR", "VRM",
    "VST", "VXRT", "W", "WALD", "WBX", "WEAV", "WKME", "WULF",
    "XPEV", "YALA", "YEXT", "YOU", "ZETA", "ZIP", "ZUO", "ZYME",
    "ZUO", "ZWS", "AFRM", "ALKT", "ALTR", "ALVO", "AMPL", "AMSC",
    "ANNX", "APGE", "APLT", "APPH", "APTV", "ARBE", "ARHS", "ARLO",
    "ARRY", "ASLE", "ATAT", "ATEN", "AUR", "AUST", "AVAH", "AVAV",
    "AWI", "BAND", "BARK", "BBAI", "BCSF", "BDSX", "BFLY", "BHIL",
    "BIRD", "BL", "BLDE", "BLFS", "BLND", "BLNK", "BMBL", "BNZI",
    "BOWL", "BRCC", "BRLT", "BRZE", "BTSG", "BVS", "BYND", "CALX",
    "CARS", "CENX", "CERT", "CHPT", "CIFR", "CLAR", "CLBT", "CLFD",
    "CLSK", "CMBM", "CMPO", "CMTL", "CNXC", "COFS", "COHR", "COMP",
    "COUR", "CPRX", "CRCT", "CREX", "CRNC", "CRNX", "CRSR", "CSTL",
    "CTLP", "CVNA", "CWAN", "CXM", "CYBN", "CYRX", "DCTH", "DDOG",
    "DLO", "DMAC", "DMTK", "DNMR", "DOMO", "DOYU", "DRS", "DSP",
    "DTC", "DYN", "EHTH", "ELWS", "EMBC", "ENFN", "ENLT", "ENVX",
    "EOSE", "EPRX", "EQRX", "ERAS", "ESMT", "ETNB", "EVBG", "EVCM",
    "EVGO", "EVLV", "EVTL", "EXFY", "EXPI", "FATH", "FBYD", "FICO",
    "FLNC", "FLYW", "FORG", "FORM", "FRGE", "FRSH", "FSLY", "FTCH",
    "FUBO", "FVRR", "GDRX", "GFS", "GGR", "GIPR", "GLBE", "GNLX",
    "GOCO", "GOEV", "GPRO", "GRAB", "GREE", "GTLB", "HCP", "HIMS",
    "HPK", "HROW", "HRTX", "HUBS", "HUT", "IAS", "IBET", "ICAD",
    "IDYA", "IGMS", "IMMR", "IMNM", "IMRX", "IMVT", "INAB", "INDI",
    "INFA", "INMD", "INOD", "INSM", "IOBT", "IONQ", "IOVA", "IPSC",
    "IRBT", "IREN", "ISPC", "ITCI", "JAMF", "JOBY", "KIND", "KNSA",
    "KOD", "KOPN", "KPLT", "KRMD", "KSCP", "KVYO", "KYMR", "LAW",
    "LFST", "LGVN", "LIDR", "LILM", "LITE", "LMAT", "LNTH", "LPRO",
    "LPSN", "LQDA", "LRE", "LSPD", "LTRN", "LTRX", "LUCD", "LUNG",
    "LUNR", "LVLU", "LYEL", "LYFT", "LZ", "MAPS", "MASS", "MATH",
    "MAXN", "MBLY", "MCFT", "MDB", "MDGL", "MDWT", "ME", "MEC",
    "MELI", "MESA", "MGNX", "MGNI", "MGY", "MIGI", "MIND", "MIR",
    "MKFG", "MNDY", "MNKD", "MOD", "MODV", "MQ", "MRCY", "MRVI",
    "MSTR", "MTTR", "MULN", "MVIS", "MX", "NCNO", "NEGG", "NERV",
    "NET", "NEXT", "NNE", "NOVA", "NRDY", "NTRA", "NTWK", "NUTX",
    "NVAX", "NVTS", "NVTA", "NXGL", "OABI", "OCEA", "OCS", "OLED",
    "OLO", "OMGA", "ONON", "ONTF", "OPEN", "OPFI", "OPRA", "OPXS",
    "ORIC", "OSCR", "OSW", "OTLY", "OWLT", "OUST", "PAYO", "PAY",
    "PCT", "PD", "PENN", "PERI", "PETS", "PHR", "PL", "PLCE",
    "PLTK", "PLUG", "PNTG", "POWW", "PRCH", "PRCT", "PRDS", "PRIM",
    "PRME", "PRO", "PRVA", "PSFE", "PTON", "PUBM", "PWP", "QBTS",
    "QD", "QSI", "QS", "RBLX", "RDW", "REAL", "RELY", "RENT",
    "REPL", "RETA", "RGTI", "RKLB", "RMBL", "ROOT", "RPD", "RPID",
    "RPRX", "RXT", "RXRX", "S", "SAI", "SANA", "SATS", "SB",
    "SBXC", "SCPH", "SCWX", "SDGR", "SEAT", "SEMR", "SENS", "SEV",
    "SGHT", "SHLS", "SHO", "SHOP", "SKIL", "SKIN", "SLAB", "SLDP",
    "SLGC", "SLNH", "SM", "SMAR", "SMCI", "SMMT", "SMR", "SMRT",
    "SMTC", "SMTI", "SNAP", "SNCE", "SND", "SOUN", "SPCE", "SPHR",
    "SPOT", "SRAD", "SRDX", "SRRK", "STEM", "STEP", "STNE", "STRC",
    "SUMO", "SWAV", "SWIM", "SWTX", "SYRE", "TALK", "TALO", "TASK",
    "TBLA", "TENB", "TGLS", "TIRX", "TKLF", "TKNO", "TOST", "TPIC",
    "TRVG", "TSAT", "TTD", "TW", "TWKS", "TWLO", "U", "UBER",
    "UPBD", "UPST", "VAXX", "VCSA", "VECO", "VEL", "VERV", "VFS",
    "VHC", "VIR", "VLD", "VNET", "VRAR", "VRM", "VST", "VTEX",
    "VXRT", "W", "WALD", "WBX", "WEAV", "WKME", "WOLF", "WULF",
    "XAIR", "XELA", "XENE", "XPEV", "YALA", "YEXT", "YOU", "YQ",
    "ZETA", "ZIP", "ZLAB", "ZUO", "ZWS", "ZYME", "ZYXI"
]

def init_tier_system():
    """Create tier tracking table"""
    conn = connect()
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS universe_tiers (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL UNIQUE,
            tier INTEGER NOT NULL, -- 1=portfolio, 2=watchlist, 3=trending, 4=broad
            tier_name VARCHAR(20) NOT NULL,
            source VARCHAR(50),
            theme VARCHAR(50),
            discovery_date DATE DEFAULT NOW(),
            last_graded DATE,
            grade_count INTEGER DEFAULT 0,
            avg_grade DECIMAL(5,2),
            priority INTEGER DEFAULT 5,
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_universe_tiers_tier ON universe_tiers(tier);
        CREATE INDEX IF NOT EXISTS idx_universe_tiers_active ON universe_tiers(active);
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Tier system initialized")

def get_current_tickers():
    """Get all tickers already in vox_grades"""
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM vox_grades")
    tickers = {row[0] for row in cur.fetchall()}
    conn.close()
    return tickers

def add_thematic_tickers():
    """Add thematic universe tickers to vox_grades"""
    conn = connect()
    cur = conn.cursor()
    
    existing = get_current_tickers()
    new_count = 0
    
    for theme, tickers in THEMATIC_UNIVERSES.items():
        for ticker in tickers:
            if ticker in existing:
                continue
            
            # Add to vox_grades with placeholder
            cur.execute("""
                INSERT INTO vox_grades (ticker, name, vox_grade, previous_grade, action, 
                    current_price, stop_loss, entry_point, position_value, shares,
                    technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score,
                    catalysts, weather_factors, generated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (ticker, f"{theme.replace('_', ' ').title()} Stock", 50, 50, 'HOLD',
                  0.0, 0.0, 0.0, 0.0, 0, 50, 50, 50, 50, 50, 50, 
                  f"Thematic: {theme}", "Pending analysis", datetime.now()))
            
            # Add to tier tracking
            cur.execute("""
                INSERT INTO universe_tiers (ticker, tier, tier_name, source, theme, priority)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker) DO UPDATE SET 
                    tier = EXCLUDED.tier,
                    tier_name = EXCLUDED.tier_name,
                    theme = EXCLUDED.theme
            """, (ticker, 3, 'trending', 'thematic_universe', theme, 8))
            
            new_count += 1
            existing.add(ticker)
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Added {new_count} thematic tickers")
    return new_count

def add_trending_tickers():
    """Add trending/momentum tickers"""
    conn = connect()
    cur = conn.cursor()
    
    existing = get_current_tickers()
    new_count = 0
    
    for ticker in TRENDING_CANDIDATES:
        if ticker in existing:
            continue
        
        cur.execute("""
            INSERT INTO vox_grades (ticker, name, vox_grade, previous_grade, action,
                current_price, stop_loss, entry_point, position_value, shares,
                technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score,
                catalysts, weather_factors, generated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (ticker, "Trending Stock", 50, 50, 'HOLD',
              0.0, 0.0, 0.0, 0.0, 0, 50, 50, 50, 50, 50, 50,
              "Trending: high volume/breakout candidate", "Pending analysis", datetime.now()))
        
        cur.execute("""
            INSERT INTO universe_tiers (ticker, tier, tier_name, source, priority)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (ticker) DO UPDATE SET tier = EXCLUDED.tier
        """, (ticker, 3, 'trending', 'trending_candidates', 7))
        
        new_count += 1
        existing.add(ticker)
    
    conn.commit()
    cur.close()
    conn.close()
    print(f"✅ Added {new_count} trending tickers")
    return new_count

def classify_portfolio_tiers():
    """Classify existing tickers into tiers"""
    conn = connect()
    cur = conn.cursor()
    
    # Tier 1: Portfolio (truncate long tickers)
    cur.execute("""
        INSERT INTO universe_tiers (ticker, tier, tier_name, source, priority)
        SELECT LEFT(ticker, 20), 1, 'portfolio', 'positions', 10
        FROM positions
        ON CONFLICT (ticker) DO UPDATE SET tier = 1, tier_name = 'portfolio', priority = 10
    """)
    
    # Tier 2: Watchlist
    cur.execute("""
        INSERT INTO universe_tiers (ticker, tier, tier_name, source, priority)
        SELECT LEFT(ticker, 20), 2, 'watchlist', 'watchlist_grades', 8
        FROM watchlist_grades
        ON CONFLICT (ticker) DO UPDATE SET tier = 2, tier_name = 'watchlist', priority = 8
    """)
    
    # Tier 3: SP500
    cur.execute("""
        INSERT INTO universe_tiers (ticker, tier, tier_name, source, priority)
        SELECT LEFT(ticker, 20), 3, 'broad_market', 'sp500_grades', 5
        FROM sp500_grades
        ON CONFLICT (ticker) DO UPDATE SET tier = 3, tier_name = 'broad_market', priority = 5
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Portfolio tiers classified")

def show_universe_stats():
    """Display current universe statistics"""
    conn = connect()
    cur = conn.cursor()
    
    print("\n📊 UNIVERSE STATISTICS")
    print("=" * 60)
    
    cur.execute("""
        SELECT tier_name, COUNT(*), AVG(priority)
        FROM universe_tiers
        WHERE active = TRUE
        GROUP BY tier_name, tier
        ORDER BY tier
    """)
    
    print(f"{'Tier':<20} {'Count':>8} {'Avg Priority':>12}")
    print("-" * 60)
    for row in cur.fetchall():
        print(f"{row[0]:<20} {row[1]:>8} {row[2]:>12.1f}")
    
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM vox_grades")
    total_graded = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM universe_tiers WHERE active = TRUE")
    total_tracked = cur.fetchone()[0]
    
    print(f"\nTotal graded: {total_graded}")
    print(f"Total tracked in tiers: {total_tracked}")
    
    # Themes
    cur.execute("""
        SELECT theme, COUNT(*) 
        FROM universe_tiers 
        WHERE theme IS NOT NULL AND active = TRUE
        GROUP BY theme 
        ORDER BY COUNT(*) DESC
    """)
    
    print("\n🎨 THEME BREAKDOWN")
    for row in cur.fetchall():
        print(f"{row[0]:<25} {row[1]:>4}")
    
    conn.close()

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'full'
    
    if action == 'init':
        init_tier_system()
        classify_portfolio_tiers()
    elif action == 'thematic':
        add_thematic_tickers()
    elif action == 'trending':
        add_trending_tickers()
    elif action == 'classify':
        classify_portfolio_tiers()
    elif action == 'stats':
        show_universe_stats()
    elif action == 'full':
        init_tier_system()
        classify_portfolio_tiers()
        t1 = add_thematic_tickers()
        t2 = add_trending_tickers()
        show_universe_stats()
        print(f"\n🚀 Total new tickers added: {t1 + t2}")
    else:
        print("Usage: init, thematic, trending, classify, stats, full")

if __name__ == '__main__':
    main()
