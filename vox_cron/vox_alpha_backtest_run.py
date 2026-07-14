#!/usr/bin/env python3
"""Wrapper for nightly multi-analyst backtest sweep — human summary output."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_alpha_backtest import run_backtest

ANALYSTS = [
    "vox_grade_v1",
    "unified_grade_v1",
    "technical_alpha_v1",
    "insider_cluster_v1",
    "trader_call_v1",
    "grade_alert_v1",
]


def _fmt_pct(x):
    try:
        return f"{float(x):+.1f}%"
    except Exception:
        return "—"


def _fmt_sharpe(x):
    try:
        return f"{float(x):+.2f}"
    except Exception:
        return "—"


def _verdict(hit, avg, sharpe):
    try:
        h, a, s = float(hit), float(avg), float(sharpe)
    except Exception:
        return "n/a"
    if a > 0 and s > 0.3 and h >= 0.45:
        return "USE"
    if a > 0 and s > 0:
        return "WEAK+"
    if a > -3 and h >= 0.35:
        return "MARGINAL"
    return "AVOID"


if __name__ == "__main__":
    end = datetime.utcnow().date()
    start = end - timedelta(days=90)
    rows = []
    failures = []

    for analyst in ANALYSTS:
        try:
            run_id, metrics = run_backtest(
                analyst_id=analyst,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                universe="signals",
                notional=10000,
                stop_loss_pct=0.08,
                max_holding_days=20,
                quiet=True,
            )
            overall = (metrics or {}).get("overall") or metrics or {}
            # run_backtest prints raw JSON — we re-summarize
            trades = overall.get("trades", 0)
            hit = overall.get("hit_rate", 0)
            avg = overall.get("avg_return", 0)
            sharpe = overall.get("sharpe", 0)
            rows.append(
                {
                    "analyst": analyst,
                    "run_id": str(run_id)[:8],
                    "trades": trades,
                    "hit": hit,
                    "avg": avg,
                    "sharpe": sharpe,
                    "verdict": _verdict(hit, avg, sharpe),
                }
            )
        except Exception as e:
            failures.append(f"{analyst}: {e}")
            rows.append(
                {
                    "analyst": analyst,
                    "run_id": "—",
                    "trades": 0,
                    "hit": 0,
                    "avg": 0,
                    "sharpe": 0,
                    "verdict": "FAIL",
                }
            )

    # Human summary only (suppress raw noise by printing clean report last)
    day = datetime.utcnow().strftime("%Y-%m-%d")
    usable = [r for r in rows if r["verdict"] in ("USE", "WEAK+")]
    avoid = [r for r in rows if r["verdict"] in ("AVOID", "FAIL")]

    lines = [
        f"🧪 **VOX Alpha Backtest Sweep — {day}**",
        f"Window: last 90d · horizons 5/20/60 · stop 8% · max hold 20d",
        "",
        "| Analyst | Trades | Hit | Avg ret | Sharpe | Verdict |",
        "|---------|-------:|----:|--------:|-------:|---------|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['analyst']}` | {r['trades']} | {100*float(r['hit']):.0f}% | "
            f"{_fmt_pct(r['avg'])} | {_fmt_sharpe(r['sharpe'])} | **{r['verdict']}** |"
        )

    lines.append("")
    if usable:
        lines.append(
            "**Usable families:** " + ", ".join(f"`{r['analyst']}`" for r in usable)
        )
    else:
        lines.append(
            "**Usable families:** none — do **not** size trades off these signal packs."
        )

    if avoid:
        lines.append(
            "**Avoid / broken:** " + ", ".join(f"`{r['analyst']}`" for r in avoid)
        )

    lines.append("")
    lines.append(
        "_Mandate: balanced book, not day-trading. Negative hit-rate packs are research feedback only._"
    )
    if failures:
        lines.append("")
        lines.append("**Errors:**")
        for f in failures:
            lines.append(f"· {f}")

    # Print clean summary (raw prints from run_backtest already went above;
    # wrap with a clear separator so Telegram readers see the table at the end)
    print("\n" + "=" * 48)
    print("\n".join(lines))
    raise SystemExit(0)
