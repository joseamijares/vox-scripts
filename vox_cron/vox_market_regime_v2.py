#!/usr/bin/env python3
"""VOX Market Regime v2 — thin wrapper around macro_engine.

The old portfolio-PnL regime detector did not write to market_regime and
duplicated the 6 AM macro slot. This wrapper keeps the cron name stable and
delegates to the real FRED/yfinance macro engine.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> int:
    engine = Path.home() / ".hermes" / "scripts" / "vox_cron" / "vox_macro_engine.py"
    if not engine.exists():
        print(f"Missing macro engine: {engine}")
        return 1
    # Execute as __main__ so its main path runs
    try:
        runpy.run_path(str(engine), run_name="__main__")
        return 0
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        return code
    except Exception as e:
        print(f"market regime wrapper failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
