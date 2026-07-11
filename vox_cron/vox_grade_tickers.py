#!/usr/bin/env python3
"""Wrapper to grade a specific list of tickers using vox_live_grader.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_live_grader import grade_ticker

if __name__ == '__main__':
    tickers = sys.argv[1:] if len(sys.argv) > 1 else []
    for t in tickers:
        print(f'Grading {t}...')
        try:
            result = grade_ticker(t)
            if result:
                print(f"  {result['ticker']}: grade={result['grade']} action={result['action']}")
            else:
                print(f"  {t}: no data / failed")
        except Exception as e:
            print(f"  {t}: ERROR {e}")
