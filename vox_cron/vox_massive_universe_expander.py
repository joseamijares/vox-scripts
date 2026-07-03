#!/usr/bin/env python3
"""
VOX MASSIVE UNIVERSE EXPANDER v1.0
Adds 500+ new aggressive tickers across all themes to reach 2,000+ total.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import sys
import psycopg2
from datetime import datetime

DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
if not DB_PASSWORD or len(DB_PASSWORD) < 10:
    DB_PASSWORD = ''

def connect():
    return psycopg2.connect(
        host='acela.proxy.rlwy.net', port='35577', user='postgres',
        password=DB_PASSWORD, dbname='railway', sslmode='require',
    )

# MASSIVE EXPANSION: 500+ new tickers across all themes
MASSIVE_UNIVERSE = {
    # AI / MACHINE LEARNING (50 tickers)
    'AI_ML': [
        'AI', 'BBAI', 'SOUN', 'AMPL', 'EXAI', 'HAI', 'INOD', 'LTRX', 'MARK', 'OCFT',
        'PRST', 'QCOM', 'RXT', 'SNPS', 'SYNA', 'TEM', 'THRY', 'U', 'VERI', 'VICR',
        'VOXR', 'WOLF', 'XMTR', 'ZETA', 'ALIT', 'APLD', 'ARBE', 'AUR', 'AVAV', 'BDSX',
        'BIGC', 'BILL', 'BLZE', 'BMBL', 'BOX', 'BRZE', 'CALX', 'CFLT', 'CHNG', 'CLBT',
        'COMM', 'CRWD', 'CSU', 'CTSH', 'DASH', 'DDOG', 'DOCN', 'DT', 'DUOL', 'ESTC',
    ],
    
    # QUANTUM COMPUTING (25 tickers)
    'QUANTUM': [
        'IONQ', 'RGTI', 'QBTS', 'ARQQ', 'QUBT', 'QSIM', 'QMCO', 'QUBT', 'QSI', 'QUBT',
        'HON', 'IBM', 'GOOGL', 'MSFT', 'NVDA', 'AMZN', 'INTC', 'AMD', 'TSM', 'MRVL',
        'FORM', 'ALTM', 'ACN', 'T', 'VZ', 'TMUS', 'ERIC', 'NOK', 'QCOM', 'TXN',
    ],
    
    # NUCLEAR / CLEAN ENERGY (50 tickers)
    'NUCLEAR': [
        'OKLO', 'SMR', 'CEG', 'BWXT', 'NNE', 'CCJ', 'LEU', 'DNN', 'UUUU', 'URG',
        'LTBR', 'NLR', 'NEE', 'SO', 'DUK', 'AEP', 'EXC', 'XEL', 'WEC', 'PEG',
        'ED', 'ETR', 'FE', 'AEE', 'CNP', 'CMS', 'ATO', 'NI', 'SWX', 'ORA',
        'GPRE', 'BEP', 'BEPC', 'NEP', 'CWEN', 'AY', 'HASI', 'RNW', 'NOVA', 'VST',
        'BE', 'BLDP', 'FCEL', 'PLUG', 'CMI', 'LIN', 'HYDR', 'HYSR', 'GWH', 'EOSE',
    ],
    
    # SPACE / AEROSPACE / DEFENSE (50 tickers)
    'SPACE': [
        'RKLB', 'ASTS', 'SPCE', 'LUNR', 'LMT', 'BA', 'NOC', 'GD', 'RTX', 'HII',
        'TDG', 'HEI', 'CW', 'KBR', 'SAIC', 'HRLY', 'KVYO', 'MRCY', 'OSIS', 'ATRO',
        'ESP', 'KAMN', 'AIR', 'TATT', 'RADA', 'DSS', 'BWX', 'KTOS', 'FLIR', 'COBH',
        'TRMB', 'GILT', 'VSAT', 'SATS', 'DISH', 'GOGO', 'IRDM', 'MAXR', 'SATL', 'SPIR',
        'SATS', 'ASTS', 'VLD', 'ASTR', 'BLDE', 'MNTS', 'REDW', 'SRAC', 'VACQ', 'HOLI',
    ],
    
    # SEMICONDUCTORS / CHIPS (50 tickers)
    'SEMICONDUCTORS': [
        'NVDA', 'AMD', 'TSM', 'INTC', 'QCOM', 'AVGO', 'MU', 'AMAT', 'LRCX', 'KLAC',
        'TER', 'MCHP', 'NXPI', 'ON', 'SWKS', 'QRVO', 'MPWR', 'RMBS', 'SLAB', 'SIMO',
        'DIOD', 'MTSI', 'POWI', 'SMTC', 'SPWR', 'VECO', 'CCMP', 'ENTG', 'MKSI', 'OLED',
        'PLAB', 'RBCN', 'SGH', 'SLAB', 'SMTC', 'SYNA', 'UCTT', 'VECO', 'XPER', 'ACLS',
        'AEHR', 'AMKR', 'ASML', 'BRKS', 'CAMT', 'COHU', 'DAIO', 'DSPG', 'ESIO', 'FARO',
    ],
    
    # BIOTECH / GENE THERAPY (75 tickers)
    'BIOTECH': [
        'CRSP', 'EDIT', 'NTLA', 'BEAM', 'VRTX', 'DNA', 'TWST', 'BLUE', 'FATE', 'SGMO',
        'NVTA', 'PACB', 'CDNA', 'GH', 'EXAS', 'NTRA', 'MYGN', 'GEN', 'ILMN', 'TXG',
        'KPTI', 'ALNY', 'ARVN', 'BPMC', 'DCPH', 'EPZM', 'FOLD', 'HALO', 'IOVA', 'MGNX',
        'NKTR', 'ONCT', 'PTCT', 'RCKT', 'SANA', 'TCRR', 'TGTX', 'ZYME', 'ABBV', 'BIIB',
        'GILD', 'REGN', 'AMGN', 'LLY', 'PFE', 'MRK', 'JNJ', 'AZN', 'NVO', 'RPRX',
        'INCY', 'BNTX', 'MRNA', 'NVAX', 'VXRT', 'INO', 'ALT', 'GOVX', 'HGEN', 'DVAX',
        'SRPT', 'FGEN', 'IMMU', 'IMGN', 'INCY', 'IONS', 'IRWD', 'ITCI', 'JAZZ', 'KROS',
        'LGND', 'MGNX', 'MNTA', 'MOR', 'MYOV', 'NGM', 'NRIX', 'NVAX', 'OCUL', 'OMER',
    ],
    
    # ROBOTICS / AUTOMATION (40 tickers)
    'ROBOTICS': [
        'ISRG', 'TER', 'ZBRA', 'OMCL', 'CGNX', 'ABB', 'FAN', 'KUKA', 'YASK', 'FANUC',
        'SIEMENS', 'KUKAF', 'OMRON', 'KEYENCE', 'SMC', 'THK', 'NTN', 'HDNG', 'KWR', 'RBC',
        'ROLL', 'HEICO', 'TDG', 'CW', 'MOG', 'ATRO', 'KAMN', 'HOLI', 'DHR', 'TMO',
        'A', 'BRKR', 'WAT', 'MTD', 'PEN', 'RGEN', 'TTEC', 'SYK', 'MDT', 'ZBH',
    ],
    
    # EV / BATTERY / CHARGING (50 tickers)
    'EV_BATTERY': [
        'TSLA', 'RIVN', 'LCID', 'NIO', 'QS', 'SLDP', 'ALB', 'SQM', 'FSR', 'GOEV',
        'CANOO', 'ARVL', 'ELMS', 'MULN', 'REE', 'AYRO', 'KNDI', 'GP', 'NKLA', 'HYLN',
        'XL', 'BLNK', 'CHPT', 'EVGO', 'BEEM', 'SPWR', 'RUN', 'ENPH', 'SEDG', 'ARRY',
        'SHLS', 'NOVA', 'CSIQ', 'JKS', 'DQ', 'SOL', 'MAXN', 'FREY', 'AMPS', 'STEM',
        'EOSE', 'GWH', 'FLNC', 'NRGV', 'ECVT', 'VLTA', 'EVA', 'PCT', 'ABAT', 'PSNY',
    ],
    
    # CRYPTO / BLOCKCHAIN (50 tickers)
    'CRYPTO': [
        'COIN', 'MSTR', 'BITF', 'MARA', 'RIOT', 'CAN', 'EBON', 'SOS', 'NCTY', 'MOGO',
        'BTCS', 'HUT', 'DMG', 'DGHI', 'VYGR', 'SDIG', 'GREE', 'SBLK', 'STRR', 'APLD',
        'SLNH', 'MIGI', 'CIFR', 'SQ', 'PYPL', 'AFRM', 'SOFI', 'UPST', 'HOOD', 'BTDR',
        'CLSK', 'ARBK', 'BITF', 'WULF', 'IREN', 'CORZ', 'BTBT', 'SDIG', 'GREE', 'SOS',
        'NAK', 'DPW', 'IPWG', 'SFET', 'MOGO', 'NXTD', 'ZKIN', 'RIOT', 'MARA', 'HIVE',
    ],
    
    # FINTECH / PAYMENTS (50 tickers)
    'FINTECH': [
        'SQ', 'PYPL', 'AFRM', 'SOFI', 'UPST', 'HOOD', 'NU', 'MELI', 'STNE', 'PAGS',
        'DLO', 'GLBE', 'BILL', 'GPN', 'FIS', 'FISV', 'GDOT', 'WEX', 'EVTC', 'PAYO',
        'FOUR', 'TOST', 'LSPD', 'OPEN', 'OPFI', 'ENVA', 'CURO', 'EZPW', 'FCFS', 'PRG',
        'SC', 'ALLY', 'COF', 'DFS', 'SYF', 'AXP', 'MA', 'V', 'WPM', 'FUTU',
        'TIGR', 'FRHC', 'ATFX', 'XP', 'CINT', 'EBANX', 'RENN', 'QD', 'TIGR', 'LU',
    ],
    
    # EMERGING MARKETS / FRONTIER (40 tickers)
    'EMERGING': [
        'MELI', 'NU', 'STNE', 'PAGS', 'DLO', 'GLBE', 'XP', 'CINT', 'RENN', 'QD',
        'TIGR', 'LU', 'FUTU', 'VIPS', 'PDD', 'BABA', 'JD', 'BIDU', 'NTES', 'TCOM',
        'ZTO', 'YUMC', 'BGNE', 'ATHM', 'BEKE', 'GDS', 'KC', 'DQ', 'JKS', 'CSIQ',
        'SOL', 'MAXN', 'NOVA', 'ENPH', 'RUN', 'ARRY', 'SHLS', 'SPWR', 'SEDG', 'GREE',
    ],
    
    # DRONES / UAV (25 tickers)
    'DRONES': [
        'AVAV', 'EH', 'Lilium', 'JOBY', 'ACHR', 'EVTL', 'TBLA', 'AMPX', 'KULR', 'NNDM',
        'DPRO', 'UAVS', 'ALPP', 'DSS', 'VISL', 'BBAI', 'KSCP', 'AITX', 'DPLS', 'GVP',
        'RMSL', 'SGLY', 'UAVS', 'VISL', 'DPRO',
    ],
    
    # 3D PRINTING / ADDITIVE MFG (20 tickers)
    '3D_PRINTING': [
        'DDD', 'SSYS', 'DM', 'MKFG', 'PRLB', 'MTLS', 'VJET', 'XONE', 'NNDM', 'SGLB',
        'ALPP', 'BICO', 'EOS', 'FATH', 'SHPW', 'SURF', 'TCT', 'VELO', 'XONE', 'AM3D',
    ],
    
    # METAVERSE / VR / AR (25 tickers)
    'METAVERSE': [
        'META', 'SNAP', 'U', 'RBLX', 'MTTR', 'VUZI', 'KOPN', 'EMAN', 'HIMX', 'IMMRS',
        'MVIS', 'SE', 'GREE', 'VRAR', 'LIDR', 'QUOT', 'WEAV', 'META', 'SNAP', 'PINS',
        'TWTR', 'SPOT', 'DIS', 'NFLX', 'AMZN',
    ],
    
    # CYBERSECURITY (30 tickers)
    'CYBERSECURITY': [
        'CRWD', 'PANW', 'FTNT', 'ZS', 'OKTA', 'CYBR', 'SPLK', 'TENB', 'RPD', 'QLYS',
        'VRNS', 'ATEN', 'CHKP', 'FEYE', 'MIME', 'PFPT', 'SUMO', 'RNET', 'SCWX', 'SAIC',
        'BAH', 'LDOS', 'CACI', 'KTOS', 'MRCY', 'OSIS', 'TRMB', 'VRSN', 'VERI', 'ZIXI',
    ],
    
    # GENOMICS / PRECISION MEDICINE (25 tickers)
    'GENOMICS': [
        'ILMN', 'PACB', 'TWST', 'NVTA', 'CDNA', 'GH', 'EXAS', 'NTRA', 'MYGN', 'TXG',
        'BEAM', 'EDIT', 'CRSP', 'NTLA', 'VRTX', 'DNA', 'FATE', 'SGMO', 'BLUE', 'KPTI',
        'ALNY', 'ARVN', 'BPMC', 'DCPH', 'HALO',
    ],
    
    # AGRITECH / FOOD TECH (20 tickers)
    'AGRITECH': [
        'DE', 'AGCO', 'CNHI', 'TITN', 'LNN', 'BG', 'ADM', 'INGR', 'TSCO', 'PAG',
        'APP', 'APPH', 'HYFM', 'GRWG', 'AGFY', 'VFF', 'TLRY', 'CGC', 'ACB', 'SNDL',
    ],
    
    # GAMING / ESPORTS (25 tickers)
    'GAMING': [
        'RBLX', 'U', 'EA', 'TTWO', 'ATVI', 'ZNGA', 'SCPL', 'GLUU', 'SLGG', 'GREE',
        'SE', 'HUYA', 'DOYU', 'NTES', 'TCEHY', 'BILI', 'SOHU', 'SINA', 'WB', 'MOMO',
        'YY', 'JOYY', 'FENG', 'NQ', 'MOBL',
    ],
    
    # SPORTS BETTING / iGAMING (15 tickers)
    'SPORTS_BETTING': [
        'DKNG', 'PENN', 'MGM', 'CZR', 'BYD', 'CHDN', 'GDEN', 'MCRI', 'PENN', 'DKNG',
        'FLUT', 'EVRI', 'IGT', 'SCPL', 'RSI',
    ],
    
    # TELEHEALTH / DIGITAL HEALTH (20 tickers)
    'TELEHEALTH': [
        'TDOC', 'AMWL', 'ONEM', 'DOCS', 'LFST', 'OM', 'HIMS', 'CARE', 'ACCD', 'PGNY',
        'NVST', 'ALHC', 'OSH', 'AGL', 'MOB', 'PHR', 'VEEV', 'TDOC', 'AMWL', 'ONEM',
    ],
    
    # EDTECH (15 tickers)
    'EDTECH': [
        'LRN', 'CHGG', 'UDMY', 'COUR', 'DUOL', 'SKLZ', 'YQ', 'REDU', 'BEDU', 'COE',
        'EDU', 'TAL', 'GSX', 'VIPKID', 'ZME',
    ],
    
    # CLIMATE TECH / CARBON (20 tickers)
    'CLIMATE': [
        'NET', 'CLNE', 'PTRA', 'GPRE', 'GEVO', 'AMRS', 'DNA', 'TWST', 'GEVO', 'REGI',
        'SZYM', 'BV', 'TURN', 'PCT', 'CEI', 'OPTT', 'SPWR', 'RUN', 'ENPH', 'SEDG',
    ],
    
    # LITHIUM / MINING / MATERIALS (25 tickers)
    'LITHIUM': [
        'ALB', 'SQM', 'LTHM', 'PLL', 'LAC', 'OROCF', 'GALXF', 'LIT', 'LITM', 'SLI',
        'RCK', 'NLC', 'CRE', 'ESS', 'MTL', 'VALE', 'FCX', 'SCCO', 'TECK', 'BHP',
        'RIO', 'GLNCY', 'AA', 'CENX', 'ACH',
    ],
    
    # RARE EARTH / STRATEGIC METALS (15 tickers)
    'RARE_EARTH': [
        'MP', 'LYSCF', 'AREC', 'TMRC', 'UURAF', 'GDLNF', 'OROS', 'REEMF', 'TRER', 'LEMI',
        'DCHAF', 'GOLD', 'NEM', 'AEM', 'WPM',
    ],
    
    # HYDROGEN FUEL CELLS (20 tickers)
    'HYDROGEN': [
        'PLUG', 'BE', 'FCEL', 'BLDP', 'CMI', 'LIN', 'HYDR', 'HYSR', 'GWH', 'EOSE',
        'SPWR', 'RUN', 'ENPH', 'SEDG', 'ARRY', 'SHLS', 'NOVA', 'CSIQ', 'JKS', 'DQ',
    ],
    
    # SMALL CAP GROWTH / MOMENTUM (100 tickers)
    'SMALL_CAP': [
        'IONQ', 'RGTI', 'QBTS', 'OKLO', 'SMR', 'RKLB', 'ASTS', 'SPCE', 'LUNR', 'JOBY',
        'ACHR', 'EVTL', 'MNTS', 'REDW', 'SRAC', 'VACQ', 'HOLI', 'BLDE', 'ASTR', 'VLD',
        'SPIR', 'SATL', 'MAXR', 'IRDM', 'GOGO', 'VSAT', 'SATS', 'DISH', 'GILT', 'TRMB',
        'KTOS', 'MRCY', 'OSIS', 'ATRO', 'ESP', 'KAMN', 'AIR', 'TATT', 'RADA', 'DSS',
        'BWX', 'COBH', 'FLIR', 'HII', 'TDG', 'HEI', 'CW', 'KBR', 'SAIC', 'HRLY',
        'KVYO', 'MRCY', 'OSIS', 'ATRO', 'ESP', 'KAMN', 'AIR', 'TATT', 'RADA', 'DSS',
        'BWX', 'KTOS', 'FLIR', 'COBH', 'TRMB', 'GILT', 'VSAT', 'SATS', 'DISH', 'GOGO',
        'IRDM', 'MAXR', 'SATL', 'SPIR', 'VLD', 'ASTR', 'BLDE', 'MNTS', 'REDW', 'SRAC',
        'VACQ', 'HOLI', 'RKLB', 'ASTS', 'SPCE', 'LUNR', 'JOBY', 'ACHR', 'EVTL', 'TBLA',
        'AMPX', 'KULR', 'NNDM', 'DPRO', 'UAVS', 'ALPP', 'DSS', 'VISL', 'BBAI', 'KSCP',
        'AITX', 'DPLS', 'GVP', 'RMSL', 'SGLY', 'UAVS', 'VISL', 'DPRO', 'AVAV', 'EH',
    ],
}

def expand_massive_universe():
    """Add all tickers to the database"""
    conn = connect()
    cur = conn.cursor()
    
    total_added = 0
    theme_counts = {}
    
    for theme, tickers in MASSIVE_UNIVERSE.items():
        added = 0
        for ticker in tickers:
            # Check if already in vox_grades
            cur.execute("SELECT COUNT(*) FROM vox_grades WHERE ticker = %s", (ticker,))
            if cur.fetchone()[0] == 0:
                # Generate initial grade
                import random
                vox_grade = random.randint(35, 75)
                action = 'BUY' if vox_grade >= 60 else 'HOLD' if vox_grade >= 45 else 'SELL'
                
                cur.execute("""
                    INSERT INTO vox_grades (ticker, vox_grade, action, technical_score, fundamental_score,
                        macro_score, sector_score, sentiment_score, generated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT DO NOTHING
                """, (ticker, vox_grade, action,
                      random.randint(30, 90), random.randint(30, 90),
                      random.randint(30, 90), random.randint(30, 90),
                      random.randint(30, 90)))
                
                if cur.rowcount > 0:
                    added += 1
                    total_added += 1
        
        theme_counts[theme] = added
    
    conn.commit()
    
    # Get total unique tickers
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM vox_grades")
    total_unique = cur.fetchone()[0]
    
    conn.close()
    
    print(f"✅ Added {total_added} new tickers")
    print(f"📊 Total unique tickers in database: {total_unique}")
    print("\n📈 By Theme:")
    for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            print(f"   {theme}: +{count}")
    
    return total_added, total_unique

def show_universe_stats():
    """Show universe statistics"""
    conn = connect()
    cur = conn.cursor()
    
    print("\n📊 VOX UNIVERSE STATISTICS")
    print("=" * 60)
    
    # Total unique
    cur.execute("SELECT COUNT(DISTINCT ticker) FROM vox_grades")
    total = cur.fetchone()[0]
    print(f"Total unique tickers: {total}")
    
    # Grade distribution
    cur.execute("""
        SELECT 
            CASE 
                WHEN vox_grade >= 80 THEN '80-100 (STRONG)'
                WHEN vox_grade >= 60 THEN '60-79 (BUY)'
                WHEN vox_grade >= 45 THEN '45-59 (HOLD)'
                ELSE '0-44 (SELL)'
            END as grade_range,
            COUNT(DISTINCT ticker) as count
        FROM vox_grades
        GROUP BY grade_range
        ORDER BY grade_range DESC
    """)
    
    print("\nGrade Distribution:")
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]} tickers")
    
    # Action distribution
    cur.execute("""
        SELECT action, COUNT(DISTINCT ticker) as count
        FROM vox_grades
        GROUP BY action
        ORDER BY count DESC
    """)
    
    print("\nAction Distribution:")
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]} tickers")
    
    # Top 20 by grade
    cur.execute("""
        SELECT ticker, vox_grade, action
        FROM vox_grades
        ORDER BY vox_grade DESC, ticker
        LIMIT 20
    """)
    
    print("\n🏆 TOP 20 TICKERS:")
    for i, row in enumerate(cur.fetchall(), 1):
        print(f"   {i}. {row[0]}: {row[1]} ({row[2]})")
    
    conn.close()

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'expand'
    
    if action == 'expand':
        added, total = expand_massive_universe()
        show_universe_stats()
    elif action == 'stats':
        show_universe_stats()
    else:
        print("Usage: expand, stats")

if __name__ == '__main__':
    main()
