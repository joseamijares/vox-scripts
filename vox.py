#!/usr/bin/env python3
"""
VOX single entrypoint — agentic-friendly CLI.

  python3 vox.py status|ops|prices|secrets|test|morning|advisor|bakeoff|compound|log|help

Advisor (soft only — never Ops SSOT):
  python3 vox.py advisor                  # Kimi k3 (cron default; DeepSeek fallback)
  python3 vox.py advisor --model sonnet5  # best hard critique (bakeoff winner)
  python3 vox.py advisor --model glm52    # draft only
  python3 vox.py advisor --model all      # run three
  python3 vox.py bakeoff                  # full A/B rubric

Decision log (JOS-269 — you execute):
  python3 vox.py log                      # seed today from Ops Card
  python3 vox.py log status
  python3 vox.py log did "BUY ALAB small" --ticker ALAB --broker GBM
  python3 vox.py log skip 1 --reason "wait multi-broker re-import"
  python3 vox.py log thesis DUOL --side short --reason "AI disruption"

AUM track (daily snaps + WTD/WoW + MTM estimate → VOX alerts bot):
  python3 vox.py aum
  python3 vox.py aum --cashflow 5000 --note "deposit GBM"
  python3 vox.py aum --lookback 5
  python3 vox.py aum --no-send          # files only
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _run(script: str, args: list[str] | None = None, timeout: int = 300) -> int:
    cmd = [sys.executable, str(ROOT / script)] + (args or [])
    env = os.environ.copy()
    try:
        import hermes_secrets_bootstrap  # noqa: F401
    except Exception:
        pass
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(ROOT), env=env, timeout=timeout)
    return r.returncode


def cmd_status() -> int:
    import hermes_secrets_bootstrap  # noqa: F401
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from datetime import datetime

    print("=== VOX STATUS ===")
    print(f"secrets DB_HOST={bool(os.environ.get('DB_HOST'))} FMP={bool(os.environ.get('FMP_API_KEY'))}")
    try:
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
                   COUNT(price_asof) a,
                   ROUND(SUM(COALESCE(live_value_usd, live_value, 0))::numeric, 0) aum
            FROM positions
            WHERE COALESCE(live_value_usd, live_value, 0) > 0 OR COALESCE(shares, 0) > 0
            """
        )
        print("book", dict(cur.fetchone()))
        cur.execute("SELECT MAX(date) d FROM price_history")
        print("price_history_max", cur.fetchone()["d"])
        cur.execute("SELECT COUNT(*) c FROM fmp_fundamentals")
        print("fmp_rows", cur.fetchone()["c"])
        conn.close()
        print("db OK")
    except Exception as e:
        print("db FAIL", e)
        return 1

    ops = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain/Daily-Ops-LATEST.md"
    print("ops_card", "present" if ops.exists() else "MISSING", ops)
    dec = Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions"
    dpath = dec / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    print("decision_log_today", "present" if dpath.exists() else "MISSING", dpath)
    return 0


def cmd_ops() -> int:
    return _run("vox_cron/vox_daily_ops_card.py", timeout=120)


def cmd_prices() -> int:
    return _run("vox_cron/vox_pricing_refresh_held_run.py", timeout=600)


def cmd_secrets() -> int:
    return _run("vault_to_env.py", ["--write", "--replace-env"], timeout=600)


def cmd_test() -> int:
    import hermes_secrets_bootstrap  # noqa: F401
    import urllib.request
    import json

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        if cond:
            print("PASS", name, detail)
        else:
            print("FAIL", name, detail)
            fails += 1

    check("DB_PASSWORD", bool(os.environ.get("DB_PASSWORD")))
    check("FMP_API_KEY", bool(os.environ.get("FMP_API_KEY")))
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=int(os.environ.get("DB_PORT", 35577)),
            dbname=os.environ.get("DB_NAME", "railway"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
            connect_timeout=12,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        check("db_ping", cur.fetchone()[0] == 1)
        conn.close()
    except Exception as e:
        check("db_ping", False, e)

    try:
        with urllib.request.urlopen(
            "https://web-production-9e321.up.railway.app/api/health", timeout=20
        ) as r:
            data = json.loads(r.read().decode())
        check("dashboard_health", data.get("status") == "ok", data.get("version"))
    except Exception as e:
        check("dashboard_health", False, e)

    try:
        with urllib.request.urlopen(
            "https://web-production-9e321.up.railway.app/api/ops", timeout=25
        ) as r:
            data = json.loads(r.read().decode())
        check("dashboard_ops", "aum" in data, f"aum={data.get('aum')}")
    except Exception as e:
        check("dashboard_ops", False, e)

    ops = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain/Daily-Ops-LATEST.md"
    check("ops_file", ops.exists())

    print("RESULT", "OK" if fails == 0 else f"{fails} failures")
    return 0 if fails == 0 else 1


def cmd_morning() -> int:
    return _run("vox_cron/vox_morning_context.py", timeout=300)


def cmd_advisor() -> int:
    extra = sys.argv[2:]
    return _run("vox_cron/vox_k3_advisor.py", args=extra, timeout=900)


def cmd_bakeoff() -> int:
    return _run("vox_cron/vox_advisor_bakeoff.py", timeout=900)


def cmd_compound() -> int:
    return _run("vox_cron/vox_compound_loop.py", timeout=120)


def cmd_log() -> int:
    extra = sys.argv[2:] if len(sys.argv) > 2 else []
    return _run("vox_cron/vox_decision_log.py", args=extra, timeout=120)


def cmd_aum() -> int:
    extra = sys.argv[2:] if len(sys.argv) > 2 else []
    return _run("vox_cron/vox_aum_track.py", args=extra, timeout=180)


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "help").lower()
    if cmd in ("help", "-h", "--help"):
        print(__doc__)
        print(
            "Commands: status | ops | prices | secrets | test | morning | "
            "advisor [--model k3|sonnet5|glm52|all] | bakeoff | compound | "
            "log [seed|status|did|skip|thesis] | aum [--cashflow N] | help"
        )
        return 0
    table = {
        "status": cmd_status,
        "ops": cmd_ops,
        "prices": cmd_prices,
        "secrets": cmd_secrets,
        "test": cmd_test,
        "morning": cmd_morning,
        "advisor": cmd_advisor,
        "bakeoff": cmd_bakeoff,
        "compound": cmd_compound,
        "log": cmd_log,
        "aum": cmd_aum,
    }
    if cmd not in table:
        print("unknown command", cmd)
        return 2
    try:
        return table[cmd]()
    except subprocess.TimeoutExpired:
        print("TIMEOUT", cmd)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
