#!/usr/bin/env python3
"""
Ensure thesis stubs with kill criteria for material positions (≥2.5% or special).
Does not overwrite existing human theses — only creates missing stubs.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor

OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "theses"
MIN_W = 2.5


def main():
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or "railway",
        user=os.environ.get("DB_USER") or "postgres",
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=20,
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT ticker, COALESCE(live_value_usd, live_value, 0) AS v, grade, council, sector
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
        """
    )
    rows = cur.fetchall()
    conn.close()
    aum = sum(float(r["v"] or 0) for r in rows) or 1
    OBS.mkdir(parents=True, exist_ok=True)
    created = []
    for r in rows:
        t = (r["ticker"] or "").upper()
        w = 100 * float(r["v"] or 0) / aum
        if w < MIN_W and t not in ("BTC", "ETH"):
            continue
        if t in ("MIRROR_TOTAL", "TOTAL", "CASH") or t.startswith("MIRROR"):
            continue
        path = OBS / f"{t}.md"
        if path.exists() and path.stat().st_size > 80:
            continue
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path.write_text(
            f"""# Thesis — {t}

**Weight:** {w:.1f}% · **Grade:** {r.get('grade') or '—'} (hygiene) · **Council:** {r.get('council') or '—'}  
**Sector:** {r.get('sector') or '—'} · **Updated:** {day}

## Why we hold
- _TODO: one paragraph investment thesis (you + VOX)_

## Horizon
- [ ] LONG (3–7y core)
- [ ] MEDIUM (thesis-driven)
- [ ] SHORT (cleanup only)

## Kill criteria (pivot if true)
1. Thesis broken: ________________
2. Grade hygiene collapse &lt;40 with no recovery plan
3. Concentration breach / mandate fit lost
4. Better risk-adjusted use of capital outside book

## Review
- Next review: _{day}_
- Status: ACTIVE

## Notes
- Multi-broker never a sell reason
- Grades ≠ auto-sell
"""
        )
        created.append(t)

    print(f"📝 **Thesis stubs** — created {len(created)} for material names")
    if created:
        print("· " + ", ".join(created[:20]))
    else:
        print("· none missing")
    print(f"Dir: {OBS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
