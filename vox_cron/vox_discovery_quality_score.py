#!/usr/bin/env python3
"""
VOX Discovery Queue Quality Score v0.1
Pure SQL scoring: prioritizes discovery_queue candidates by grade, technical,
pattern, smart-money, sector, sentiment, and trader signals. Writes to Railway
and Obsidian.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "Discovery"


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS discovery_priority (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            snapshot_date DATE NOT NULL,
            vox_grade NUMERIC(5,2),
            unified_grade NUMERIC(5,2),
            technical_score NUMERIC(5,2),
            pattern_score NUMERIC(5,2),
            insider_score NUMERIC(5,2),
            sector_score NUMERIC(5,2),
            sentiment_score NUMERIC(5,2),
            trader_mentions INT,
            composite_priority NUMERIC(5,2) NOT NULL,
            reasons TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, snapshot_date)
        );
    """)


def score_candidates(cur):
    cur.execute("""
        WITH dq AS (
            SELECT DISTINCT ON (ticker) ticker, vox_grade, discovery_source, created_at
            FROM discovery_queue
            WHERE status = 'pending'
            ORDER BY ticker, created_at DESC
        ),
        vg AS (
            SELECT DISTINCT ON (ticker) ticker, vox_grade, sector
            FROM vox_grades
            ORDER BY ticker, generated_at DESC
        ),
        ug AS (
            SELECT DISTINCT ON (ticker) ticker, unified_grade
            FROM unified_grades
            ORDER BY ticker, computed_at DESC
        ),
        ts AS (
            SELECT DISTINCT ON (ticker) ticker, score
            FROM technical_signals
            ORDER BY ticker, computed_at DESC
        ),
        pa AS (
            SELECT ticker, COUNT(*) AS pattern_count, MAX(conviction) AS max_conviction
            FROM pattern_alerts
            WHERE detected_at >= NOW() - INTERVAL '7 days'
            GROUP BY ticker
        ),
        sms AS (
            SELECT ticker, combined_score
            FROM smart_money_signals
            WHERE signal_date = CURRENT_DATE
        ),
        srs AS (
            SELECT sector, composite_rank
            FROM sector_rotation_scores
            WHERE snapshot_date = CURRENT_DATE
        ),
        smom AS (
            SELECT DISTINCT ON (sector) sector, avg_grade
            FROM sector_momentum
            ORDER BY sector, computed_at DESC
        ),
        sent AS (
            SELECT DISTINCT ON (ticker) ticker, mention_count, bullish_ratio, vox_score
            FROM sentiment_scores
            ORDER BY ticker, computed_at DESC
        ),
        tm AS (
            SELECT ticker, COUNT(*) AS mention_count
            FROM trader_mentions
            WHERE mention_date >= NOW() - INTERVAL '7 days'
            GROUP BY ticker
        )
        SELECT DISTINCT ON (dq.ticker)
            dq.ticker,
            COALESCE(vg.vox_grade, dq.vox_grade) AS vox_grade,
            ug.unified_grade,
            ts.score AS technical_score,
            pa.pattern_count,
            pa.max_conviction,
            sms.combined_score AS insider_score,
            COALESCE(srs.composite_rank, smom.avg_grade) AS sector_score,
            sent.mention_count,
            sent.bullish_ratio,
            sent.vox_score,
            tm.mention_count AS trader_mentions,
            dq.discovery_source
        FROM dq
        LEFT JOIN vg ON dq.ticker = vg.ticker
        LEFT JOIN ug ON dq.ticker = ug.ticker
        LEFT JOIN ts ON dq.ticker = ts.ticker
        LEFT JOIN pa ON dq.ticker = pa.ticker
        LEFT JOIN sms ON dq.ticker = sms.ticker
        LEFT JOIN smom ON smom.sector = vg.sector
        LEFT JOIN srs ON srs.sector = vg.sector
        LEFT JOIN sent ON dq.ticker = sent.ticker
        LEFT JOIN tm ON dq.ticker = tm.ticker
        ORDER BY dq.ticker
    """)
    return cur.fetchall()


def normalize(val, min_val=0, max_val=100):
    if val is None:
        return 0
    return max(0, min(100, (float(val) - min_val) / (max_val - min_val) * 100))


def compute(rows):
    results = []
    for r in rows:
        (
            ticker, vox_grade, unified_grade, tech_score,
            pattern_count, max_conviction, insider_score,
            sector_score, mention_count, bullish_ratio, sentiment_vox, trader_mentions, source
        ) = r

        vox_norm = normalize(vox_grade)
        unified_norm = normalize(unified_grade)
        tech_norm = normalize(tech_score)
        pattern_norm = normalize((pattern_count or 0) * 10 + (max_conviction or 0) * 10)
        insider_norm = normalize(insider_score)
        sector_norm = normalize(sector_score)
        sentiment_norm = 0
        if bullish_ratio is not None:
            sentiment_norm = float(bullish_ratio) * 100
        else:
            sentiment_norm = normalize(sentiment_vox)
        trader_norm = min(100, (trader_mentions or 0) * 10)
        mention_norm = min(100, (mention_count or 0) * 2)

        composite = round(
            vox_norm * 0.25 +
            unified_norm * 0.15 +
            tech_norm * 0.15 +
            pattern_norm * 0.10 +
            insider_norm * 0.10 +
            sector_norm * 0.10 +
            sentiment_norm * 0.05 +
            max(trader_norm, mention_norm) * 0.10,
            2
        )

        reasons = []
        if vox_norm >= 70:
            reasons.append(f"strong vox grade {vox_grade}")
        if insider_norm >= 50:
            reasons.append(f"smart money signal {insider_score}")
        if sector_norm >= 55:
            reasons.append(f"strong sector {sector_score}")
        if tech_norm >= 70:
            reasons.append(f"technical score {tech_score}")
        if trader_norm >= 30:
            reasons.append(f"trader buzz {trader_mentions}")
        if not reasons:
            reasons.append("default discovery candidate")

        results.append({
            "ticker": ticker,
            "vox_grade": vox_grade,
            "unified_grade": unified_grade,
            "technical_score": tech_score,
            "pattern_score": pattern_norm,
            "insider_score": insider_score,
            "sector_score": sector_score,
            "sentiment_score": sentiment_norm,
            "trader_mentions": trader_mentions,
            "composite_priority": composite,
            "reasons": ", ".join(reasons),
        })

    return sorted(results, key=lambda x: x["composite_priority"], reverse=True)


def persist(cur, results):
    for r in results:
        cur.execute("""
            INSERT INTO discovery_priority
            (ticker, snapshot_date, vox_grade, unified_grade, technical_score,
             pattern_score, insider_score, sector_score, sentiment_score,
             trader_mentions, composite_priority, reasons)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, snapshot_date) DO UPDATE SET
                vox_grade = EXCLUDED.vox_grade,
                unified_grade = EXCLUDED.unified_grade,
                technical_score = EXCLUDED.technical_score,
                pattern_score = EXCLUDED.pattern_score,
                insider_score = EXCLUDED.insider_score,
                sector_score = EXCLUDED.sector_score,
                sentiment_score = EXCLUDED.sentiment_score,
                trader_mentions = EXCLUDED.trader_mentions,
                composite_priority = EXCLUDED.composite_priority,
                reasons = EXCLUDED.reasons,
                created_at = NOW()
        """, (
            r["ticker"], r["vox_grade"], r["unified_grade"], r["technical_score"],
            r["pattern_score"], r["insider_score"], r["sector_score"],
            r["sentiment_score"], r["trader_mentions"], r["composite_priority"],
            r["reasons"]
        ))


def write_obsidian(results):
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OBSIDIAN_DIR / f"DiscoveryQuality-{date_str}.md"

    lines = [
        f"# VOX Discovery Queue Quality — {date_str}",
        "",
        "| Rank | Ticker | Priority | VOX | Unified | Tech | Insider | Sector | Trader | Reasons |",
        "|------|--------|----------|-----|---------|------|---------|--------|--------|---------|",
    ]
    for i, r in enumerate(results[:20], 1):
        vg_str = f"{r['vox_grade']:.1f}" if r['vox_grade'] is not None else ''
        ug_str = f"{r['unified_grade']:.1f}" if r['unified_grade'] is not None else ''
        tech_str = f"{r['technical_score']:.1f}" if r['technical_score'] is not None else ''
        ins_str = f"{r['insider_score']:.1f}" if r['insider_score'] is not None else ''
        sec_str = f"{r['sector_score']:.1f}" if r['sector_score'] is not None else ''
        tm_str = f"{r['trader_mentions']:.0f}" if r['trader_mentions'] is not None else ''
        lines.append(
            f"| {i} | {r['ticker']} | {r['composite_priority']:.1f} | "
            f"{vg_str} | {ug_str} | {tech_str} | {ins_str} | {sec_str} | {tm_str} | {r['reasons']} |"
        )

    lines.append("\n## Promote to Council")
    top = [r for r in results if r["composite_priority"] >= 60]
    if top:
        for r in top:
            lines.append(f"- {r['ticker']} (priority {r['composite_priority']:.1f})")
    else:
        lines.append("- No candidates crossed the 60 priority threshold today.")

    path.write_text("\n".join(lines))
    return path


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_table(cur)
        rows = score_candidates(cur)
        results = compute(rows)
        persist(cur, results)
        conn.commit()
        path = write_obsidian(results)
        print(f"Discovery Queue Quality: {len(results)} candidates")
        for r in results[:5]:
            print(f"  {r['ticker']}: priority={r['composite_priority']:.1f}")
        print(f"Obsidian note: {path}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
