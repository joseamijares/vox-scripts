#!/usr/bin/env python3
"""
VOX MANDATORY CHECKLIST SYSTEM
Run before investment recommendations. Uses psycopg2 + env password
(never blanks PGPASSWORD). Exit 0 if can recommend, 1 if blocked.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

HERMES_HOME = Path.home() / ".hermes"
OUT_DIR = HERMES_HOME / "scripts" / "vox_cron"

# Core tables that must work for recommendations
CORE_TABLES = [
    "unified_grades",
    "vox_grades",
    "positions",
    "broker_positions",
    "market_regime",
    "technical_signals",
    "sp500_grades",
    "macro_signals",
    "sector_momentum",
    "trade_signals",
    "council_deliberations",
    "price_history",
    "discovery_queue",
    "grade_alerts",
    "earnings_calendar",
]

# Optional / legacy — warn only if missing
OPTIONAL_TABLES = [
    "watchlist",
    "watchlist_grades",
    "pattern_alerts",
    "sentiment_scores",
    "sp500_sector_leaders",
    "commodity_prices",
    "alerts",
    "journal",
    "system_logs",
    "geopolitical_events",
    "supply_chain_events",
    "weather_patterns",
    "weather_risks",
    "plays",
    "broker_accounts",
    "broker_holdings",
    "broker_status",
    "sp500_alerts",
    "sp500_universe",
    "cron_runs",
]


def load_env() -> None:
    envp = HERMES_HOME / ".env"
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    load_env()
    pw = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    if not pw or len(pw) < 5:
        raise RuntimeError("DB password missing/short — set DB_PASSWORD or PGPASSWORD in ~/.hermes/.env")
    # Never blank password
    os.environ["PGPASSWORD"] = pw
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        dbname=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pw,
        connect_timeout=15,
    )
    return conn, conn.cursor(cursor_factory=RealDictCursor)


class VoxMandatoryChecklist:
    def __init__(self) -> None:
        self.checklist: Dict[str, Any] = {}
        self.data: Dict[str, Any] = {}
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.conn = None
        self.cur = None

    def run_checklist(self) -> Dict[str, Any]:
        print("=" * 70)
        print("VOX MANDATORY CHECKLIST — RUNNING CORE SYSTEMS")
        print("=" * 70)
        print()
        self.check_db_connection()
        if self.checklist.get("db_connection"):
            self.query_tables()
            self.cross_validate()
            self.data_freshness()
        self.external_research()
        self.social_research()
        return self.final_verification()

    def check_db_connection(self) -> None:
        print("[1/6] Checking database connection...")
        try:
            self.conn, self.cur = connect()
            self.cur.execute("SELECT NOW() AS n")
            self.cur.fetchone()
            self.checklist["db_connection"] = True
            print("  ✅ Database connected (psycopg2)")
        except Exception as e:
            self.checklist["db_connection"] = False
            self.errors.append(f"Database connection failed: {e}")
            print(f"  ❌ Database connection FAILED: {e}")

    def _count(self, table: str):
        assert self.cur is not None
        try:
            self.cur.execute(f"SELECT COUNT(*) AS c FROM {table}")
            return int(self.cur.fetchone()["c"])
        except Exception as e:
            self.conn.rollback()
            raise e

    def query_tables(self) -> None:
        print("[2/6] Querying core + optional tables...")
        core_ok = 0
        for table in CORE_TABLES:
            try:
                count = self._count(table)
                self.data[table] = {"status": "OK", "count": count}
                core_ok += 1
                print(f"  ✅ {table}: {count} rows")
            except Exception as e:
                self.data[table] = {"status": "ERROR", "error": str(e)}
                self.errors.append(f"Core table {table} failed: {e}")
                print(f"  ❌ {table}: FAILED — {e}")
        for table in OPTIONAL_TABLES:
            try:
                count = self._count(table)
                self.data[table] = {"status": "OK", "count": count}
                print(f"  · {table}: {count} rows")
            except Exception as e:
                self.conn.rollback()
                self.data[table] = {"status": "MISSING", "error": str(e)}
                self.warnings.append(f"Optional table {table}: {e}")
                print(f"  ⚠️  {table}: missing/failed (optional)")
        self.checklist["all_tables_queried"] = core_ok == len(CORE_TABLES)
        self.checklist["core_tables_ok"] = core_ok

    def cross_validate(self) -> None:
        print("[3/6] Cross-validating grade sources...")
        assert self.cur is not None
        try:
            self.cur.execute(
                """
                WITH latest AS (
                  SELECT DISTINCT ON (ticker) ticker, vox_grade, generated_at
                  FROM vox_grades
                  ORDER BY ticker, generated_at DESC
                )
                SELECT l.ticker, l.vox_grade, s.vox_grade AS sp500_grade,
                       ABS(l.vox_grade - s.vox_grade) AS diff
                FROM latest l
                JOIN sp500_grades s ON l.ticker = s.ticker
                WHERE l.generated_at > NOW() - INTERVAL '7 days'
                  AND ABS(COALESCE(l.vox_grade,0) - COALESCE(s.vox_grade,0)) > 12
                ORDER BY diff DESC
                LIMIT 10
                """
            )
            rows = self.cur.fetchall()
            if rows:
                self.warnings.append(f"{len(rows)} VOX vs SP500 grade gaps >12 (sample)")
                print(f"  ⚠️  {len(rows)} grade gaps >12 (showing up to 5)")
                for r in rows[:5]:
                    print(f"     {r['ticker']}: vox={r['vox_grade']} sp={r['sp500_grade']} Δ={r['diff']}")
            else:
                print("  ✅ No major VOX/SP500 gaps in latest grades")
        except Exception as e:
            self.conn.rollback()
            self.warnings.append(f"Cross-validate grades failed: {e}")
            print(f"  ⚠️  grade cross-check failed: {e}")

        try:
            self.cur.execute(
                """
                SELECT COUNT(*) AS c FROM positions p
                LEFT JOIN unified_grades u ON p.ticker = u.ticker
                WHERE COALESCE(p.shares,0) > 0 AND u.ticker IS NULL
                """
            )
            missing = int(self.cur.fetchone()["c"])
            if missing:
                self.warnings.append(f"{missing} active positions missing unified_grades")
                print(f"  ⚠️  {missing} active positions without unified grade")
            else:
                print("  ✅ All active positions have unified grades (or none active)")
        except Exception as e:
            self.conn.rollback()
            self.warnings.append(str(e))

        self.checklist["cross_validated"] = True

    def data_freshness(self) -> None:
        print("[3b/6] Freshness gate...")
        assert self.cur is not None
        try:
            from vox_cron.vox_data_health import assess_data_health, health_summary

            h = assess_data_health()
            self.data["data_health"] = h
            print(health_summary(h))
            if h.get("score", 0) < 50:
                self.warnings.append(f"Data confidence LOW ({h.get('score')}/100)")
            if h.get("blocking"):
                for b in h["blocking"]:
                    self.warnings.append(f"Health blocking: {b}")
            self.checklist["data_health_score"] = h.get("score")
        except Exception as e:
            self.warnings.append(f"data_health failed: {e}")
            print(f"  ⚠️  data_health: {e}")

    def external_research(self) -> None:
        print("[4/6] External research...")
        # Prefer intel artifacts over manual
        intel = HERMES_HOME / "cron" / "output" / "intel"
        day = datetime.now().strftime("%Y-%m-%d")
        found = []
        for name in ("breaking", "policy", "morning", "weather"):
            p = intel / f"{name}_{day}.json"
            if p.exists():
                found.append(name)
        if found:
            self.checklist["external_research"] = f"ARTIFACTS:{','.join(found)}"
            print(f"  ✅ Intel artifacts today: {', '.join(found)}")
        else:
            self.checklist["external_research"] = "MANUAL_OR_STALE"
            self.warnings.append("No intel artifacts for today yet")
            print("  ⚠️  No today intel artifacts")

    def social_research(self) -> None:
        print("[5/6] Social / X layer...")
        intel = HERMES_HOME / "cron" / "output" / "intel"
        day = datetime.now().strftime("%Y-%m-%d")
        social = intel / f"social_{day}.json"
        if social.exists():
            self.checklist["social_research"] = "ARTIFACT"
            print("  ✅ Social intel artifact present")
        else:
            self.checklist["social_research"] = "OPTIONAL"
            print("  · Social optional / may be quiet")

    def final_verification(self) -> Dict[str, Any]:
        print("[6/6] Final verification...")
        all_complete = all(
            [
                self.checklist.get("db_connection", False),
                self.checklist.get("all_tables_queried", False),
                self.checklist.get("cross_validated", False),
            ]
        )
        can = all_complete and len(self.errors) == 0
        if can:
            print("  ✅ ALL CORE CHECKS PASSED")
            print("=" * 70)
            print("VOX CHECKLIST COMPLETE — RECOMMENDATION ALLOWED")
            print("=" * 70)
        else:
            print("  ❌ CHECKLIST FAILED")
            print("=" * 70)
            print("VOX CHECKLIST FAILED — NO RECOMMENDATION ALLOWED")
            print("=" * 70)
            for e in self.errors:
                print(f"  - {e}")
            for w in self.warnings[:10]:
                print(f"  ! {w}")
        if self.conn:
            self.conn.close()
        return {
            "checklist": self.checklist,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "can_recommend": can,
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    checklist = VoxMandatoryChecklist()
    result = checklist.run_checklist()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUT_DIR / f"checklist_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    # Strip huge nested health for compact save? keep full
    with open(output_file, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nResult saved to: {output_file}")
    sys.exit(0 if result.get("can_recommend") else 1)
