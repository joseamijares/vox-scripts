#!/usr/bin/env python3
"""
VOX Digest Formatter
Reads a digest JSON file and outputs Telegram-formatted text.
Usage: python format_digest.py <type> [json_path]
  type: morning_briefing | alert_digest | weekly_opportunities
"""
import json
import sys
from datetime import datetime


def format_market_signals(signals):
    lines = []
    for sig_type, data in signals.items():
        val = data.get("value")
        signal = data.get("signal", "NEUTRAL")
        if val is not None:
            lines.append(f"- `{sig_type}`: {val:.3f} ({signal})")
    return "\n".join(lines)


def format_morning_briefing(data):
    m = data["market"]
    p = data["portfolio"]
    a = data["alerts"]

    lines = [
        f"# 🌅 VOX Morning Briefing — {data['generated_at'][:10]}",
        "",
        f"**TL;DR:** {data['tldr']}",
        "",
        "## Market Snapshot",
        f"- Regime: **{m['regime']}** (score: {m['regime_score']})",
    ]
    lines.append(format_market_signals(m["signals"]))

    lines.extend([
        "",
        "## Portfolio State",
        f"- AUM: **${p['total_aum']:,.0f}** ({p['total_positions']} positions)",
        f"- Stock AUM: ${p['stock_aum']:,.0f} | Crypto AUM: ${p['crypto_aum']:,.0f}",
        f"- Grades: 🟢 {p['grade_distribution']['strong']} | 🟡 {p['grade_distribution']['moderate']} | 🔴 {p['grade_distribution']['weak']}",
        f"- Missing cost basis: {p['missing_cost_basis']} positions",
        "",
        "## Alerts",
    ])

    if a["critical"]:
        lines.append("🔴 **CRITICAL**")
        for alert in a["critical"]:
            lines.append(f"- `{alert['ticker']}`: {alert['message']}")

    if a["action"]:
        lines.append("🟡 **ACTION**")
        for alert in a["action"][:5]:
            lines.append(f"- `{alert['ticker']}` ({alert['type']}): {alert['message']}")

    if not a["critical"] and not a["action"]:
        lines.append("✅ No critical or action alerts")

    if data.get("watchlist"):
        lines.extend(["", "## Top Watchlist"])
        for w in data["watchlist"][:5]:
            lines.append(f"- `{w['ticker']}` — grade {w['grade']}, council {w['council']}")

    lines.extend(["", "## Checklist"])
    for item in data["checklist"]:
        lines.append(f"- [ ] {item}")

    lines.extend(["", f"_Generated at {data['generated_at']}_"])
    return "\n".join(lines)


def format_alert_digest(data):
    lines = [
        f"# 🚨 VOX Alert Monitor — {data['generated_at'][:10]}",
        "",
        f"Portfolio: {data['portfolio_summary']['total_positions']} positions, ${data['portfolio_summary']['total_aum']:,.0f} AUM",
        f"Total alerts: {data['alert_count']}",
        "",
    ]

    if data["alerts"]["critical"]:
        lines.append("🔴 **CRITICAL — Act Now**")
        for alert in data["alerts"]["critical"]:
            lines.append(f"- `{alert['ticker']}` ({alert['type']}): {alert['message']}")
        lines.append("")

    if data["alerts"]["action"]:
        lines.append("🟡 **ACTION — Review Today**")
        for alert in data["alerts"]["action"][:10]:
            lines.append(f"- `{alert['ticker']}` ({alert['type']}): {alert['message']}")
        lines.append("")

    if not data["alerts"]["critical"] and not data["alerts"]["action"]:
        lines.append("✅ No critical or action alerts. Portfolio is within guardrails.")

    lines.append(f"\n_Generated at {data['generated_at']}_")
    return "\n".join(lines)


def format_weekly_opportunities(data):
    lines = [
        f"# 📊 VOX Weekly Opportunities — {data['generated_at'][:10]}",
        "",
        f"**Macro Regime:** {data['macro_regime']['regime']} (score: {data['macro_regime']['score']})",
        "",
        "## Top 10 Cross-Layer Opportunities",
    ]

    for i, opp in enumerate(data["top_10"], 1):
        ticker = opp.get("ticker", "N/A")
        grade = opp.get("grade", "N/A")
        source = opp.get("source", "unknown")
        sector = opp.get("sector", "")
        price = opp.get("current_price")
        line = f"{i}. `{ticker}` — grade {grade} | source: {source}"
        if sector:
            line += f" | sector: {sector}"
        if price:
            line += f" | price: ${price:.2f}"
        lines.append(line)

    if data.get("sector_leaders"):
        lines.extend(["", "## Sector Leaders"])
        for s in data["sector_leaders"][:10]:
            lines.append(
                f"- `{s.get('sector')}` #{s.get('rank')}: `{s.get('ticker')}` "
                f"(momentum: {s.get('momentum_score')}, 5d: {s.get('change_5d_pct', 0):.2f}%)"
            )

    lines.append(f"\n_Generated at {data['generated_at']}_")
    return "\n".join(lines)


FORMATTERS = {
    "morning_briefing": format_morning_briefing,
    "alert_digest": format_alert_digest,
    "weekly_opportunities": format_weekly_opportunities,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python format_digest.py <type> [json_path]")
        print("Types:", ", ".join(FORMATTERS.keys()))
        sys.exit(1)

    digest_type = sys.argv[1]
    json_path = sys.argv[2] if len(sys.argv) > 2 else f"sample_{digest_type}.json"

    formatter = FORMATTERS.get(digest_type)
    if not formatter:
        print(f"Unknown type: {digest_type}")
        print("Types:", ", ".join(FORMATTERS.keys()))
        sys.exit(1)

    with open(json_path) as f:
        data = json.load(f)

    print(formatter(data))


if __name__ == "__main__":
    main()
