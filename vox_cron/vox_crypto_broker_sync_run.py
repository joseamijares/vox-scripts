#!/usr/bin/env python3
"""Daily crypto broker sync: Binance + Bitso → broker_positions.

Exit 0 if at least one venue succeeded (partial OK).
Local deliver only — not Telegram.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(name: str) -> int:
    path = HERE / name
    print(f"\n=== {name} ===", flush=True)
    try:
        # isolate exit
        ns = runpy.run_path(str(path), run_name="__not_main__")
        main = ns.get("main")
        if not callable(main):
            print(f"❌ no main() in {name}")
            return 1
        code = int(main() or 0)  # type: ignore[arg-type]
        print(f"exit {code}", flush=True)
        return code
    except SystemExit as e:
        code = int(e.code or 0)
        print(f"exit {code}", flush=True)
        return code
    except Exception as e:
        print(f"❌ {name}: {e}", flush=True)
        return 1


def main() -> int:
    b1 = run("vox_binance_sync.py")
    b2 = run("vox_bitso_sync.py")
    ok = (b1 == 0) or (b2 == 0)
    print(f"\nCrypto broker sync summary binance={b1} bitso={b2} → {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
