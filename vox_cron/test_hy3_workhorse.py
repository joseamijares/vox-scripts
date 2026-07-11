#!/usr/bin/env python3
"""Smoke test for vox_hy3_workhorse.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
from vox_hy3_workhorse import hy3_draft


def test_hy3_draft():
    out = hy3_draft(
        system_prompt="You are a concise test assistant.",
        user_prompt="Say 'hy3 workhorse smoke test OK' and nothing else.",
        max_tokens=50,
        temperature=0.3,
        script_name="test_hy3_workhorse",
    )
    content = out.get("content", "").strip()
    assert content, "hy3_draft returned empty content"
    assert "OK" in content or "hy3" in content.lower(), f"Unexpected content: {content}"
    print(f"fallback={out.get('fallback')}, content={content}")


if __name__ == '__main__':
    test_hy3_draft()
    print("PASS")
