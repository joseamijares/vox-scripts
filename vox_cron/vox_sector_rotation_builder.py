#!/usr/bin/env python3
"""
VOX Sector Rotation Builder v0.1
Pure SQL workflow: composite sector ranking from momentum + rotation + market regime.
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

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "SectorRotation"


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sector_rotation_scores (
            id SERIAL PRIMARY KEY,
            sector TEXT NOT NULL,
            snapshot_date DATE NOT NULL,
            momentum_score NUMERIC(5,2),
            rotation_score NUMERIC(5,2),
            composite_rank NUMERIC(5,2) NOT NULL,
            regime_flag TEXT,
            top_tickers TEXT[],
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(sector, snapshot_date)
        );
    """)


def compute_scores(cur):
    cur.execute("""
        WITH latest_momentum AS (
            SELECT DISTINCT ON (sector)
                sector, avg_grade, avg_return_5d, avg_return_20d, momentum_score, top_tickers, buy_count, sell_count
            FROM sector_momentum
            ORDER BY sector, computed_at DESC
        ),
        latest_rotation AS (
            SELECT DISTINCT ON (sector)
                sector, relative_strength, return_1m, momentum_score AS rotation_momentum, rotation_signal, rank
            FROM sector_rotation
            ORDER BY sector, created_at DESC
        ),
        regime AS (
            SELECT regime, confidence, vix_level, spy_trend, fed_stance
            FROM market_regime
            ORDER BY created_at DESC
            LIMIT 1
        )
        SELECT
            m.sector,
            m.momentum_score AS mom,
            m.avg_grade,
            r.relative_strength,
            r.rotation_momentum,
            r.rank AS rotation_rank,
            m.top_tickers,
            rg.regime,
            rg.spy_trend
        FROM latest_momentum m
        LEFT JOIN latest_rotation r ON m.sector = r.sector
        CROSS JOIN regime rg
    """)
    rows = cur.fetchall()

    scores = []
    for row in rows:
        sector, mom, avg_grade, rs, rot_mom, rot_rank, top_tickers, regime, spy_trend = row
        mom_norm = min(100, float(mom or 0) * 1.5)  # scale momentum score
        grade_norm = float(avg_grade or 0)
        rs_norm = min(100, float(rs or 0) * 50 + 50) if rs else 50  # relative strength centered
        rot_norm = min(100, float(rot_mom or 0) * 1.5)
        composite = round((mom_norm * 0.35 + grade_norm * 0.25 + rs_norm * 0.20 + rot_norm * 0.20), 2)

        # regime flag
        flag = "neutral"
        if regime and spy_trend:
            regime_str = (regime or "").lower()
            spy_str = (spy_trend or "").lower()
            if "bull" in regime_str or "risk_on" in regime_str or "up" in spy_str:
                if mom_norm >= 60:
                    flag = "overweight"
            elif "bear" in regime_str or "risk_off" in regime_str or "down" in spy_str:
                if mom_norm <= 40:
                    flag = "underweight"

        scores.append({
            "sector": sector,
            "momentum_score": round(mom_norm, 2),
            "rotation_score": round(rot_norm, 2),
            "composite_rank": composite,
            "regime_flag": flag,
            "top_tickers": top_tickers or [],
            "regime": regime,
            "spy_trend": spy_trend,
        })

    return sorted(scores, key=lambda x: x["composite_rank"], reverse=True)


def persist_scores(cur, scores):
    for s in scores:
        cur.execute("""
            INSERT INTO sector_rotation_scores
            (sector, snapshot_date, momentum_score, rotation_score, composite_rank, regime_flag, top_tickers)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)
            ON CONFLICT (sector, snapshot_date) DO UPDATE SET
                momentum_score = EXCLUDED.momentum_score,
                rotation_score = EXCLUDED.rotation_score,
                composite_rank = EXCLUDED.composite_rank,
                regime_flag = EXCLUDED.regime_flag,
                top_tickers = EXCLUDED.top_tickers,
                created_at = NOW()
        """, (s["sector"], s["momentum_score"], s["rotation_score"], s["composite_rank"], s["regime_flag"], s["top_tickers"]))


def write_obsidian(scores):
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OBSIDIAN_DIR / f"SectorRotation-{date_str}.md"

    regime = scores[0]["regime"] if scores else "N/A"
    spy_trend = scores[0]["spy_trend"] if scores else "N/A"

    lines = [
        f"# VOX Sector Rotation — {date_str}",
        "",
        f"**Regime:** {regime} | **SPY Trend:** {spy_trend}",
        "",
        "| Rank | Sector | Composite | Momentum | Rotation | Regime Flag | Top Tickers |",
        "|------|--------|-----------|----------|----------|-------------|-------------|",
    ]
    for i, s in enumerate(scores, 1):
        top = ", ".join(s["top_tickers"][:5])
        lines.append(
            f"| {i} | {s['sector']} | {s['composite_rank']:.1f} | {s['momentum_score']:.1f} | {s['rotation_score']:.1f} | {s['regime_flag']} | {top} |"
        )

    lines.extend(["", "## Overweight / Underweight"])
    for s in scores:
        if s["regime_flag"] in ("overweight", "underweight"):
            lines.append(f"- **{s['sector']}** → {s['regime_flag']} (composite {s['composite_rank']:.1f})")

    path.write_text("\n".join(lines))
    return path


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_table(cur)
        scores = compute_scores(cur)
        persist_scores(cur, scores)
        conn.commit()
        path = write_obsidian(scores)
        print(f"Sector Rotation Builder: {len(scores)} sectors")
        for s in scores[:5]:
            print(f"  {s['sector']}: composite={s['composite_rank']:.1f} flag={s['regime_flag']}")
        print(f"Obsidian note: {path}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
