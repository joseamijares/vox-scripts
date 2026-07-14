#!/usr/bin/env python3
"""Wrapper for portfolio brain cron (no CLI args in Hermes script field)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vox_portfolio_brain import main

if __name__ == "__main__":
    raise SystemExit(main())
