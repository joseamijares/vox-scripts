#!/usr/bin/env python3
"""Wrapper for vox_watchlist_thesis.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
import vox_watchlist_thesis

if __name__ == '__main__':
    vox_watchlist_thesis.main(force=False)
