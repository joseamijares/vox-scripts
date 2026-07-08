#!/usr/bin/env python3
"""
VOX Active Script Auditor — read-only reference map for safe cleanup.

Outputs CSV with columns: filename, path, classification, cron_references,
imports, imported_by, last_modified.

Classification:
- ACTIVE: referenced by a cron job or imported (transitively) by an active script.
- SUSPECT-DUPLICATE: matches _vN, _old, _backup, _test, _draft naming patterns.
- ORPHAN: not referenced anywhere in vox_cron.
- UNKNOWN: referenced but not via cron or known import path.
"""
import json
import csv
import re
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

REPO_ROOT = Path("/Users/jos/.hermes/scripts")
VOX_CRON = REPO_ROOT / "vox_cron"
JOBS_FILE = Path.home() / ".hermes" / "cron" / "jobs.json"
OUTPUT_CSV = REPO_ROOT / "vox_cron_audit_active_scripts.csv"

SUSPECT_PATTERNS = [
    re.compile(r"_v\d+\.py$"),
    re.compile(r"_old\.py$"),
    re.compile(r"_backup\.py$"),
    re.compile(r"_test\.py$"),
    re.compile(r"_draft\.py$"),
]


# Regex to capture all module names from an import statement.
import_re = re.compile(r"(?:from|import)\s+([A-Za-z0-9_.]+)(?:\s+import\s+([A-Za-z0-9_,\s]+))?")


def extract_imports(text: str, own_name: str, script_name_set: set) -> set:
    """Extract script names referenced by a Python file."""
    imports = set()
    for match in import_re.finditer(text):
        base = match.group(1)
        # Extract all module components from `vox_cron.vox_data_health` or `vox_data_health`
        parts = base.split(".")
        for part in parts:
            candidate = part + ".py"
            if candidate in script_name_set and candidate != own_name:
                imports.add(candidate)
        # Also check names imported after `from X import Y` where Y might be a module
        imported = match.group(2) or ""
        for item in imported.split(","):
            item = item.strip()
            if item:
                candidate = item + ".py"
                if candidate in script_name_set and candidate != own_name:
                    imports.add(candidate)
    # Fallback: any script name as a standalone word (excluding import lines already handled)
    for name in script_name_set:
        if name != own_name and re.search(rf"\b{name[:-3]}\b", text):
            imports.add(name)
    return imports


def load_jobs() -> list:
    """Load Hermes cron jobs, stripping invalid control characters."""
    raw = JOBS_FILE.read_text(errors="ignore")
    raw = "".join(
        ch
        for ch in raw
        if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) < 127) or ord(ch) >= 160
    )
    return json.loads(raw).get("jobs", [])


def main():
    jobs = load_jobs()

    script_to_crons = defaultdict(list)
    for job in jobs:
        script = job.get("script", "")
        name = job.get("name", "unknown")
        enabled = job.get("enabled", False)
        if script:
            script_to_crons[Path(script).name].append((name, enabled))

    all_scripts = sorted([p for p in VOX_CRON.rglob("*.py") if p.is_file()])
    script_names = {p.name: p for p in all_scripts}
    script_name_set = set(script_names.keys())

    script_imports = {
        p.name: extract_imports(p.read_text(errors="ignore"), p.name, script_name_set)
        for p in all_scripts
    }

    # Active scripts = referenced by cron OR imported by an active script (transitive closure)
    active_scripts = set(script_to_crons.keys()) & script_name_set

    changed = True
    while changed:
        changed = False
        for script in list(active_scripts):
            for imp in script_imports.get(script, set()):
                if imp not in active_scripts:
                    active_scripts.add(imp)
                    changed = True

    # Treat the auditor and data-health gate as live tooling even if no cron imports them yet
    live_tooling = {"audit_active_scripts.py", "vox_data_health.py"}

    def classify(name: str, path: Path) -> str:
        if name in active_scripts or name in script_to_crons or name in live_tooling:
            return "ACTIVE"
        for pat in SUSPECT_PATTERNS:
            if pat.search(name):
                return "SUSPECT-DUPLICATE"
        if not any(name in imports for imports in script_imports.values()):
            return "ORPHAN"
        return "UNKNOWN"

    rows = []
    for p in all_scripts:
        name = p.name
        rel = str(p.relative_to(REPO_ROOT))
        crons = script_to_crons.get(name, [])
        cron_refs = "; ".join([f"{c[0]}({'enabled' if c[1] else 'paused'})" for c in crons])
        imports = "; ".join(sorted(script_imports.get(name, set())))
        imported_by = "; ".join(sorted([k for k, v in script_imports.items() if name in v]))
        classification = classify(name, p)
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d")
        rows.append(
            {
                "filename": name,
                "path": rel,
                "classification": classification,
                "cron_references": cron_refs,
                "imports": imports,
                "imported_by": imported_by,
                "last_modified": mtime,
            }
        )

    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "filename",
                "path",
                "classification",
                "cron_references",
                "imports",
                "imported_by",
                "last_modified",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(r["classification"] for r in rows)
    print(f"Wrote {OUTPUT_CSV}")
    print(f"Total scripts: {len(rows)}")
    print(f"Classifications: {dict(counts)}")
    print(f"Active scripts: {len(active_scripts)}")
    print("\n--- SUSPECT-DUPLICATE ---")
    for r in rows:
        if r["classification"] == "SUSPECT-DUPLICATE":
            print(r["path"])
    print("\n--- ORPHAN (first 30) ---")
    for r in rows:
        if r["classification"] == "ORPHAN":
            print(r["path"])


if __name__ == "__main__":
    main()
