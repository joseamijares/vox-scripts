#!/usr/bin/env python3
"""DEPRECATED wrapper — Phase 2 price owner.

Grades-only price touch via canonical vox_pricing_refresh.py grades mode.
Do not use vox_hybrid_price_feed for positions.
"""
import runpy
import sys
from pathlib import Path

sys.argv = ["vox_pricing_refresh.py", "grades"]
runpy.run_path(str(Path(__file__).with_name("vox_pricing_refresh.py")), run_name="__main__")
