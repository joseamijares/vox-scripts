#!/usr/bin/env python3
"""Held-book pricing refresh cron wrapper."""
import runpy
import sys
from pathlib import Path

sys.argv = ["vox_pricing_refresh.py", "held"]
runpy.run_path(str(Path(__file__).with_name("vox_pricing_refresh.py")), run_name="__main__")
