#!/usr/bin/env python3
"""JOS-263 48h smart-approvals soak report (no_agent cron).

Emits a short markdown summary to stdout (delivered by Hermes cron)
and writes a local copy under the pre-quicksilver backup dir.
Does not change config.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

HOME = Path.home() / ".hermes"
CFG = HOME / "config.yaml"
BACKUP = sorted((HOME / "backups").glob("pre-quicksilver-adoption-*"))[-1]
OUT = BACKUP / "JOS-263-soak-report.md"


def main() -> int:
    cfg = yaml.safe_load(CFG.read_text())
    a = cfg.get("approvals") or {}
    s = cfg.get("streaming") or {}
    lines = [
        f"# JOS-263 smart-approvals soak report",
        f"",
        f"UTC: {datetime.now(timezone.utc).isoformat()}",
        f"",
        f"## Live config",
        f"- approvals.mode: `{a.get('mode')}`",
        f"- approvals.cron_mode: `{a.get('cron_mode')}`",
        f"- deny patterns: {len(a.get('deny') or [])}",
        f"- streaming.enabled: `{s.get('enabled')}`",
        f"- checkpoints.enabled: `{(cfg.get('checkpoints') or {}).get('enabled')}`",
        f"",
        f"## Soak checklist (fill / confirm)",
        f"- [ ] No surprise auto-approve on secrets / destructive / broker-ish shells",
        f"- [ ] Deny still blocks expected patterns",
        f"- [ ] VOX Ops Card / breaking finals clean (no mid-render junk)",
        f"- [ ] Streaming progressive edits OK in Telegram DM",
        f"- [ ] If reviewer unavailable → manual prompt (not silent approve)",
        f"",
        f"## Disposition",
        f"If all clean: close JOS-263 Done, then close parent JOS-258.",
        f"If not: set approvals.mode to manual from Mac Terminal, then investigate.",
        f"",
        f"## Config dump (non-secret)",
        f"```json",
        json.dumps(
            {
                "approvals_mode": a.get("mode"),
                "cron_mode": a.get("cron_mode"),
                "deny_n": len(a.get("deny") or []),
                "streaming": s.get("enabled"),
            },
            indent=2,
        ),
        f"```",
        f"",
    ]
    text = "\n".join(lines)
    OUT.write_text(text)
    print(text)
    print(f"\n(wrote {OUT})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
