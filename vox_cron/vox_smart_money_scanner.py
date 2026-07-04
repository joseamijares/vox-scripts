#!/usr/bin/env python3
"""
VOX Smart Money Scanner v0.1
Prototype: detect clustered insider buying + institutional accumulation.
Pure SQL scoring; optional DeepSeek Flash note only on high-signal candidates.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import psycopg2
import psycopg2.extras

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

OBSIDIAN_DIR = Path.home() / "Documents" / "Obsidian" / "VOX" / "SmartMoney"


def ensure_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS smart_money_signals (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(20) NOT NULL,
            signal_date DATE NOT NULL,
            insider_score NUMERIC(5,2),
            institutional_score NUMERIC(5,2),
            combined_score NUMERIC(5,2) NOT NULL,
            signal_type VARCHAR(50),
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, signal_date)
        );
    """)


def compute_signals(cur):
    # Insider score: cluster of open-market purchase transactions in last 10 days
    cur.execute("""
        SELECT
            ticker,
            COUNT(*) AS buy_count,
            COUNT(DISTINCT insider_name) AS distinct_insiders,
            SUM(total_value) AS total_buy_value,
            MAX(CASE WHEN is_director OR is_officer OR is_10pct_owner THEN 1 ELSE 0 END) AS senior_buy,
            SUM(CASE
                WHEN importance = 'high' THEN 3
                WHEN importance = 'medium' THEN 2
                ELSE 1
            END) AS importance_points
        FROM insider_trades
        WHERE transaction_type IN ('P', 'BUY', 'Purchase')
          AND transaction_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY ticker
        HAVING COUNT(*) >= 1 OR SUM(total_value) >= 500000
    """)
    insider_rows = {r[0]: {
        "buy_count": r[1], "distinct_insiders": r[2], "total_buy_value": r[3], "senior_buy": r[4], "importance_points": r[5]
    } for r in cur.fetchall()}

    # Institutional score: net inflow as % of total flow, and absolute magnitude
    cur.execute("""
        SELECT DISTINCT ON (ticker)
            ticker,
            net_institutional_flow,
            institutional_inflow_3m,
            institutional_outflow_3m,
            top_10_holder_pct,
            short_interest_pct
        FROM institutional_data
        ORDER BY ticker, recorded_at DESC
    """)
    inst_rows = {r[0]: {
        "net_flow": r[1], "inflow": r[2], "outflow": r[3], "top10_pct": r[4], "short_pct": r[5]
    } for r in cur.fetchall()}

    # Combine scores
    tickers = set(insider_rows.keys()) | set(inst_rows.keys())
    def to_float(x):
        return float(x) if x is not None else None

    signals = []
    for t in tickers:
        iscore = 0.0
        idet_raw = insider_rows.get(t)
        idet = None
        if idet_raw:
            idet = {
                "buy_count": idet_raw["buy_count"],
                "distinct_insiders": idet_raw["distinct_insiders"],
                "total_buy_value": to_float(idet_raw["total_buy_value"]),
                "senior_buy": bool(idet_raw["senior_buy"]),
                "importance_points": idet_raw["importance_points"],
            }
            iscore = min(100, (
                idet["buy_count"] * 10 +
                idet["distinct_insiders"] * 15 +
                idet["importance_points"] * 5 +
                (20 if idet["senior_buy"] else 0) +
                min(30, (idet["total_buy_value"] or 0) / 1_000_000)
            ))

        sscore = 0.0
        sdet_raw = inst_rows.get(t)
        sdet = None
        if sdet_raw:
            sdet = {
                "net_flow": to_float(sdet_raw["net_flow"]),
                "inflow": to_float(sdet_raw["inflow"]),
                "outflow": to_float(sdet_raw["outflow"]),
                "top10_pct": to_float(sdet_raw["top10_pct"]),
                "short_pct": to_float(sdet_raw["short_pct"]),
            }
            if sdet["inflow"] and sdet["outflow"] and sdet["net_flow"] is not None:
                total = sdet["inflow"] + sdet["outflow"]
                if total > 0:
                    sscore = min(100, max(0, 50 + 50 * (sdet["net_flow"] / total)))

        combined = 0.6 * iscore + 0.4 * sscore
        signal_type = []
        if iscore >= 40:
            signal_type.append("insider_cluster")
        if sscore >= 60:
            signal_type.append("institutional_inflow")
        if not signal_type:
            continue

        signals.append({
            "ticker": t,
            "insider_score": round(iscore, 2),
            "institutional_score": round(sscore, 2),
            "combined_score": round(combined, 2),
            "signal_type": ", ".join(signal_type),
            "details": {
                "insider": idet,
                "institutional": sdet,
            }
        })

    return sorted(signals, key=lambda x: x["combined_score"], reverse=True)


def persist_signals(cur, signals):
    for s in signals:
        cur.execute("""
            INSERT INTO smart_money_signals
            (ticker, signal_date, insider_score, institutional_score, combined_score, signal_type, details)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, signal_date) DO UPDATE SET
                insider_score = EXCLUDED.insider_score,
                institutional_score = EXCLUDED.institutional_score,
                combined_score = EXCLUDED.combined_score,
                signal_type = EXCLUDED.signal_type,
                details = EXCLUDED.details,
                created_at = NOW()
        """, (s["ticker"], s["insider_score"], s["institutional_score"], s["combined_score"], s["signal_type"], psycopg2.extras.Json(s["details"])))


def write_obsidian(signals):
    OBSIDIAN_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = OBSIDIAN_DIR / f"SmartMoney-{date_str}.md"

    lines = [f"# VOX Smart Money Signals — {date_str}", ""]
    lines.append("| Rank | Ticker | Combined | Insider | Institutional | Type |")
    lines.append("|------|--------|----------|---------|---------------|------|")
    for i, s in enumerate(signals, 1):
        lines.append(f"| {i} | {s['ticker']} | {s['combined_score']:.1f} | {s['insider_score']:.1f} | {s['institutional_score']:.1f} | {s['signal_type']} |")

    lines.extend(["", "## Notes"])
    for s in signals:
        lines.append(f"- **{s['ticker']}**: {s['signal_type']}")
        if s['details']['insider']:
            d = s['details']['insider']
            lines.append(f"  - Insider: {d['buy_count']} buys, {d['distinct_insiders']} distinct buyers, ${d['total_buy_value']:,.0f} total value")
        if s['details']['institutional']:
            d = s['details']['institutional']
            lines.append(f"  - Institutional: net flow {d['net_flow']}, top10 holders {d['top10_pct']:.1f}%, short {d['short_pct']:.1f}%")

    path.write_text("\n".join(lines))
    return path


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    try:
        ensure_table(cur)
        signals = compute_signals(cur)
        persist_signals(cur, signals)
        conn.commit()
        path = write_obsidian(signals)
        print(f"Smart Money Scanner: {len(signals)} signals")
        for s in signals[:10]:
            print(f"  {s['ticker']}: combined={s['combined_score']:.1f} type={s['signal_type']}")
        print(f"Obsidian note: {path}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
