#!/usr/bin/env python3
"""VOX Portfolio Follow-up — mandate-aware sell + sleeve drift + broker freshness.

JOS-189 / JOS-192
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from generate_dashboard import generate_dashboard_data, MIN_SELL_WEIGHT_PCT  # noqa: E402

OUT_DIR = Path.home() / ".hermes" / "cron" / "output"
OBS = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox" / "memory" / "weekly"


def main() -> int:
    # Rebuild consolidated positions first when possible
    try:
        from vox_rebuild_positions import rebuild
        rebuild()
    except Exception as e:
        print(f"(rebuild skipped: {e})", file=sys.stderr)

    data = generate_dashboard_data()
    day = datetime.now().strftime("%Y-%m-%d")
    sells = data["actions"]["sell_now"]
    trims = data["actions"]["trim_review"]
    watches = data["actions"].get("watch") or []
    stale = data["stale_brokers"]
    manual = data["manual_update_needed"]
    sleeves = (data.get("sleeve_snapshot") or {}).get("sleeves") or []

    lines = []
    lines.append(f"📡 **VOX Portfolio Follow-up — {day}**")
    lines.append("")
    lines.append(
        f"AUM: **${data['grand_total']:,.0f}** | Positions: **{data['total_positions']}** | "
        f"Avg grade: **{data['avg_grade']:.1f}**"
    )
    lines.append(f"_Mandate: {data.get('mandate', 'top-tier balanced')}_")
    lines.append("")

    lines.append("## Broker status")
    for b, meta in sorted(
        data["integration_status"].items(),
        key=lambda x: -(x[1].get("total_usd") or 0),
    ):
        age = meta.get("sync_age_days")
        age_s = f"{age}d" if age is not None else "—"
        flag = (
            " 🔴"
            if meta.get("health") in ("STALE", "MISSING", "UNKNOWN")
            else (" 🟡" if meta.get("health") == "AGING" else " ✅")
        )
        lines.append(
            f"- {flag} **{b}**: {meta.get('health')} | ${meta.get('total_usd') or 0:,.0f} | "
            f"{meta.get('mode')} | sync age {age_s}"
        )
    lines.append("")

    if manual:
        lines.append("## Manual update needed")
        lines.append("Send Excel/photo for: **" + ", ".join(manual) + "**")
        lines.append("")

    # Sleeve drift
    lines.append("## Sleeve drift (vs target)")
    lines.append("| Sleeve | Now % | Target % | Gap |")
    lines.append("|--------|------:|---------:|----:|")
    for s in sorted(sleeves, key=lambda x: x.get("sleeve") or ""):
        if s["sleeve"] in ("OTHER",) and s["now_pct"] < 0.1:
            continue
        gap = s["gap_pp"]
        mark = " 🔴" if abs(gap) >= 8 else (" 🟡" if abs(gap) >= 4 else "")
        lines.append(
            f"| {s['sleeve']}{mark} | {s['now_pct']:.1f}% | {s['target_pct']:.0f}% | {gap:+.1f}pp |"
        )
    lines.append("")

    lines.append(f"## SELL now (≥{MIN_SELL_WEIGHT_PCT}% or material junk)")
    if sells:
        for s in sells:
            why = "; ".join((s.get("reasons") or [])[:2]) or s.get("council") or ""
            lines.append(
                f"- 🔴 **{s['ticker']}** — grade {s['grade']} | "
                f"${s['value_usd']:,.0f} ({s['weight_pct']}%) | {s.get('sleeve')} | {why}"
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append(f"## TRIM review")
    if trims:
        for s in trims:
            why = "; ".join((s.get("reasons") or [])[:2]) or ""
            lines.append(
                f"- 🟡 **{s['ticker']}** — grade {s['grade']} | "
                f"${s['value_usd']:,.0f} ({s['weight_pct']}%) | {s.get('sleeve')} | {why}"
            )
    else:
        lines.append("- None")
    lines.append("")

    # Explicit protected names note
    lines.append("## Protected / do-not-auto-sell")
    lines.append("- **COST, APH, WMT, quality megacaps** — compounders/core")
    lines.append("- **SPCX** — SpaceX theme (not SPAC ETF)")
    lines.append("- **BTC/ETH** — core crypto (trim only if oversized)")
    lines.append("- Multi-broker ownership is **never** a sell reason")
    lines.append("")

    lines.append("## Largest holdings")
    for p in data["all_positions"][:10]:
        lines.append(
            f"- {p['ticker']}: ${p['value_usd']:,.0f} ({p['weight_pct']}%) "
            f"g{p['grade']} {p['council']}"
        )
    lines.append("")
    lines.append("_Policy: `vox_portfolio_policy.py` · Rebuild: `vox_rebuild_positions.py`_")

    report = "\n".join(lines)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"portfolio_followup_{day}.md").write_text(report + "\n")
    (OUT_DIR / f"portfolio_followup_{day}.json").write_text(
        json.dumps(data, indent=2, default=str)
    )
    OBS.mkdir(parents=True, exist_ok=True)
    (OBS / f"PortfolioFollowup-{day}.md").write_text(report + "\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
