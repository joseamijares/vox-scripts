#!/usr/bin/env python3
"""
VOX Filing/Transcript Summarizer
Reads long-form SEC filings, earnings transcripts, or other documents from
PostgreSQL or local text, chunks them if necessary, and uses the workhorse
router (deepseek-v4-pro with fallback) to extract a concise one-line catalyst.

Outputs are written to Obsidian `memory/catalysts/{TICKER}-YYYY-MM-DD.md` and
optionally stored back to a `catalysts` table.

This task is advisory-only: it produces research notes, not signals.
"""
from __future__ import annotations
import os, sys, re, json
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
CATALYST_DIR = OBSIDIAN_VOX / "memory" / "catalysts"
CATALYST_DIR.mkdir(parents=True, exist_ok=True)

DB_HOST = os.environ.get('DB_HOST', 'acela.proxy.rlwy.net')
DB_PORT = int(os.environ.get('DB_PORT', '35577'))
DB_NAME = os.environ.get('DB_NAME', 'railway')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD') or os.environ.get('PGPASSWORD')

MAX_CHARS = 12000
AUTO_MARKER = "<!-- vox-catalyst -->"


def connect_db():
    return psycopg2.connect(host=DB_HOST, port=DB_PORT, database=DB_NAME,
                            user=DB_USER, password=DB_PASSWORD)


def ensure_catalysts_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalysts (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            source TEXT,
            source_url TEXT,
            catalyst_type VARCHAR(50),
            summary TEXT,
            sentiment VARCHAR(20),
            generated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            confidence INT DEFAULT 0
        )
    """)


def fetch_recent_filings(cursor, limit=10):
    """Default source: SEC EDGAR Form 4 filings from insider_trades."""
    cursor.execute("""
        SELECT DISTINCT ON (ticker, form4_url)
            ticker,
            form4_url AS source_url,
            transaction_date AS event_date,
            MAX(created_at) OVER (PARTITION BY ticker, form4_url) AS created_at
        FROM insider_trades
        WHERE form4_url IS NOT NULL
          AND transaction_date >= CURRENT_DATE - INTERVAL '14 days'
        ORDER BY ticker, form4_url, created_at DESC
        LIMIT %s
    """, (limit,))
    return cursor.fetchall()


def fetch_filing_text(url: str) -> str:
    """Fetch raw text from an SEC filing URL."""
    import requests
    headers = {"User-Agent": "VOX Research vox@example.com"}
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            # Normalize XML spacing into readable text
            text = resp.text
            # Collapse multiple whitespace but preserve some structure
            text = re.sub(r'\n\s+', ' ', text)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()
    except Exception as e:
        return f"[Error fetching {url}: {e}]"
    return ""


def summarize_text(ticker: str, source: str, text: str, transaction_rows: list | None = None, catalyst_type: str = "SEC Filing") -> dict:
    if not text or len(text) < 50:
        return {"summary": "", "sentiment": "neutral", "confidence": 0}

    # Add structured transaction context if available
    txn_context = ""
    if transaction_rows:
        summaries = []
        for row in transaction_rows:
            summaries.append(
                f"{row.get('insider_name')} ({row.get('insider_title')}) {row.get('transaction_type')} "
                f"{row.get('shares')} shares at ${row.get('price_per_share')}"
            )
        txn_context = "\n".join(summaries)

    truncated = text[:MAX_CHARS]
    system_prompt = """You are a disciplined equity research analyst. Given a SEC filing excerpt and a structured transaction summary, produce a concise one-line catalyst summary and a sentiment label.

Output ONLY valid JSON with no markdown, no explanation, and no preamble. Use this exact schema:
{"summary": "one-line catalyst", "sentiment": "bullish|bearish|neutral", "confidence": 0-100}

The summary should be under 25 words, state the material development, and be actionable."""

    user_prompt = f"""Ticker: {ticker}
Source: {source}
Type: {catalyst_type}

Structured transactions:
{txn_context}

Excerpt:
{truncated}

Output JSON only."""

    result = workhorse_draft(system_prompt, user_prompt, max_tokens=300, temperature=0.3,
                             script_name="vox_filing_summarizer")
    content = result.get('content') or ''

    # Try to extract JSON block; if that fails, treat as raw summary and parse fields heuristically
    json_match = re.search(r'\{.*?\}', content, re.S)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
        except Exception:
            parsed = {"summary": content.strip(), "sentiment": "neutral", "confidence": 50}
    else:
        parsed = {"summary": content.strip(), "sentiment": "neutral", "confidence": 50}

    # If summary still looks like JSON or is a prefix fragment, fall back to the whole content
    if not parsed.get('summary') or parsed['summary'].startswith('{'):
        parsed['summary'] = content.strip().replace('{', '').replace('}', '').strip()

    parsed['summary'] = re.sub(r'\s+', ' ', str(parsed.get('summary', ''))).strip()
    parsed['sentiment'] = parsed.get('sentiment', 'neutral').lower()
    parsed['confidence'] = max(0, min(100, int(parsed.get('confidence', 50) or 50)))
    return parsed


def write_obsidian_catalyst(ticker: str, source: str, source_url: str, catalyst_type: str,
                            summary: str, sentiment: str, confidence: int, date_str: str):
    filename = f"{ticker.upper()}-{date_str}.md"
    path = CATALYST_DIR / filename
    frontmatter = f"""---
ticker: {ticker}
catalyst_type: {catalyst_type}
source: {source}
source_url: {source_url}
sentiment: {sentiment}
confidence: {confidence}
date: {date_str}
---
"""
    body = f"""
## Catalyst Summary
{AUTO_MARKER}
*{datetime.now().strftime("%Y-%m-%d %H:%M")}*

{summary}

- **Sentiment:** {sentiment}
- **Confidence:** {confidence}/100
- **Source:** [{source}]({source_url})
"""
    path.write_text(frontmatter + body)
    return path


def main(limit: int = 10, store_db: bool = True):
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        ensure_catalysts_table(cursor)
        filings = fetch_recent_filings(cursor, limit=limit)
        if not filings:
            print("No recent filings to summarize.")
            return

        updated = 0
        for row in filings:
            ticker = row['ticker'].upper()
            url = row['source_url']
            event_date = row['event_date'].strftime('%Y-%m-%d') if row['event_date'] else datetime.now().strftime('%Y-%m-%d')
            text = fetch_filing_text(url)
            if not text or len(text) < 200:
                print(f"SKIP {ticker}: no usable text from {url}")
                continue

            cursor.execute("""
                SELECT *
                FROM insider_trades
                WHERE ticker = %s AND form4_url = %s
            """, (ticker, url))
            txns = cursor.fetchall()

            parsed = summarize_text(ticker, f"SEC Form 4 ({event_date})", text, transaction_rows=txns, catalyst_type="SEC Form 4")
            if not parsed['summary']:
                print(f"FAIL {ticker}: no summary generated")
                continue

            path = write_obsidian_catalyst(ticker, f"SEC Form 4 ({event_date})", url, "SEC Form 4",
                                           parsed['summary'], parsed['sentiment'], parsed['confidence'], event_date)

            if store_db:
                cursor.execute("""
                    INSERT INTO catalysts (ticker, source, source_url, catalyst_type, summary, sentiment, confidence)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (ticker, f"SEC Form 4 ({event_date})", url, "SEC Form 4",
                      parsed['summary'], parsed['sentiment'], parsed['confidence']))

            updated += 1
            print(f"OK {ticker}: {parsed['summary'][:80]}... (sentiment={parsed['sentiment']}, confidence={parsed['confidence']})")
            print(f"   -> {path}")

        conn.commit()
        print(f"Summarized {updated} catalysts.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='VOX Filing/Transcript Summarizer')
    parser.add_argument('--limit', type=int, default=10, help='Max filings to summarize')
    parser.add_argument('--no-db', action='store_true', help='Only write to Obsidian, do not store to DB')
    args = parser.parse_args()
    main(limit=args.limit, store_db=not args.no_db)
