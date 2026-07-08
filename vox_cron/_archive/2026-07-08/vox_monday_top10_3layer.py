#!/usr/bin/env python3
"""
VOX Monday Top 10 — 3-layer review: system signals → Sonnet 5 → DeepSeek v4 Pro.
"""
import os
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_utils as vu
import psycopg2
from datetime import datetime

DB = {
    "host": "acela.proxy.rlwy.net",
    "port": 35577,
    "user": "postgres",
    "password": os.environ.get("PGPASSWORD") or os.environ.get("DB_PASSWORD"),
    "dbname": "railway",
}

def q(sql):
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [d[0] for d in cur.description]
    cur.close()
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def fetch_data():
    return {
        "unified_grades": q("SELECT ticker, unified_grade, action, vox_grade, sp500_grade, trade_grade, tech_score, contradiction FROM unified_grades ORDER BY unified_grade DESC LIMIT 15"),
        "council": q("SELECT ticker, timestamp, consensus, risk_veto, final_action FROM council_deliberations WHERE final_action IN ('BUY','ACCUMULATE','STRONG_BUY') ORDER BY timestamp DESC LIMIT 15"),
        "top_opportunities": q("SELECT ticker, vox_grade, action, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, sector FROM top_opportunities ORDER BY vox_grade DESC LIMIT 10"),
        "sector_leaders": q("SELECT sector, ticker, momentum_score FROM sp500_sector_leaders ORDER BY momentum_score DESC LIMIT 15"),
        "sector_rotation": q("SELECT sector, etf_ticker, relative_strength, momentum_score, rotation_signal FROM sector_rotation ORDER BY rank LIMIT 10"),
        "macro": q("SELECT signal_name, signal_value, signal_direction, impact_sector, confidence FROM macro_signals ORDER BY confidence DESC LIMIT 10"),
        "market_regime": q("SELECT regime, confidence, vix_level, spy_trend, fed_stance, description FROM market_regime ORDER BY created_at DESC LIMIT 1"),
        "pattern_alerts": q("SELECT ticker, pattern_type, conviction, direction FROM pattern_alerts ORDER BY detected_at DESC LIMIT 10"),
        "insider": q("SELECT ticker, insider_name, transaction_type, total_value, importance FROM insider_trades ORDER BY created_at DESC LIMIT 10"),
        "trader_calls": q("SELECT trader_name, ticker, call_type, target_price, stop_price, thesis FROM trader_calls ORDER BY call_date DESC LIMIT 10"),
        "theme_alignment": q("SELECT theme, ticker, alignment_score, vox_grade, sector, macro_signal FROM theme_alignment ORDER BY alignment_score DESC LIMIT 10"),
        "earnings": q("SELECT ticker, report_date, eps_estimate, revenue_estimate FROM earnings_calendar WHERE report_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '7 days' ORDER BY report_date LIMIT 15"),
    }

def grade_mentioned_tickers():
    """Pre-grade any ticker mentioned by downstream systems that lacks a fresh grade."""
    sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
    from vox_live_grader import grade_ticker

    rows = q("""
        SELECT DISTINCT ticker FROM (
            SELECT ticker FROM council_deliberations
            UNION SELECT ticker FROM top_opportunities
            UNION SELECT ticker FROM pattern_alerts
            UNION SELECT ticker FROM insider_trades
            UNION SELECT ticker FROM trader_calls
            UNION SELECT ticker FROM theme_alignment
            UNION SELECT ticker FROM discovery_queue
            UNION SELECT ticker FROM earnings_calendar
            UNION SELECT ticker FROM watchlist
            UNION SELECT ticker FROM positions
        ) m
        WHERE NOT EXISTS (
            SELECT 1 FROM vox_grades v WHERE v.ticker = m.ticker
            AND v.generated_at > NOW() - INTERVAL '1 day'
        )
        AND m.ticker ~ '^[A-Z]+$'
        ORDER BY ticker
    """)
    tickers = [r['ticker'] for r in rows]
    if not tickers:
        print("All mentioned tickers already graded within 24h.")
        return

    print(f"Pre-grading {len(tickers)} mentioned tickers without fresh grade...")
    graded, failed = 0, 0
    for ticker in tickers[:20]:
        res = grade_ticker(ticker, timeout_secs=15)
        if res and not res.get('timeout') and res.get('grade') is not None:
            graded += 1
        else:
            failed += 1
        time.sleep(2)
    print(f"Pre-graded {graded} new, {failed} failed/timeout.")


def build_layer1_summary(data):
    lines = ["# VOX Layer 1 System Signals"]
    lines.append(f"Market Regime: {data['market_regime'][0] if data['market_regime'] else 'N/A'}")
    lines.append("\n## Top Unified Grades")
    for r in data['unified_grades']:
        lines.append(f"- {r['ticker']}: unified_grade={r['unified_grade']} action={r['action']} vox={r['vox_grade']} tech={r['tech_score']}")
    lines.append("\n## Council Buy/Accumulate")
    for r in data['council']:
        lines.append(f"- {r['ticker']}: consensus={r['consensus']} risk_veto={r['risk_veto']} final_action={r['final_action']}")
    lines.append("\n## Top Opportunities")
    for r in data['top_opportunities']:
        lines.append(f"- {r['ticker']}: vox_grade={r['vox_grade']} action={r['action']} sector={r['sector']} tech={r['technical_score']} fund={r['fundamental_score']} macro={r['macro_score']}")
    lines.append("\n## Sector Leaders")
    for r in data['sector_leaders']:
        lines.append(f"- {r['sector']}: {r['ticker']} momentum={r['momentum_score']}")
    lines.append("\n## Sector Rotation")
    for r in data['sector_rotation']:
        lines.append(f"- {r['sector']} ({r['etf_ticker']}): RS={r['relative_strength']} mom={r['momentum_score']} signal={r['rotation_signal']}")
    lines.append("\n## Macro Signals")
    for r in data['macro']:
        lines.append(f"- {r['signal_name']}: {r['signal_value']} {r['signal_direction']} ({r['impact_sector']}, conf={r['confidence']})")
    lines.append("\n## Pattern Alerts")
    for r in data['pattern_alerts']:
        lines.append(f"- {r['ticker']}: {r['pattern_type']} {r['direction']} conv={r['conviction']}")
    lines.append("\n## Insider Trades")
    for r in data['insider']:
        lines.append(f"- {r['ticker']}: {r['insider_name']} {r['transaction_type']} ${r['total_value']:,.0f} ({r['importance']})")
    lines.append("\n## Theme Alignment")
    for r in data['theme_alignment']:
        lines.append(f"- {r['theme']}: {r['ticker']} align={r['alignment_score']} vox={r['vox_grade']}")
    lines.append("\n## Trader Calls")
    for r in data['trader_calls']:
        lines.append(f"- {r['trader_name']}: {r['ticker']} {r['call_type']} | {r['thesis'][:80]}")
    lines.append("\n## Earnings This Week")
    for r in data['earnings']:
        lines.append(f"- {r['ticker']}: {r['report_date']} eps_est={r['eps_estimate']} rev_est={r['revenue_estimate']}")
    return "\n".join(lines)

def main():
    print("Pre-grading any mentioned tickers without fresh grade...")
    grade_mentioned_tickers()
    print("Collecting Layer 1 system signals...")
    data = fetch_data()
    layer1 = build_layer1_summary(data)

    # Save Layer 1
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path.home() / ".hermes" / "cron" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"vox_layer1_monday_{ts}.md").write_text(layer1)
    print(f"Layer 1 saved ({len(layer1)} chars)")

    # Layer 2: Sonnet 5 synthesis
    print("Layer 2: Sonnet 5 synthesis...")
    system_prompt = (
        "You are an aggressive-growth portfolio strategist for the VOX system. "
        "The user targets 25-50% yearly returns, rejects defensive stocks, and is open to all sectors. "
        "Rank the top 10 BUY plays for Monday. Give a ranked list with a concise bull case, risk, and position-size guidance. "
        "Avoid PG, KO, VZ, JNJ, utilities, REITs. Always return the full markdown table and the Layer 2 Logic paragraph. Do not omit the table."
    )
    sonnet_prompt = f"""Using the following VOX Layer 1 system data, produce the TOP 10 plays to buy on Monday.

MANDATORY OUTPUT FORMAT (do not skip any section):
1. Layer 2 Logic paragraph — explain cross-system convergence (unified grades, council, opportunities, sector leaders, pattern alerts, insider buying, trader calls).
2. A markdown table with exactly these columns:
   | Rank | Ticker | Final Grade | Key Catalysts | Position Size | Risk Level |
3. After the table, one bullet per pick with the single best confirming signal and one risk.

SELECTION RULES:
- Hybrid list: mix high-quality aggressive names and speculative high-conviction plays.
- Prefer tickers that appear in MULTIPLE systems.
- Exclude or downgrade names with strong sell/unfavorable council action or bearish macro signal.

{layer1}
"""
    sonnet = vu.call_openrouter(
        system_prompt=system_prompt,
        user_prompt=sonnet_prompt,
        model="anthropic/claude-sonnet-5",
        max_tokens=4000,
        temperature=0.3,
        script_name="vox_monday_top10_3layer.py",
        notes="Layer 2 Sonnet 5 Monday top 10 synthesis",
    )
    layer2 = sonnet["content"]
    (out_dir / f"vox_layer2_monday_{ts}.md").write_text(layer2)
    print(f"Layer 2 complete (${sonnet['cost_usd']:.4f})")

    # Layer 3: DeepSeek v4 Pro validation
    print("Layer 3: DeepSeek v4 Pro validation...")
    validate_prompt = f"""You are an independent risk validator. Review the following Layer 1 data and the Sonnet 5 Layer 2 top-10 list. 

Tasks:
1. Confirm or challenge each pick with one sentence of evidence.
2. Flag any ticker that should be REMOVED or DEMOTED due to stale data, conflicting signals, low liquidity, or excessive risk.
3. Suggest any ticker from Layer 1 that was overlooked and deserves inclusion.
4. Give a final VALIDATED top 10 in markdown table format (Rank, Ticker, Validator Verdict, Note).

LAYER 1 DATA:
{layer1}

LAYER 2 SONNET 5 OUTPUT:
{layer2}
"""
    deepseek = vu.call_openrouter(
        system_prompt="You are a skeptical, evidence-based risk validator. Be concise and direct.",
        user_prompt=validate_prompt,
        model="deepseek/deepseek-v4-pro",
        max_tokens=4000,
        temperature=0.2,
        script_name="vox_monday_top10_3layer.py",
        notes="Layer 3 DeepSeek v4 Pro Monday top 10 validation",
    )
    layer3 = deepseek["content"]
    (out_dir / f"vox_layer3_monday_{ts}.md").write_text(layer3)
    print(f"Layer 3 complete (${deepseek['cost_usd']:.4f})")

    final_path = out_dir / f"vox_monday_top10_final_{ts}.md"
    final = f"""# VOX Monday Top 10 — 3-Layer Final Output

## Layer 2: Sonnet 5 Synthesis
{layer2}

---

## Layer 3: DeepSeek v4 Pro Validation
{layer3}

---

*Generated: {datetime.now().isoformat()}*
*Sonnet 5 cost: ${sonnet['cost_usd']:.4f} | DeepSeek v4 Pro cost: ${deepseek['cost_usd']:.4f}*
"""
    final_path.write_text(final)
    print(f"\n✅ FINAL saved: {final_path}")
    print(final)

if __name__ == '__main__':
    main()
