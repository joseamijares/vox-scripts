#!/usr/bin/env python3
"""Cron wrapper for outside-book ideas scanner."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vox_outside_ideas import main

if __name__ == "__main__":
    raise SystemExit(main())
