#!/usr/bin/env python3
"""
VOX Watchlist Thesis Updater
Fetches watchlist entries with missing/null one-line theses, uses the workhorse router
(moonshotai/kimi-k2 with fallback) to draft a concise one-line thesis per ticker, and writes:
1. `watchlist.thesis` in the database (only if currently blank or marked as auto-generated)
2. Atomic ticker pages in Obsidian `memory/theses/{TICKER}.md` (appends a machine-drafted block)
Preserves user-edited notes by only overwriting the `<!-- vox-thesis -->` block.
"""
import os, sys, json, re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_workhorse import workhorse_draft, thinking_draft

import argparse
import psycopg2
from psycopg2.extras import RealDictCursor

OBSIDIAN_VOX = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox"
THESIS_DIR = OBSIDIAN_VOX / "memory" / "theses"
THESIS_DIR.mkdir(parents=True, exist_ok=True)

AUTO_THESIS_MARKER = "<!-- vox-thesis -->"
AUTO_THESIS_PREFIX = "[Auto]"

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = int(os.environ.get('DB_PORT', '35577'))
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD') or os.environ.get('PGPASSWORD')


def connect_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def fetch_candidates(cursor):
    cursor.execute("""
        SELECT id, ticker, name, thesis, notes, grade, status
        FROM watchlist
        WHERE thesis IS NULL
           OR thesis = ''
           OR thesis ILIKE '%%small-cap under $2B list from X post%%'
           OR thesis ILIKE '%%VOX Top 10 Hybrid%%'
        ORDER BY added_at DESC
        LIMIT 5
    """)
    return cursor.fetchall()


def fetch_ticker_context(cursor, ticker):
    # latest grade
    cursor.execute("""
        SELECT vox_grade, action, generated_at
        FROM vox_grades
        WHERE ticker = %s
        ORDER BY generated_at DESC LIMIT 1
    """, (ticker,))
    grade = cursor.fetchone()
    # latest grade_alert
    cursor.execute("""
        SELECT old_grade, new_grade, old_action, new_action, triggered_at
        FROM grade_alerts
        WHERE ticker = %s
        ORDER BY triggered_at DESC LIMIT 1
    """, (ticker,))
    alert = cursor.fetchone()
    # latest technical signal
    cursor.execute("""
        SELECT score, alpha_zoo_score, alpha_factor_count, computed_at
        FROM technical_signals
        WHERE ticker = %s
        ORDER BY computed_at DESC LIMIT 1
    """, (ticker,))
    tech = cursor.fetchone()
    # latest insider cluster
    cursor.execute("""
        SELECT SUM(shares) as shares, COUNT(DISTINCT insider_name) as insiders, MIN(transaction_date) as first_buy, MAX(transaction_date) as last_buy
        FROM insider_trades
        WHERE ticker = %s AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY ticker
    """, (ticker,))
    insider = cursor.fetchone()
    return grade, alert, tech, insider


def build_prompt(ticker, name, grade, alert, tech, insider) -> str:
    name = name or ticker
    pieces = [f"Ticker: {ticker} ({name})"]
    if grade:
        pieces.append(f"Latest VOX grade: {grade['action']} {grade['vox_grade']} (generated {grade['generated_at']})")
    if alert:
        delta = alert['new_grade'] - alert['old_grade'] if alert['new_grade'] is not None and alert['old_grade'] is not None else 0
        pieces.append(f"Latest grade-swing alert: {alert['old_grade']} -> {alert['new_grade']} ({alert['old_action']} -> {alert['new_action']}, Δ{delta}) on {alert['triggered_at']}")
    if tech:
        pieces.append(f"Latest technical signal: score={tech['score']}, alpha_zoo={tech['alpha_zoo_score']}, factors={tech['alpha_factor_count']} (computed {tech['computed_at']})")
    if insider:
        pieces.append(f"Insider buying (30d): {insider['shares']} shares across {insider['insiders']} insiders, {insider['first_buy']} to {insider['last_buy']}")
    return "\n".join(pieces)


def draft_thesis(ticker, name, context_text) -> str:
    system_prompt = """You are a concise equity research assistant. Given the context below, write a single one-line investment thesis for the ticker. It must be under 25 words, state the core bull or bear case, and be actionable. No hedging, no generic filler. Output ONLY the thesis line."""
    user_prompt = f"""Context:
{context_text}

Write one concise thesis line for {ticker} ({name or ticker})."""
    result = workhorse_draft(system_prompt, user_prompt, max_tokens=80, temperature=0.35,
                             script_name="vox_watchlist_thesis")
    content = result.get('content') or ''
    content = content.strip().replace('\n', ' ')
    # Strip surrounding quotes if the model returned quoted text
    if len(content) >= 2 and content[0] == '"' and content[-1] == '"':
        content = content[1:-1]
    return content


def is_auto_thesis(thesis: str) -> bool:
    if not thesis:
        return True
    return thesis.startswith(AUTO_THESIS_PREFIX) or AUTO_THESIS_MARKER in thesis


def update_db_thesis(cursor, wid, thesis):
    tagged = f"{AUTO_THESIS_PREFIX} {thesis} {AUTO_THESIS_MARKER}"
    cursor.execute("""
        UPDATE watchlist
        SET thesis = %s
        WHERE id = %s
    """, (tagged, wid))


def update_obsidian_thesis(ticker, thesis, name, context_text):
    path = THESIS_DIR / f"{ticker.upper()}.md"
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    block = f"""
## VOX-Generated Thesis
{AUTO_THESIS_MARKER}
*{date_str}*

{thesis}

_Context_:
```
{context_text}
```
"""
    if path.exists():
        text = path.read_text()
        # Replace existing vox-thesis block
        pattern = re.compile(rf"## VOX-Generated Thesis\n.*?{re.escape(AUTO_THESIS_MARKER)}.*?\n(?=## |\Z)", re.S)
        if pattern.search(text):
            text = pattern.sub(block.lstrip(), text)
        else:
            text = text.rstrip() + "\n" + block
        path.write_text(text)
    else:
        frontmatter = f"""---
ticker: {ticker}
name: {name or ticker}
updated: {date_str}
source: vox-watchlist-thesis
---
"""
        path.write_text(frontmatter + block)


def main(force: bool = False):
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        candidates = fetch_candidates(cursor)
        if not candidates:
            print("No watchlist candidates need thesis updates.")
            return
        updated = 0
        for row in candidates:
            wid = row['id']
            ticker = row['ticker'].upper()
            current = row['thesis'] or ''
            # Only update if blank or already auto-generated, unless --force
            if not force and not is_auto_thesis(current):
                print(f"SKIP {ticker}: user-edited thesis exists")
                continue
            grade, alert, tech, insider = fetch_ticker_context(cursor, ticker)
            context = build_prompt(ticker, row['name'], grade, alert, tech, insider)
            thesis = draft_thesis(ticker, row['name'], context)
            if not thesis:
                print(f"FAIL {ticker}: no thesis generated")
                continue
            update_db_thesis(cursor, wid, thesis)
            update_obsidian_thesis(ticker, thesis, row['name'], context)
            updated += 1
            print(f"OK {ticker}: {thesis[:80]}...")
        conn.commit()
        print(f"Updated {updated} theses.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VOX Watchlist Thesis Updater')
    parser.add_argument('--force', action='store_true', help='Regenerate theses even if user-edited')
    args = parser.parse_args()
    main(force=args.force)
