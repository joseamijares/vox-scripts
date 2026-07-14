#!/usr/bin/env python3
"""
VOX Data Health Gate — run before any LLM-facing synthesis query.

Exposes assess_data_health() → 0-100 confidence + blocking/warnings.
Uses latest-per-ticker grade freshness (Pattern 7) and psycopg2 (not bare psql).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))

HERMES_HOME = Path.home() / ".hermes"
GRADE_FRESHNESS_HOURS = 72
ALERT_FRESHNESS_HOURS = 48


def _load_env() -> None:
    envp = HERMES_HOME / ".env"
    if not envp.exists():
        return
    for line in envp.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _password() -> str:
    _load_env()
    pw = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""
    return pw


def _connect():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    pw = _password()
    if not pw:
        raise RuntimeError("DB password missing (DB_PASSWORD/PGPASSWORD / ~/.hermes/.env)")
    conn = psycopg2.connect(
        host=os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("PGPORT", "35577")),
        dbname=os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("PGUSER", "postgres"),
        password=pw,
        connect_timeout=15,
    )
    return conn, conn.cursor(cursor_factory=RealDictCursor)


def _scalar(cur, sql: str, default: Any = 0):
    try:
        cur.execute(sql)
        row = cur.fetchone()
        if not row:
            return default
        return list(row.values())[0]
    except Exception:
        cur.connection.rollback()
        return default


def _table_exists(cur, name: str) -> bool:
    cur.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
        (name,),
    )
    return bool(cur.fetchone()["exists"])


def assess_data_health() -> Dict[str, Any]:
    """Return a single health score and detailed findings."""
    warnings: List[str] = []
    blocking: List[str] = []

    try:
        conn, cur = _connect()
    except Exception as e:
        return {
            "score": 0,
            "grade_freshness_hours": 9999.0,
            "grade_stale_pct": 100.0,
            "total_grades": 0,
            "fresh_grades": 0,
            "unified_hours": 9999.0,
            "price_hours": 9999.0,
            "alerts_fresh": False,
            "has_smart_money": False,
            "has_sector_rotation": False,
            "has_discovery": False,
            "has_institutional": False,
            "has_macro": False,
            "missing_tables": [],
            "warnings": [],
            "blocking": [f"DB connection failed: {e}"],
            "generated_at": datetime.now().isoformat(),
        }

    # Pattern 7 fix: latest grade per ticker, not historical row counts
    total_tickers = int(
        _scalar(
            cur,
            "SELECT COUNT(*) FROM (SELECT ticker FROM vox_grades GROUP BY ticker) s",
            0,
        )
        or 0
    )
    fresh_tickers = int(
        _scalar(
            cur,
            f"""
            SELECT COUNT(*) FROM (
              SELECT ticker FROM vox_grades
              GROUP BY ticker
              HAVING MAX(generated_at) > NOW() - INTERVAL '{GRADE_FRESHNESS_HOURS} hours'
            ) s
            """,
            0,
        )
        or 0
    )
    stale_tickers = max(0, total_tickers - fresh_tickers)
    grade_stale_pct = round(100.0 * stale_tickers / total_tickers, 2) if total_tickers else 0.0

    # Age of freshest latest row + age of oldest latest row
    grade_freshness_hours = float(
        _scalar(
            cur,
            """
            SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(last_g))) / 3600.0, 9999)
            FROM (SELECT MAX(generated_at) AS last_g FROM vox_grades GROUP BY ticker) t
            """,
            9999,
        )
        or 9999
    )
    oldest_latest_hours = float(
        _scalar(
            cur,
            """
            SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MIN(last_g))) / 3600.0, 9999)
            FROM (SELECT MAX(generated_at) AS last_g FROM vox_grades GROUP BY ticker) t
            """,
            9999,
        )
        or 9999
    )

    unified_hours = float(
        _scalar(
            cur,
            "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(computed_at))) / 3600.0, 9999) FROM unified_grades",
            9999,
        )
        or 9999
    )
    unified_count = int(_scalar(cur, "SELECT COUNT(*) FROM unified_grades", 0) or 0)

    price_hours = float(
        _scalar(
            cur,
            "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(date)::timestamp)) / 3600.0, 9999) FROM price_history",
            9999,
        )
        or 9999
    )
    # Active book price coverage (positions with shares>0)
    active_price = _scalar(
        cur,
        """
        WITH active AS (
          SELECT DISTINCT ticker FROM positions WHERE COALESCE(shares,0) > 0
        )
        SELECT json_build_object(
          'active', (SELECT COUNT(*) FROM active),
          'fresh4', (
            SELECT COUNT(*) FROM active a
            JOIN (SELECT ticker, MAX(date) d FROM price_history GROUP BY ticker) ph
              ON ph.ticker = a.ticker AND ph.d >= CURRENT_DATE - 4
          ),
          'missing', (
            SELECT COUNT(*) FROM active a
            LEFT JOIN (SELECT DISTINCT ticker FROM price_history) ph ON ph.ticker = a.ticker
            WHERE ph.ticker IS NULL
          )
        )
        """,
        {},
    )
    if isinstance(active_price, str):
        import json

        try:
            active_price = json.loads(active_price)
        except Exception:
            active_price = {}
    if not isinstance(active_price, dict):
        active_price = {}

    tech_hours = float(
        _scalar(
            cur,
            "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(computed_at))) / 3600.0, 9999) FROM technical_signals",
            9999,
        )
        or 9999
    )
    sp500_hours = float(
        _scalar(
            cur,
            "SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(computed_at))) / 3600.0, 9999) FROM sp500_grades",
            9999,
        )
        or 9999
    )

    signal_count = int(_scalar(cur, "SELECT COUNT(*) FROM signal_performance", 0) or 0) if _table_exists(cur, "signal_performance") else 0
    smart_count = 0
    for t in ("smart_money_signals", "smart_money"):
        if _table_exists(cur, t):
            smart_count = int(_scalar(cur, f"SELECT COUNT(*) FROM {t}", 0) or 0)
            break
    sector_count = 0
    for t in ("sector_rotation_scores", "sector_rotation", "sector_momentum"):
        if _table_exists(cur, t):
            sector_count = int(_scalar(cur, f"SELECT COUNT(*) FROM {t}", 0) or 0)
            break
    discovery_count = 0
    for t in ("discovery_priority", "discovery_queue"):
        if _table_exists(cur, t):
            discovery_count = int(_scalar(cur, f"SELECT COUNT(*) FROM {t}", 0) or 0)
            break
    inst_count = int(_scalar(cur, "SELECT COUNT(*) FROM institutional_data", 0) or 0) if _table_exists(cur, "institutional_data") else 0
    macro_count = int(_scalar(cur, "SELECT COUNT(*) FROM macro_signals", 0) or 0) if _table_exists(cur, "macro_signals") else 0
    alerts_recent = int(
        _scalar(
            cur,
            f"SELECT COUNT(*) FROM grade_alerts WHERE triggered_at > NOW() - INTERVAL '{ALERT_FRESHNESS_HOURS} hours'",
            0,
        )
        or 0
    ) if _table_exists(cur, "grade_alerts") else 0

    positions_active = int(
        _scalar(cur, "SELECT COUNT(*) FROM positions WHERE COALESCE(shares,0) > 0 AND COALESCE(live_value_usd,0) > 0", 0)
        or 0
    )
    breaking_note = Path.home() / "Documents/Obsidian/VOX/vox/memory/decisions/Breaking-LATEST.md"
    has_breaking = breaking_note.exists() and (
        datetime.now().timestamp() - breaking_note.stat().st_mtime < 36 * 3600
    )

    conn.close()

    # Blocking / warnings — latest-per-ticker rules
    if grade_stale_pct >= 50:
        blocking.append(f"{grade_stale_pct:.0f}% of tickers have latest grade older than {GRADE_FRESHNESS_HOURS}h ({stale_tickers}/{total_tickers})")
    elif grade_stale_pct >= 15:
        warnings.append(f"{grade_stale_pct:.0f}% of tickers have stale latest grades ({stale_tickers}/{total_tickers})")
    elif stale_tickers > 0:
        warnings.append(f"{stale_tickers} tickers with latest grade older than {GRADE_FRESHNESS_HOURS}h")

    if unified_count == 0:
        blocking.append("unified_grades is empty")
    elif unified_hours > 36:
        blocking.append(f"unified_grades is {unified_hours:.1f}h old")
    elif unified_hours > 24:
        warnings.append(f"unified_grades is {unified_hours:.1f}h old")

    if tech_hours > 72:
        warnings.append(f"technical_signals is {tech_hours:.1f}h old")
    if sp500_hours > 14 * 24:
        blocking.append(f"sp500_grades is {sp500_hours/24:.1f}d old")
    elif sp500_hours > 8 * 24:
        warnings.append(f"sp500_grades is {sp500_hours/24:.1f}d old")

    if price_hours > 96:
        warnings.append(f"price_history max date is {price_hours:.1f}h old")
    active_n = int(active_price.get("active") or 0)
    fresh4 = int(active_price.get("fresh4") or 0)
    missing_ph = int(active_price.get("missing") or 0)
    if active_n and fresh4 / active_n < 0.4:
        warnings.append(f"Active book price_history thin: {fresh4}/{active_n} fresh≤4d, {missing_ph} missing")

    if signal_count == 0:
        warnings.append("signal_performance is empty")
    if smart_count == 0:
        warnings.append("smart_money table empty/missing")
    if sector_count == 0:
        warnings.append("sector tables empty/missing")
    if discovery_count == 0:
        warnings.append("discovery tables empty/missing")
    if inst_count == 0:
        warnings.append("institutional_data is empty")
    if macro_count == 0:
        warnings.append("macro_signals is empty")
    if alerts_recent == 0:
        warnings.append(f"No grade_alerts in last {ALERT_FRESHNESS_HOURS}h")
    if positions_active == 0:
        blocking.append("No active positions with value")

    score = 100
    score -= min(40, int(grade_stale_pct * 0.6))
    if unified_hours > 36:
        score -= 20
    elif unified_hours > 24:
        score -= 8
    if tech_hours > 48:
        score -= 5
    if active_n and fresh4 / max(active_n, 1) < 0.4:
        score -= 8
    if inst_count == 0:
        score -= 3
    if macro_count == 0:
        score -= 3
    if alerts_recent == 0:
        score -= 2
    if smart_count == 0 or sector_count == 0 or discovery_count == 0:
        score -= 3
    score -= 8 * len(blocking)
    score = max(0, min(100, score))
    if blocking:
        score = min(score, 49)

    return {
        "score": score,
        "grade_freshness_hours": round(grade_freshness_hours, 1),
        "oldest_latest_grade_hours": round(oldest_latest_hours, 1),
        "grade_stale_pct": grade_stale_pct,
        "total_grades": total_tickers,
        "fresh_grades": fresh_tickers,
        "stale_tickers": stale_tickers,
        "unified_hours": round(unified_hours, 1),
        "unified_count": unified_count,
        "price_hours": round(price_hours, 1),
        "tech_hours": round(tech_hours, 1),
        "sp500_hours": round(sp500_hours, 1),
        "active_price_coverage": active_price,
        "alerts_fresh": alerts_recent > 0,
        "has_smart_money": smart_count > 0,
        "has_sector_rotation": sector_count > 0,
        "has_discovery": discovery_count > 0,
        "has_institutional": inst_count > 0,
        "has_macro": macro_count > 0,
        "has_breaking_note": has_breaking,
        "positions_active": positions_active,
        "missing_tables": [],
        "warnings": warnings,
        "blocking": blocking,
        "generated_at": datetime.now().isoformat(),
    }


def health_summary(health: Dict[str, Any]) -> str:
    level = "HIGH" if health["score"] >= 80 else "MEDIUM" if health["score"] >= 50 else "LOW"
    cov = health.get("active_price_coverage") or {}
    lines = [
        f"**Data Confidence: {health['score']}/100 ({level})**",
        (
            f"- Latest grades/ticker: {health.get('fresh_grades', 0)}/{health.get('total_grades', 0)} fresh "
            f"(<72h) | stale {health.get('grade_stale_pct', 0)}% | newest age {health.get('grade_freshness_hours')}h"
        ),
        f"- Unified: {health.get('unified_count', 0)} rows, {health.get('unified_hours', '?')}h old | Tech: {health.get('tech_hours', '?')}h | SP500: {round((health.get('sp500_hours') or 0)/24, 1)}d",
        f"- Active price_history: {cov.get('fresh4', '?')}/{cov.get('active', '?')} ≤4d, missing {cov.get('missing', '?')}",
        f"- SmartMoney: {health['has_smart_money']} | Sector: {health['has_sector_rotation']} | Discovery: {health['has_discovery']} | Breaking note: {health.get('has_breaking_note')}",
        f"- Institutional: {health['has_institutional']} | Macro: {health['has_macro']} | Alerts 48h: {health['alerts_fresh']}",
    ]
    if health.get("blocking"):
        lines.append("- **Blocking issues:**")
        for b in health["blocking"]:
            lines.append(f"  - {b}")
    if health.get("warnings"):
        lines.append("- **Warnings:**")
        for w in health["warnings"]:
            lines.append(f"  - {w}")
    return "\n".join(lines)


if __name__ == "__main__":
    h = assess_data_health()
    print(health_summary(h))
    print(f"\nSCORE={h['score']}")
