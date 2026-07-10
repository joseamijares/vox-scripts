#!/usr/bin/env python3
"""Wrapper for vox_alpha_signal_adapter.py cron — Hermes cannot pass CLI args."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_alpha_signal_adapter import main

if __name__ == '__main__':
    main(dry_run=False, lookback_days=30)
