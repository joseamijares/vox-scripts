#!/usr/bin/env python3
"""
VOX Insider Trading Monitor v2.0
Real SEC EDGAR Form 4 ingestion for portfolio + high-conviction watchlist.

Sources:
  - positions (shares > 0)
  - vox_grades (vox_grade >= 70)
  - unified_grades (unified_grade >= 70)
  - watchlist (grade >= 70)

Limits: 150 tickers per run (rate-throttled to SEC).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import re
import time
import json
import functools
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import psycopg2
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = int(os.environ.get('DB_PORT', '35577'))
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_USER = os.environ.get('DB_USER', 'postgres')

EMAIL = os.environ.get('SEC_USER_AGENT_EMAIL', 'vox@example.com')
MAX_TICKERS = int(os.environ.get('VOX_INSIDER_MAX_TICKERS', '150'))

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FEED_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=only&count=20&output=atom"
SEC_FORM4_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession_no_dashes}/form4.xml"


def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))


def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )


def create_insider_table():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS insider_trades (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            insider_name VARCHAR(200),
            insider_title VARCHAR(100),
            transaction_date DATE NOT NULL,
            transaction_type VARCHAR(20), -- 'P' Purchase, 'S' Sale, 'A' Award, 'M' vest/exercise, 'G' gift
            shares NUMERIC(15,2),
            price_per_share NUMERIC(12,4),
            total_value NUMERIC(15,2),
            shares_after NUMERIC(15,2),
            is_director BOOLEAN DEFAULT FALSE,
            is_officer BOOLEAN DEFAULT FALSE,
            is_10pct_owner BOOLEAN DEFAULT FALSE,
            importance VARCHAR(20) DEFAULT 'medium',
            form4_url TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, insider_name, transaction_date, transaction_type, shares)
        )
    """)
    conn.commit()
    conn.close()
    print("✅ insider_trades table ready")


@functools.lru_cache(maxsize=1)
def load_cik_map():
    """Download SEC ticker -> CIK mapping."""
    try:
        req = urllib.request.Request(
            SEC_TICKERS_URL,
            headers={'User-Agent': f'VOX Insider Monitor {EMAIL}'}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        # data is dict of index -> {cik_str, ticker, title}
        return {item['ticker'].upper(): str(item['cik_str']).zfill(10)
                for item in data.values()}
    except Exception as e:
        print(f"⚠️  Could not load SEC CIK map: {e}")
        return {}


def get_tickers_to_monitor():
    conn = connect_db()
    cur = conn.cursor()
    tickers = set()

    # Portfolio positions
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0")
    for row in cur.fetchall():
        tickers.add(row[0].upper().strip())

    # Vox grades >= 70 (high-conviction actionable)
    cur.execute("SELECT DISTINCT ticker FROM vox_grades WHERE vox_grade >= 70")
    for row in cur.fetchall():
        tickers.add(row[0].upper().strip())

    # Unified grades >= 70
    cur.execute("SELECT DISTINCT ticker FROM unified_grades WHERE unified_grade >= 70")
    for row in cur.fetchall():
        tickers.add(row[0].upper().strip())

    # Watchlist grade >= 70
    cur.execute("SELECT DISTINCT ticker FROM watchlist WHERE grade >= 70")
    for row in cur.fetchall():
        tickers.add(row[0].upper().strip())

    conn.close()

    # Filter to valid SEC tickers only (exclude crypto -USD, spaces, etc.)
    cleaned = {t for t in tickers if re.match(r'^[A-Z0-9]{1,5}$', t)}
    # Drop common non-stock suffixes
    cleaned = {t.split('-')[0].split('.')[0] for t in cleaned}
    return sorted(cleaned)


def sec_request(url, retries=3):
    """Make a polite SEC request with basic rate limiting."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': f'VOX Insider Monitor {EMAIL}'
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** attempt
                print(f"    ⚠️  429 rate limit, sleeping {wait}s")
                time.sleep(wait)
                continue
            # Return empty for 404/403
            return None
        except Exception as e:
            if attempt == retries - 1:
                print(f"    ⚠️  Request failed: {e}")
                return None
            time.sleep(1)
    return None


def parse_atom_feed(xml_text, ticker):
    """Parse SEC atom feed for Form 4 filings. Return list of accession numbers."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = {'atom': 'http://www.w3.org/2005/Atom'}
    filings = []
    for entry in root.findall('atom:entry', ns):
        content = entry.find('atom:content', ns)
        if content is None:
            continue
        # Accession number is inside atom:content with namespace
        for child in content:
            if child.tag == f"{{{ns['atom']}}}accession-number" and child.text:
                filings.append(child.text)
                break
    return filings


def parse_form4_xml(xml_text, ticker):
    """Parse Form 4 XML into transaction records."""
    records = []
    if not xml_text:
        return records

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"    ⚠️  XML parse error for {ticker}: {e}")
        return records

    # SEC Form 4 XML has no namespace on child elements

    # Issuer / trading symbol
    issuer_symbol = None
    issuer = root.find('.//issuer')
    if issuer is not None:
        sym = issuer.find('issuerTradingSymbol')
        if sym is not None and sym.text:
            issuer_symbol = sym.text.upper()

    # Reporting owner info
    rpt = root.find('.//reportingOwner')
    name = title = ''
    is_director = is_officer = is_10pct = False
    if rpt is not None:
        rpt_id = rpt.find('reportingOwnerId')
        if rpt_id is not None:
            n = rpt_id.find('rptOwnerName')
            if n is not None:
                name = n.text or ''
        rel = rpt.find('reportingOwnerRelationship')
        if rel is not None:
            d = rel.find('isDirector')
            o = rel.find('isOfficer')
            t = rel.find('isTenPercentOwner')
            title_el = rel.find('officerTitle')
            is_director = d is not None and d.text == 'true'
            is_officer = o is not None and o.text == 'true'
            is_10pct = t is not None and t.text == 'true'
            if title_el is not None and title_el.text:
                title = title_el.text

    period = root.find('periodOfReport')
    period_date = period.text if period is not None else None

    def tx_value(node, tag):
        el = node.find(f'.//{tag}')
        if el is None:
            return None
        val = el.find('value')
        if val is not None and val.text:
            return val.text
        if el.text:
            return el.text
        return None

    def tx_numeric(node, tag):
        v = tx_value(node, tag)
        if v is None:
            return None
        try:
            return float(v.replace(',', ''))
        except ValueError:
            return None

    def first_code(node):
        """Find transactionCode inside transactionCoding."""
        tc = node.find('transactionCoding')
        if tc is not None:
            c = tc.find('transactionCode')
            if c is not None and c.text:
                return c.text.upper()
        return None

    # Non-derivative transactions (open market / RSU vesting / exercises)
    for tx in root.findall('.//nonDerivativeTransaction'):
        tdate = tx_value(tx, 'transactionDate') or period_date
        if not tdate:
            continue
        code = first_code(tx) or 'M'
        shares = tx_numeric(tx, 'transactionShares')
        price = tx_numeric(tx, 'transactionPricePerShare')
        ad = (tx_value(tx, 'transactionAcquiredDisposedCode') or '').upper()
        shares_after = tx_numeric(tx, 'sharesOwnedFollowingTransaction')
        if shares is None or shares <= 0:
            continue
        total = (shares * price) if price is not None else 0
        # transaction type: P=acquire, S=dispose, M=exercise/vest, A=award, G=gift
        if ad == 'A':
            ttype = 'P'
        elif ad == 'D':
            ttype = 'S'
        else:
            ttype = code if code in ('P', 'A', 'S', 'G', 'M') else 'M'
        records.append({
            'ticker': issuer_symbol or ticker,
            'name': name,
            'title': title,
            'date': tdate,
            'type': ttype,
            'shares': shares,
            'price': price if price is not None else 0,
            'value': total,
            'shares_after': shares_after,
            'is_director': is_director,
            'is_officer': is_officer,
            'is_10pct': is_10pct,
        })

    return records


def calculate_importance(filing):
    importance = 'medium'
    title = (filing.get('title') or '').upper()
    ttype = filing.get('type', 'M')
    value = filing.get('value', 0) or 0

    # CEO/CFO/Chairman open market purchases are high
    if ttype in ('P', 'A') and any(x in title for x in ['CEO', 'CFO', 'CHAIRMAN', 'PRESIDENT', 'CHIEF EXECUTIVE', 'CHIEF FINANCIAL']):
        importance = 'high'
    # Large purchases > $1M
    if ttype in ('P', 'A') and value > 1_000_000:
        importance = 'high'
    # Large sales > $5M
    if ttype == 'S' and value > 5_000_000:
        importance = 'high'
    # Officer sales generally medium
    if ttype == 'S' and filing.get('is_officer'):
        importance = 'medium'
    # 10% owner purchases
    if ttype in ('P', 'A') and filing.get('is_10pct'):
        importance = 'high'
    return importance


def store_filings(ticker, filings, form4_url):
    if not filings:
        return 0
    conn = connect_db()
    cur = conn.cursor()
    stored = 0
    for f in filings:
        importance = calculate_importance(f)
        title = f.get('title', '')[:99]
        name = f.get('name', '')[:199]
        try:
            cur.execute("""
                INSERT INTO insider_trades
                (ticker, insider_name, insider_title, transaction_date, transaction_type,
                 shares, price_per_share, total_value, shares_after, importance,
                 is_director, is_officer, is_10pct_owner, form4_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, insider_name, transaction_date, transaction_type, shares) DO NOTHING
            """, (f.get('ticker', ticker), name, title, f.get('date'),
                  f.get('type'), f.get('shares'), f.get('price'), f.get('value'),
                  f.get('shares_after'), importance, f.get('is_director', False),
                  f.get('is_officer', False), f.get('is_10pct', False), form4_url))
            if cur.rowcount > 0:
                stored += 1
        except Exception as e:
            print(f"    ⚠️  DB insert error for {ticker}: {e}")
    conn.commit()
    conn.close()
    return stored


def fetch_and_store_for_ticker(ticker, cik_map):
    ticker = ticker.upper().split('-')[0].split('.')[0]
    cik = cik_map.get(ticker)
    if not cik:
        return (0, 0)

    feed_url = SEC_FEED_URL.format(cik=cik)
    xml_text = sec_request(feed_url)
    if xml_text is None:
        return (0, 0)

    accessions = parse_atom_feed(xml_text, ticker)
    if not accessions:
        return (0, 0)

    total_stored = 0
    for acc in accessions:
        acc_no_dashes = acc.replace('-', '')
        form4_url = SEC_FORM4_URL.format(cik=cik.lstrip('0'), accession_no_dashes=acc_no_dashes)
        form4_xml = sec_request(form4_url)
        if form4_xml is None:
            continue
        filings = parse_form4_xml(form4_xml, ticker)
        if filings:
            stored = store_filings(ticker, filings, form4_url)
            total_stored += stored
            if stored > 0:
                print(f"    + {ticker}: {stored} new transaction(s)")
        # Polite rate limit
        time.sleep(0.15)
    return (len(accessions), total_stored)


def detect_cluster_buying():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker,
               COUNT(DISTINCT insider_name) as buyers,
               SUM(total_value) as total,
               SUM(CASE WHEN transaction_type IN ('P','A') THEN total_value ELSE 0 END) as buy_value
        FROM insider_trades
        WHERE transaction_date > NOW() - INTERVAL '30 days'
        GROUP BY ticker
        HAVING COUNT(DISTINCT insider_name) >= 2
           AND SUM(CASE WHEN transaction_type IN ('P','A') THEN total_value ELSE 0 END) > 0
        ORDER BY buy_value DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def generate_insider_report():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT ticker, insider_name, insider_title, transaction_date,
               transaction_type, shares, total_value, importance
        FROM insider_trades
        WHERE transaction_date > NOW() - INTERVAL '30 days'
        ORDER BY
            CASE importance WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            total_value DESC
        LIMIT 25
    """)
    rows = cur.fetchall()

    print(f"\n{'='*70}")
    print(f"🚨 INSIDER TRADING ALERTS — Last 30 Days")
    print(f"{'='*70}")
    if not rows:
        print("No insider trades recorded yet.")
    else:
        print(f"{'Ticker':<8} {'Name':<22} {'Title':<16} {'Date':<12} {'Type':<4} {'Value':<15} {'Importance'}")
        print(f"{'-'*70}")
        for row in rows:
            ticker, name, title, date, t_type, shares, value, importance = row
            t_icon = {'P': '🟢', 'A': '🟢', 'S': '🔴', 'M': '⚪', 'G': '⚪'}.get(t_type, '⚪')
            imp_icon = '🔴' if importance == 'high' else '🟡'
            print(f"{ticker:<8} {name[:21]:<22} {title[:15]:<16} {str(date):<12} {t_icon} {t_type:<2} ${value:>12,.0f} {imp_icon} {importance}")

    # Cluster buying
    clusters = detect_cluster_buying()
    print(f"\n{'='*70}")
    print(f"📊 CLUSTER BUYING ANALYSIS")
    print(f"{'='*70}")
    if not clusters:
        print("No cluster buying detected.")
    else:
        for ticker, buyers, total, buy_value in clusters:
            print(f"  {ticker}: {buyers} insiders bought ${buy_value:,.0f}")

    conn.close()


def run_insider_monitor():
    print("=" * 70)
    print(f"VOX INSIDER TRADING MONITOR — {datetime.now()}")
    print(f"Using real SEC EDGAR Form 4 data")
    print("=" * 70)

    create_insider_table()

    cik_map = load_cik_map()
    print(f"✅ Loaded {len(cik_map):,} SEC ticker/CIK mappings")

    tickers = get_tickers_to_monitor()
    print(f"\nMonitoring {len(tickers)} tickers for insider activity (max {MAX_TICKERS} per run)")

    # Prioritize: positions first, then high grades, then others
    prioritized = []
    # Fetch positions from DB again to ensure ordering
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ticker FROM positions WHERE shares > 0")
    positions = {row[0].upper() for row in cur.fetchall()}
    cur.execute("SELECT DISTINCT ticker FROM unified_grades WHERE unified_grade >= 70")
    high_grade = {row[0].upper() for row in cur.fetchall()}
    cur.execute("SELECT DISTINCT ticker FROM vox_grades WHERE vox_grade >= 70")
    high_vox = {row[0].upper() for row in cur.fetchall()}
    conn.close()

    for t in tickers:
        if t in positions:
            prioritized.append((0, t))
        elif t in high_grade or t in high_vox:
            prioritized.append((1, t))
        else:
            prioritized.append((2, t))
    prioritized.sort()
    selected = [t for _, t in prioritized[:MAX_TICKERS]]

    total_stored = 0
    total_accessions = 0
    completed = 0

    def process_one(ticker):
        nonlocal completed
        accs, stored = fetch_and_store_for_ticker(ticker, cik_map)
        completed += 1
        print(f"[{completed}/{len(selected)}] {ticker} — inspected {accs}, stored {stored}")
        return accs, stored

    # Polite parallel: 3 concurrent requests, then 0.25s pause per batch
    workers = min(3, len(selected))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(process_one, t): t for t in selected}
        for future in as_completed(futures):
            try:
                accs, stored = future.result()
                total_accessions += accs
                total_stored += stored
            except Exception as e:
                print(f"    ⚠️  Worker error for {futures[future]}: {e}")

    print(f"\nInspected {total_accessions} Form 4 filings, stored {total_stored} new transactions")
    generate_insider_report()
    return total_stored


if __name__ == '__main__':
    run_insider_monitor()
