#!/usr/bin/env python3
"""
Enrich held book (+ optional outside) with FMP free fundamentals.
- Respects ~250 calls/day free tier (2 calls/ticker default)
- Stores fmp_fundamentals table
- Updates latest vox_grades.fundamental_score when FMP score available
- Writes Obsidian Fund-Scores-LATEST.md
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vox_fmp import (  # noqa: E402
    compute_fund_score,
    get_financial_scores,
    get_growth,
    get_ratios_ttm,
)

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
CALL_BUDGET = 220  # leave headroom under free 250
SLEEP = 0.35


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or "railway",
        user=os.environ.get("DB_USER") or "postgres",
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def ensure_table(cur):
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS fmp_fundamentals (
            ticker TEXT PRIMARY KEY,
            fund_score DOUBLE PRECISION,
            piotroski DOUBLE PRECISION,
            altman_z DOUBLE PRECISION,
            net_margin DOUBLE PRECISION,
            roe DOUBLE PRECISION,
            debt_equity DOUBLE PRECISION,
            rev_growth DOUBLE PRECISION,
            notes TEXT,
            raw_json JSONB,
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def held_tickers(cur) -> List[str]:
    cur.execute(
        """
        SELECT ticker, COALESCE(live_value_usd, live_value, 0) AS v
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
        ORDER BY v DESC
        """
    )
    rows = cur.fetchall()
    # skip crypto-ish symbols without FMP equity coverage
    skip = {
        "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "BONK",
        "AVAX", "DOT", "LINK", "SHIB", "PENGU", "MORPHO", "VANA", "VAULTA",
        "MIRROR_TOTAL", "CASH",
    }
    out = []
    for r in rows:
        t = (r["ticker"] or "").upper()
        if t in skip or t.startswith("MIRROR"):
            continue
        out.append(t)
    return out


def enrich_ticker(ticker: str, with_growth: bool = False):
    calls = 0
    ratios = get_ratios_ttm(ticker)
    calls += 1
    time.sleep(SLEEP)
    scores = get_financial_scores(ticker)
    calls += 1
    time.sleep(SLEEP)
    growth = None
    if with_growth:
        try:
            growth = get_growth(ticker)
            calls += 1
            time.sleep(SLEEP)
        except Exception:
            pass
    computed = compute_fund_score(ratios, scores, growth, None)
    return computed, calls, {"ratios": ratios, "scores": scores, "growth": growth}


def main():
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    ensure_table(cur)
    conn.commit()

    tickers = held_tickers(cur)
    # Outside ideas if file exists — light touch
    outside_path = OBS / "Outside-Ideas-LATEST.md"
    extra = []
    if outside_path.exists():
        for line in outside_path.read_text().splitlines():
            if line.startswith("· **") or line.startswith("- **"):
                # · **DUOL** g70
                try:
                    part = line.split("**")[1]
                    extra.append(part.upper())
                except Exception:
                    pass
    # unique priority: held first
    seen = set()
    ordered = []
    for t in tickers + extra:
        if t not in seen:
            seen.add(t)
            ordered.append(t)

    budget = CALL_BUDGET
    results = []
    errors = []
    for i, t in enumerate(ordered):
        need = 3 if i < 25 else 2  # growth for top 25
        if budget < need:
            break
        try:
            computed, used, raw = enrich_ticker(t, with_growth=(i < 25))
            budget -= used
            if computed.get("fund_score") is None:
                errors.append((t, "no_score"))
                continue
            import json as _json

            cur.execute(
                """
                INSERT INTO fmp_fundamentals
                  (ticker, fund_score, piotroski, altman_z, net_margin, roe, debt_equity,
                   rev_growth, notes, raw_json, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb, NOW())
                ON CONFLICT (ticker) DO UPDATE SET
                  fund_score=EXCLUDED.fund_score,
                  piotroski=EXCLUDED.piotroski,
                  altman_z=EXCLUDED.altman_z,
                  net_margin=EXCLUDED.net_margin,
                  roe=EXCLUDED.roe,
                  debt_equity=EXCLUDED.debt_equity,
                  rev_growth=EXCLUDED.rev_growth,
                  notes=EXCLUDED.notes,
                  raw_json=EXCLUDED.raw_json,
                  updated_at=NOW()
                """,
                (
                    t,
                    computed["fund_score"],
                    computed.get("piotroski"),
                    computed.get("altman_z"),
                    computed.get("net_margin"),
                    computed.get("roe"),
                    computed.get("debt_equity"),
                    computed.get("rev_growth"),
                    computed.get("notes"),
                    _json.dumps(
                        {
                            "scores": raw.get("scores"),
                            "growth": raw.get("growth"),
                            "ratios_sample": {
                                k: (raw.get("ratios") or {}).get(k)
                                for k in (
                                    "netProfitMarginTTM",
                                    "returnOnEquityTTM",
                                    "debtToEquityTTM",
                                    "currentRatioTTM",
                                )
                            },
                        }
                    ),
                ),
            )
            # patch latest grade fundamental_score
            cur.execute(
                """
                UPDATE vox_grades g SET fundamental_score = %s
                WHERE g.ticker = %s
                  AND g.generated_at = (
                    SELECT MAX(generated_at) FROM vox_grades WHERE ticker = %s
                  )
                """,
                (computed["fund_score"], t, t),
            )
            results.append((t, computed["fund_score"], computed.get("notes")))
        except Exception as e:
            msg = str(e)
            if "402" in msg or "Premium" in msg or "subscription" in msg.lower():
                errors.append((t, "free_tier_symbol_restricted"))
            else:
                errors.append((t, msg[:120]))
            budget = max(0, budget - 1)

    conn.commit()

    # report
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results.sort(key=lambda x: -x[1])
    lines = [
        f"# FMP Fund Scores — {day}",
        "",
        "_Hygiene fundamentals from FMP free stable API. Not auto-trade edge._",
        "",
        f"Enriched: **{len(results)}** · Errors: **{len(errors)}** · Call budget left ~{budget}",
        "",
        "## Top fund scores (held/outside)",
    ]
    for t, s, n in results[:25]:
        lines.append(f"- **{t}** {s:.0f} — {n}")
    lines += ["", "## Bottom (weak fundamentals)"]
    for t, s, n in results[-10:]:
        lines.append(f"- **{t}** {s:.0f} — {n}")
    if errors:
        lines += ["", "## Errors / skipped"]
        for t, e in errors[:15]:
            lines.append(f"- {t}: {e}")
    lines += [
        "",
        "## Policy",
        "- Grades remain hygiene ranking",
        "- FMP free ~250 calls/day; this job prioritizes held book",
        "- Upgrade to FMP Starter only if this layer stays valuable",
    ]
    OBS.mkdir(parents=True, exist_ok=True)
    (OBS / "Fund-Scores-LATEST.md").write_text("\n".join(lines) + "\n")
    (OBS / f"Fund-Scores-{day}.md").write_text("\n".join(lines) + "\n")

    print(f"📊 **FMP Fund Enrich** — {len(results)} tickers · errors {len(errors)}")
    for t, s, n in results[:8]:
        print(f"· {t} fund={s:.0f} ({n})")
    if results:
        avg = sum(x[1] for x in results) / len(results)
        print(f"Avg fund score: {avg:.1f}")
    print(f"Obsidian: memory/brain/Fund-Scores-LATEST")
    conn.close()
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
