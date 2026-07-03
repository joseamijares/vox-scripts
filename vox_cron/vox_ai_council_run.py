#!/usr/bin/env python3
"""Wrapper for vox-ai-council cron (no arguments allowed in Hermes script field)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from vox_council_research import main as council_main

if __name__ == "__main__":
    # Inject default arguments
    sys.argv = ["vox_council_research.py", "--run", "--top-n", "10"]
    sys.exit(council_main())
