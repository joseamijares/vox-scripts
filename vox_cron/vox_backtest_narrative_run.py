#!/usr/bin/env python3
"""Wrapper for vox_backtest_narrative.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_backtest_narrative

if __name__ == '__main__':
    vox_backtest_narrative.main()
