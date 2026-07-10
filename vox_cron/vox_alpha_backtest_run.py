#!/usr/bin/env python3
"""Wrapper for nightly multi-analyst backtest sweep."""
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_alpha_backtest import run_backtest

ANALYSTS = [
    'vox_grade_v1',
    'unified_grade_v1',
    'technical_alpha_v1',
    'insider_cluster_v1',
    'trader_call_v1',
    'grade_alert_v1',
]

if __name__ == '__main__':
    end = datetime.utcnow().date()
    start = end - timedelta(days=90)
    for analyst in ANALYSTS:
        try:
            run_backtest(
                analyst_id=analyst,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                universe='signals',
                notional=10000,
                stop_loss_pct=0.08,
                max_holding_days=20
            )
        except Exception as e:
            print(f"Backtest failed for {analyst}: {e}")
