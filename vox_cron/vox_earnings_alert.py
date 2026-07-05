#!/usr/bin/env python3
"""
VOX Earnings Alert — Daily pre-market warning for held/watchlist tickers reporting earnings today or tomorrow.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import psycopg2
from datetime import datetime, timedelta

DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = 35577
DB_NAME = 'railway'
DB_USER = 'postgres'


def get_db_password():
    return os.environ.get('DB_PASSWORD', os.environ.get('PGPASSWORD', ''))


def connect_db():
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=get_db_password()
    )


def get_alert_rows():
    conn = connect_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT e.ticker, e.report_date, e.report_time, e.eps_estimate, e.importance, e.status,
               COALESCE(ug.unified_grade, vg.vox_grade, 0) AS grade,
               p.shares IS NOT NULL AS held
        FROM earnings_calendar e
        LEFT JOIN (
            SELECT DISTINCT ON (ticker) ticker, unified_grade
            FROM unified_grades
            ORDER BY ticker, computed_at DESC
        ) ug ON ug.ticker = e.ticker
        LEFT JOIN (
            SELECT DISTINCT ON (ticker) ticker, vox_grade
            FROM vox_grades
            ORDER BY ticker, generated_at DESC
        ) vg ON vg.ticker = e.ticker
        LEFT JOIN (SELECT DISTINCT ticker, shares FROM positions WHERE shares > 0) p ON p.ticker = e.ticker
        WHERE e.report_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '1 day'
          AND (p.shares IS NOT NULL OR EXISTS (SELECT 1 FROM watchlist w WHERE w.ticker = e.ticker))
        ORDER BY e.report_date, e.importance_score DESC, e.ticker
    """)
    rows = cur.fetchall()
    conn.close()
    return rows


def action_suggestion(grade, held, importance, eps_estimate):
    if held:
        if grade >= 70:
            return "Consider trimming before earnings"
        elif grade >= 50:
            return "Hold through, but watch closely"
        else:
            return "Consider exiting before earnings"
    else:
        if grade >= 70 and eps_estimate is not None:
            return "Worth watching for a post-earnings dip"
        else:
            return "Monitor only"


def generate():
    rows = get_alert_rows()
    date_str = datetime.now().strftime('%Y-%m-%d')
    out_dir = Path.home() / 'Documents' / 'Obsidian' / 'VOX' / 'Earnings'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f'EarningsAlert-{date_str}.md'

    lines = [
        f"# VOX Earnings Alert — {date_str}",
        "",
        f"**Tickers reporting today or tomorrow:** {len(rows)}",
        "",
        "| Ticker | Date | Time | EPS Est | Grade | Held | Importance | Suggestion |",
        "|--------|------|------|---------|-------|------|------------|------------|",
    ]
    alerts = []
    for r in rows:
        ticker, rd, rt, eps, importance, status, grade, held = r
        eps_s = f"${eps:.2f}" if eps is not None else 'N/A'
        suggestion = action_suggestion(grade, held, importance, eps)
        lines.append(f"| {ticker} | {rd} | {rt or 'TNS'} | {eps_s} | {grade or 0:.0f} | {'Yes' if held else 'No'} | {importance} | {suggestion} |")
        alerts.append(f"{ticker} ({'held' if held else 'watch'}): reports {rt or 'TNS'} {rd} — {suggestion}")

    if not rows:
        lines.append("")
        lines.append("_No positions or watchlist tickers reporting today or tomorrow._")

    path.write_text('\n'.join(lines))
    print('\n'.join(lines))
    print(f"📝 Obsidian alert: {path}")
    return rows


if __name__ == '__main__':
    generate()
