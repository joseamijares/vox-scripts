#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from vox_intel_suite import main as suite_main
if __name__ == "__main__":
    sys.argv = ["vox_intel_suite.py", "social"]
    raise SystemExit(suite_main())
