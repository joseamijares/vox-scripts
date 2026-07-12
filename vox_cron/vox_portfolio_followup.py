#!/usr/bin/env python3
"""VOX Portfolio Follow-up — weekly/biweekly sell + freshness report.

Designed for multi-broker book:
  API: eToro, Binance, Bitso
  Manual: GBM Main, GBM USA, Schwab, IBKR

Rules:
- SELL/TRIM action alerts only when weight >= 2.5% of consolidated portfolio
- Grade-based flags still listed, but small dust is noise-tagged
- Empty stdout only if nothing actionable AND no stale brokers (silent ok)

Cron: weekly Monday 8:00 CT recommended, deliver origin.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: F401

# Reuse dashboard generator
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from generate_dashboard import generate_dashboard_data, MIN_SELL_WEIGHT_PCT  # noqa: E402

OUT_DIR = Path.home() / ".hermes" / "cron" / "output"
OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "weekly"


def main() -> int:
    data = generate_dashboard_data()
    day = datetime.now().strftime("%Y-%m-%d")
    sells = data["actions"]["sell_now"]
    trims = data["actions"]["trim_review"]
    stale = data["stale_brokers"]
    manual = data["manual_update_needed"]

    lines = []
    lines.append(f"📡 **VOX Portfolio Follow-up — {day}**")
    lines.append("")
    lines.append(f"AUM (consolidated): **${data['grand_total']:,.0f}** | Positions: **{data['total_positions']}** | Avg grade: **{data['avg_grade']:.1f}**")
    lines.append("")

    # Broker health
    lines.append("## Broker status")
    for b, meta in sorted(data["integration_status"].items(), key=lambda x: -(x[1].get("total_usd") or 0)):
        age = meta.get("sync_age_days")
        age_s = f"{age}d" if age is not None else "—"
        flag = " 🔴" if meta.get("health") in ("STALE", "MISSING", "UNKNOWN") else (" 🟡" if meta.get("health") == "AGING" else " ✅")
        lines.append(
            f"- {flag} **{b}**: {meta.get('health')} | ${meta.get('total_usd') or 0:,.0f} | "
            f"{meta.get('mode')} | sync age {age_s}"
        )
    lines.append("")

    if manual:
        lines.append("## Manual update needed")
        lines.append("Send Excel/photo for: **" + ", ".join(manual) + "**")
        lines.append("")

    # SELL actions
    lines.append(f"## SELL now (≥{MIN_SELL_WEIGHT_PCT}% weight)")
    if sells:
        for s in sells:
            lines.append(
                f"- 🔴 **{s['ticker']}** — {s['council']} grade {s['grade']} | "
                f"${s['value_usd']:,.0f} ({s['weight_pct']}%) | {s['brokers']}"
            )
    else:
        lines.append("- None above weight threshold")
    lines.append("")

    lines.append(f"## TRIM review (≥{MIN_SELL_WEIGHT_PCT}% weight)")
    if trims:
        for s in trims:
            lines.append(
                f"- 🟡 **{s['ticker']}** — {s['council']} grade {s['grade']} | "
                f"${s['value_usd']:,.0f} ({s['weight_pct']}%) | {s['brokers']}"
            )
    else:
        lines.append("- None")
    lines.append("")

    # Core holdings
    lines.append("## Largest holdings")
    for p in data["all_positions"][:10]:
        lines.append(
            f"- {p['ticker']}: ${p['value_usd']:,.0f} ({p['weight_pct']}%) "
            f"g{p['grade']} {p['council']}"
        )
    lines.append("")
    lines.append("_Noise filter: P&L/sell actions only if position ≥2.5% portfolio. Grade flags still tracked._")
    lines.append("_When you send weekly/biweekly exports, I refresh manual brokers then re-run this follow-up._")

    report = "\n".join(lines)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"portfolio_followup_{day}.md").write_text(report + "\n")
    (OUT_DIR / f"portfolio_followup_{day}.json").write_text(json.dumps(data, indent=2, default=str))

    OBS.mkdir(parents=True, exist_ok=True)
    (OBS / f"PortfolioFollowup-{day}.md").write_text(report + "\n")

    # Always print for deliver:origin weekly visibility
    print(report)

    # Exit 0 always on successful generation (Pattern 9b)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
