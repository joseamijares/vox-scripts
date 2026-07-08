#!/usr/bin/env python3
"""
VOX Data Health Gate — run before any LLM-facing synthesis query.

Exposes a single function `assess_data_health()` that returns a structured
report with a 0-100 confidence score and a list of blocking/limiting issues.

Optimized to use a single DB round-trip to avoid slow repeated psql connections.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))

import json
import subprocess
import os
from datetime import datetime
from typing import Dict, List, Any

HERMES_HOME = Path.home() / ".hermes"
SCRIPT_DIR = HERMES_HOME / "scripts" / "vox_cron"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GRADE_FRESHNESS_HOURS = 72
ALERT_FRESHNESS_HOURS = 48

REQUIRED_TABLES = [
    "unified_grades",
    "price_history",
    "signal_performance",
]

WANTED_TABLES = [
    "institutional_data",
    "macro_signals",
]


def _db_password() -> str:
    pw = os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", ""))
    if not pw and (HERMES_HOME / ".env").exists():
        with open(HERMES_HOME / ".env") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key == "DB_PASSWORD":
                        pw = value
                        break
    return pw


def _query_single_json(sql: str) -> Dict[str, Any]:
    """Run a single SQL query returning one JSON object via psql."""
    pw = _db_password()
    env = os.environ.copy()
    env["PGPASSWORD"] = pw
    result = subprocess.run(
        [
            "psql", "-h", "acela.proxy.rlwy.net", "-p", "35577",
            "-U", "postgres", "-d", "railway", "-t", "-A", "-c", sql,
        ],
        capture_output=True, text=True, env=env,
    )
    if result.returncode != 0:
        print(f"SQL Error: {result.stderr}")
        return {}
    try:
        return json.loads(result.stdout.strip())
    except Exception:
        return {}


def assess_data_health() -> Dict[str, Any]:
    """Return a single health score and detailed findings."""
    warnings: List[str] = []
    blocking: List[str] = []

    sql = f"""
    SELECT json_build_object(
        'total_grades', (SELECT COUNT(*) FROM vox_grades),
        'fresh_grades', (SELECT COUNT(*) FROM vox_grades WHERE generated_at > NOW() - INTERVAL '{GRADE_FRESHNESS_HOURS} hours'),
        'grade_hours', (SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(generated_at))) / 3600.0, 9999) FROM vox_grades),
        'unified_hours', (SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(computed_at))) / 3600.0, 9999) FROM unified_grades),
        'price_hours', (SELECT COALESCE(EXTRACT(EPOCH FROM (NOW() - MAX(date))) / 3600.0, 9999) FROM price_history),
        'signal_count', (SELECT COUNT(*) FROM signal_performance),
        'smart_count', (SELECT COUNT(*) FROM smart_money_signals),
        'sector_count', (SELECT COUNT(*) FROM sector_rotation_scores),
        'discovery_count', (SELECT COUNT(*) FROM discovery_priority),
        'inst_count', (SELECT COUNT(*) FROM institutional_data),
        'macro_count', (SELECT COUNT(*) FROM macro_signals),
        'alerts_recent', (SELECT COUNT(*) FROM grade_alerts WHERE triggered_at > NOW() - INTERVAL '{ALERT_FRESHNESS_HOURS} hours')
    ) AS payload
    """
    data = _query_single_json(sql)

    total_grades = int(data.get("total_grades", 0) or 0)
    fresh_grades = int(data.get("fresh_grades", 0) or 0)
    grade_stale_pct = round(100.0 * (total_grades - fresh_grades) / total_grades, 2) if total_grades else 0.0
    grade_freshness_hours = float(data.get("grade_hours", 9999.0) or 9999.0)
    unified_hours = float(data.get("unified_hours", 9999.0) or 9999.0)
    price_hours = float(data.get("price_hours", 9999.0) or 9999.0)
    signal_count = int(data.get("signal_count", 0) or 0)
    smart_count = int(data.get("smart_count", 0) or 0)
    sector_count = int(data.get("sector_count", 0) or 0)
    discovery_count = int(data.get("discovery_count", 0) or 0)
    inst_count = int(data.get("inst_count", 0) or 0)
    macro_count = int(data.get("macro_count", 0) or 0)
    alerts_recent = int(data.get("alerts_recent", 0) or 0)

    if grade_stale_pct >= 50:
        blocking.append(f"{grade_stale_pct:.0f}% of vox_grades are stale (>72h)")
    elif grade_stale_pct >= 25:
        warnings.append(f"{grade_stale_pct:.0f}% of vox_grades are stale")

    if unified_hours > 24:
        blocking.append(f"unified_grades is {unified_hours:.1f}h old")
    elif unified_hours > 12:
        warnings.append(f"unified_grades is {unified_hours:.1f}h old")

    if price_hours > 72:
        blocking.append(f"price_history is {price_hours:.1f}h old")
    elif price_hours > 48:
        warnings.append(f"price_history is {price_hours:.1f}h old")

    if signal_count == 0:
        warnings.append("signal_performance is empty")

    if smart_count == 0:
        warnings.append("smart_money_signals has no rows")
    if sector_count == 0:
        warnings.append("sector_rotation_scores has no rows")
    if discovery_count == 0:
        warnings.append("discovery_priority has no rows")

    if inst_count == 0:
        warnings.append("institutional_data is empty")
    if macro_count == 0:
        warnings.append("macro_signals is empty")

    if alerts_recent == 0:
        warnings.append(f"No grade_alerts in last {ALERT_FRESHNESS_HOURS}h")

    missing_tables = []
    for table in REQUIRED_TABLES:
        try:
            rows = _query_single_json(f"SELECT json_build_object('ok', EXISTS (SELECT 1 FROM {table} LIMIT 1)) AS payload")
            if not rows.get("ok"):
                missing_tables.append(table)
        except Exception:
            missing_tables.append(table)
    if missing_tables:
        blocking.append(f"Missing required tables: {', '.join(missing_tables)}")

    score = 100
    score -= min(50, int(grade_stale_pct / 2))
    if unified_hours > 24:
        score -= 15
    elif unified_hours > 12:
        score -= 5
    if price_hours > 48:
        score -= 10
    if inst_count == 0:
        score -= 5
    if macro_count == 0:
        score -= 5
    if alerts_recent == 0:
        score -= 5
    if smart_count == 0 or sector_count == 0 or discovery_count == 0:
        score -= 3
    for _ in blocking:
        score -= 10
    score = max(0, min(100, score))
    if blocking:
        score = min(score, 49)

    return {
        "score": score,
        "grade_freshness_hours": round(grade_freshness_hours, 1),
        "grade_stale_pct": grade_stale_pct,
        "total_grades": total_grades,
        "fresh_grades": fresh_grades,
        "alerts_fresh": alerts_recent > 0,
        "has_smart_money": smart_count > 0,
        "has_sector_rotation": sector_count > 0,
        "has_discovery": discovery_count > 0,
        "has_institutional": inst_count > 0,
        "has_macro": macro_count > 0,
        "missing_tables": missing_tables,
        "warnings": warnings,
        "blocking": blocking,
        "generated_at": datetime.now().isoformat(),
    }


def health_summary(health: Dict[str, Any]) -> str:
    """Return a markdown summary for human/LLM consumption."""
    level = "HIGH" if health["score"] >= 80 else "MEDIUM" if health["score"] >= 50 else "LOW"
    lines = [
        f"**Data Confidence: {health['score']}/100 ({level})**",
        f"- Grade freshness: {health['grade_freshness_hours']}h | {health['grade_stale_pct']}% stale ({health['fresh_grades']}/{health['total_grades']} fresh)",
        f"- SmartMoney: {health['has_smart_money']} | SectorRotation: {health['has_sector_rotation']} | Discovery: {health['has_discovery']}",
        f"- Institutional: {health['has_institutional']} | Macro: {health['has_macro']}",
    ]
    if health["blocking"]:
        lines.append("- **Blocking issues:**")
        for b in health["blocking"]:
            lines.append(f"  - {b}")
    if health["warnings"]:
        lines.append("- **Warnings:**")
        for w in health["warnings"]:
            lines.append(f"  - {w}")
    return "\n".join(lines)


if __name__ == "__main__":
    h = assess_data_health()
    print(health_summary(h))
