#!/usr/bin/env python3
"""
VOX Backtest Narrative Generator
Uses tencent/hy3:free (with deepseek-v4-flash fallback) to convert backtest_runs metrics
into a one-paragraph human-readable narrative per analyst. Writes to Obsidian.
"""
import os, sys, json, psycopg2
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_hy3_workhorse import hy3_draft

OBSIDIAN_VOX = Path.home() / "Documents" / "Obsidian" / "VOX" / "vox"
BACKTEST_DIR = OBSIDIAN_VOX / "SignalQuality" / "BacktestNarratives"
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)


def fetch_recent_runs(limit=20):
    import os, psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(host=os.environ.get('DB_HOST','acela.proxy.rlwy.net'), port=int(os.environ.get('DB_PORT','35577')), database=os.environ.get('DB_NAME','railway'), user=os.environ.get('DB_USER','postgres'), password=os.environ.get('DB_PASSWORD') or os.environ.get('PGPASSWORD'))
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT run_id, analyst_id, start_date, end_date, universe, metrics, strategy_config, completed_at
        FROM backtest_runs
        WHERE status = 'complete' AND metrics IS NOT NULL
        ORDER BY completed_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def format_run(row) -> str:
    run_id = row['run_id']
    analyst_id = row['analyst_id']
    start_date = row['start_date']
    end_date = row['end_date']
    universe = row['universe']
    metrics = row['metrics'] if isinstance(row['metrics'], dict) else json.loads(row['metrics'] or '{}')
    strategy_config = row['strategy_config'] if isinstance(row['strategy_config'], dict) else (json.loads(row['strategy_config'] or '{}'))
    overall = metrics.get('overall', {})
    horizon_breakdown = json.dumps({k: v for k, v in metrics.items() if k != 'overall'}, indent=2)
    return f"""Analyst: {analyst_id}
Period: {start_date} to {end_date}
Universe: {universe}
Strategy: {json.dumps(strategy_config)}
Metrics:
- Trades: {overall.get('trades', 'N/A')}
- Hit rate: {overall.get('hit_rate', 0):.2%}
- Avg return: {overall.get('avg_return', 0):.2f}%
- Sharpe: {overall.get('sharpe', 0):.2f}
- Max drawdown: {overall.get('max_drawdown', 'N/A')}

Horizon breakdown:
{horizon_breakdown}
"""


def generate_narrative(runs_text: str) -> str:
    system_prompt = """You are VOX, a quantitative strategy analyst. Summarize the backtest results below into ONE concise paragraph per analyst. For each:
- State the key result (hit rate, avg return, Sharpe).
- Identify the strongest/weakest point.
- Say whether this analyst should be used for live signals, refined, or retired.
Be direct. No fluff. No bullet points unless they are part of a markdown table."""
    user_prompt = f"""Backtest results across analysts (T+1 open execution):

{runs_text}

Write a one-paragraph narrative per analyst. Do not include generic advice."""
    result = hy3_draft(system_prompt, user_prompt, max_tokens=1000, temperature=0.3,
                       script_name="vox_backtest_narrative", fallback_model="deepseek/deepseek-v4-flash")
    return result.get('content', '').strip() or "_Narrative generation failed._"


def main():
    rows = fetch_recent_runs(limit=20)
    if not rows:
        print("No completed backtest runs with metrics found.")
        return
    runs_text = "\n---\n".join([format_run(r) for r in rows])
    narrative = generate_narrative(runs_text)
    date_str = datetime.now().strftime("%Y-%m-%d")
    path = BACKTEST_DIR / f"BacktestNarrative-{date_str}.md"
    path.write_text(f"""# Backtest Narrative — {date_str}

Machine-generated summary of recent AlphaModel backtests.

<!-- vox-written -->

{narrative}

## Source Runs
```json
{runs_text}
```
""")
    print(f"Wrote {path}")


if __name__ == '__main__':
    main()
