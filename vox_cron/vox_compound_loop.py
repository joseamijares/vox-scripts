#!/usr/bin/env python3
"""
VOX compound loop — REAL issues only. Quiet when clean.

Checks:
  1) DB reachable + book non-empty
  2) Material holdings price_asof freshness
  3) Dashboard /api/health
  4) Critical secrets present
  5) Enabled cron last_status failures
  6) price_history max date not ancient

If any FAIL → write Compound-Issues-LATEST.md + stdout report (exit 1).
If all PASS → short OK line, exit 0 (cron can stay quiet on local).

Usage:
  python3 vox_cron/vox_compound_loop.py
  python3 vox.py compound
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT = OBS / "Compound-Issues-LATEST.md"
DASH = "https://web-production-9e321.up.railway.app"


def main() -> int:
    now = datetime.now(timezone.utc)
    issues: list[str] = []
    notes: list[str] = []

    # secrets
    for k in ("DB_HOST", "DB_PASSWORD", "FMP_API_KEY"):
        if not os.environ.get(k):
            issues.append(f"secret missing: {k}")

    # db + pricing freshness on material names
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 35577)),
            dbname=os.environ.get("DB_NAME", "railway"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
            connect_timeout=15,
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            """
            SELECT COUNT(*) n,
                   ROUND(SUM(COALESCE(live_value_usd,live_value,0))::numeric,0) aum
            FROM positions
            WHERE COALESCE(live_value_usd,live_value,0)>0 OR COALESCE(shares,0)>0
            """
        )
        row = cur.fetchone() or {}
        n, aum = int(row.get("n") or 0), float(row.get("aum") or 0)
        if n < 10 or aum < 1000:
            issues.append(f"book looks empty/broken: n={n} aum={aum}")
        else:
            notes.append(f"book n={n} aum=${aum:,.0f}")

        cur.execute(
            """
            SELECT ticker, price_asof, COALESCE(live_value_usd,live_value,0) v
            FROM positions
            WHERE COALESCE(live_value_usd,live_value,0) > 0
            """
        )
        aum = aum or 1
        stale_mat = []
        for r in cur.fetchall():
            t = (r.get("ticker") or "").upper()
            if t in ("MIRROR_TOTAL", "CASH") or " " in t:
                continue
            w = 100 * float(r["v"] or 0) / aum
            if w < 1.0:
                continue
            asof = r.get("price_asof")
            if asof is None:
                stale_mat.append(f"{r['ticker']} (no asof, {w:.1f}%)")
                continue
            if asof.tzinfo is None:
                asof = asof.replace(tzinfo=timezone.utc)
            age_h = (now - asof).total_seconds() / 3600
            # after hours allow 36h; during week if >48h always bad
            if age_h > 48:
                stale_mat.append(f"{r['ticker']} asof {age_h:.0f}h ({w:.1f}%)")
        if stale_mat:
            issues.append("stale material prices: " + ", ".join(stale_mat[:12]))
        else:
            notes.append("material prices fresh enough")

        cur.execute("SELECT MAX(date) d FROM price_history")
        d = (cur.fetchone() or {}).get("d")
        if not d or (now.date() - d).days > 5:
            issues.append(f"price_history max date stale: {d}")
        else:
            notes.append(f"price_history max={d}")
        conn.close()
    except Exception as e:
        issues.append(f"db error: {e}")

    # dashboard
    try:
        with urllib.request.urlopen(f"{DASH}/api/health", timeout=20) as r:
            data = json.loads(r.read().decode())
        if data.get("status") != "ok":
            issues.append(f"dashboard health not ok: {data}")
        else:
            notes.append(f"dashboard ok v{data.get('version')}")
    except Exception as e:
        issues.append(f"dashboard unreachable: {e}")

    # cron failures among enabled
    try:
        jobs = json.loads(
            (Path.home() / ".hermes" / "cron" / "jobs.json").read_text()
        )["jobs"]
        bad = []
        for j in jobs:
            if not j.get("enabled"):
                continue
            st = j.get("last_status")
            if st is None:
                continue
            if st not in ("ok", "success", "completed", 0, "0"):
                bad.append(f"{j.get('name')}:{st}")
        if bad:
            issues.append("cron failures: " + ", ".join(bad[:15]))
        else:
            notes.append(f"enabled crons ok-ish ({sum(1 for j in jobs if j.get('enabled'))})")
    except Exception as e:
        issues.append(f"cron inspect error: {e}")

    # report
    OBS.mkdir(parents=True, exist_ok=True)
    if not issues:
        msg = f"VOX compound OK {now.strftime('%Y-%m-%d %H:%M UTC')} · " + " · ".join(notes[:4])
        print(msg)
        # keep last good stamp
        OUT.write_text(
            f"# Compound Issues — clean\n\n_{now.isoformat()}_\n\nNo real issues.\n\n"
            + "\n".join(f"- {n}" for n in notes)
            + "\n"
        )
        return 0

    lines = [
        f"# Compound Issues — {now.strftime('%Y-%m-%d')}",
        "",
        f"_Generated {now.isoformat()} · real failures only_",
        "",
        "## Issues (fix these)",
    ]
    for i, iss in enumerate(issues, 1):
        lines.append(f"{i}. {iss}")
    lines += ["", "## Context", *[f"- {n}" for n in notes], "", "## Suggested agent actions"]
    lines.append("1. `python3 vox.py prices` if stale prices")
    lines.append("2. `python3 vox.py secrets` if secret missing")
    lines.append("3. Check Railway if dashboard down")
    lines.append("4. `python3 vox.py test` after fix")
    lines.append("5. Do **not** add new AI layers / councils")
    text = "\n".join(lines) + "\n"
    OUT.write_text(text)
    print("VOX COMPOUND ISSUES")
    for iss in issues:
        print(" !", iss)
    print("Full:", OUT)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
