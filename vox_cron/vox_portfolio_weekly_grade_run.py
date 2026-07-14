#!/usr/bin/env python3
"""Weekly portfolio grade cron wrapper (no CLI args)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vox_portfolio_weekly_grade import main

if __name__ == "__main__":
    raise SystemExit(main())
