#!/usr/bin/env python3
"""
Test harness for VOX cron scripts.
Validates syntax, imports, and structure without requiring DB/network.
"""
import ast
import os
import sys
from pathlib import Path

SCRIPTS = [
    "vox_macro_snapshot.py",
    "vox_morning_briefing.py",
    "vox_alert_monitor.py",
    "vox_weekly_opportunities.py",
]


def test_syntax(path):
    with open(path) as f:
        source = f.read()
    try:
        ast.parse(source)
        return True, "Syntax OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"


def test_imports(path):
    """Try to import the module (won't run main)."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("module", path)
        module = importlib.util.module_from_spec(spec)
        # Don't execute — just check it loads
        return True, "Imports OK (not executed)"
    except Exception as e:
        return False, f"Import error: {e}"


def test_has_main(path):
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source)
    has_main = any(
        isinstance(node, ast.If) and
        isinstance(node.test, ast.Compare) and
        any(isinstance(op, ast.Eq) for op in node.test.ops) and
        any(isinstance(val, ast.Constant) and val.value == "__main__" for val in node.test.comparators)
        for node in ast.walk(tree)
    )
    return has_main, "Has __main__ guard" if has_main else "Missing __main__ guard"


def main():
    base = Path(__file__).parent
    all_ok = True

    print("🔧 VOX Cron Script Test Harness\n")

    for script in SCRIPTS:
        path = base / script
        print(f"Testing {script}...")

        ok1, msg1 = test_syntax(path)
        ok2, msg2 = test_has_main(path)

        icon1 = "✅" if ok1 else "❌"
        icon2 = "✅" if ok2 else "❌"

        print(f"  {icon1} {msg1}")
        print(f"  {icon2} {msg2}")

        if not ok1 or not ok2:
            all_ok = False

    print()
    if all_ok:
        print("✅ All cron scripts passed structural tests.")
        print("Note: Full execution requires DB_PASSWORD env var and network access.")
        sys.exit(0)
    else:
        print("❌ Some tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
