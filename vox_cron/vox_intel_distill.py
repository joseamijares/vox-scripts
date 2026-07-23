#!/usr/bin/env python3
"""
VOX Intel Spine — DISTILL (Phase 1)

DeepSeek compresses today's events JSONL into Intel-Digest-LATEST.md.
Soft only — never SSOT / never auto-trade.

Usage:
  python3 vox_cron/vox_intel_distill.py
  python3 vox_cron/vox_intel_distill.py --no-llm   # structural digest only
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

INTEL = Path.home() / ".hermes" / "cron" / "output" / "intel"
OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
OUT_MD = OBS / "Intel-Digest-LATEST.md"
OUT_JSON = INTEL / "IntelDigest-LATEST.json"


def load_events() -> list[dict]:
    path = INTEL / "events_LATEST.jsonl"
    if not path.exists():
        day = datetime.now().strftime("%Y-%m-%d")
        path = INTEL / f"events_{day}.jsonl"
    if not path.exists():
        return []
    out = []
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out


def structural_digest(events: list[dict]) -> dict:
    by_theme: dict[str, list] = defaultdict(list)
    for e in events:
        by_theme[e.get("theme") or "other"].append(e)

    book_linked = sorted(
        [e for e in events if (e.get("book_w") or 0) > 0],
        key=lambda x: -float(x.get("book_w") or 0),
    )[:15]
    trump = [e for e in events if e.get("theme") == "trump_policy"][:10]
    earn = [e for e in events if e.get("theme") == "earnings"][:20]
    geo = [e for e in events if e.get("theme") in ("oil_geo", "market_structure")][:10]
    high = [e for e in events if int(e.get("severity") or 0) >= 3][:12]

    return {
        "n": len(events),
        "themes": {k: len(v) for k, v in by_theme.items()},
        "book_linked": book_linked,
        "trump_policy": trump,
        "earnings": earn,
        "geo_macro": geo,
        "high_severity": high,
    }


def llm_bullets(struct: dict) -> str:
    if os.environ.get("VOX_INTEL_NO_LLM") == "1":
        return ""
    try:
        from vox_utils import call_openrouter
    except Exception as e:
        return f"(llm import failed: {e})"

    def _titles(items, n=8):
        lines = []
        for e in items[:n]:
            tw = e.get("tickers") or []
            bw = e.get("book_w") or 0
            lines.append(f"- [{e.get('theme')}] w={bw} {tw} {e.get('title')}")
        return "\n".join(lines) or "- (none)"

    user = f"""Compress VOX intel for a balanced multi-broker book. Soft only. No orders.

EVENT COUNTS: {json.dumps(struct.get('themes') or {})}

BOOK-LINKED:
{_titles(struct.get('book_linked') or [])}

TRUMP/POLICY:
{_titles(struct.get('trump_policy') or [])}

EARNINGS:
{_titles(struct.get('earnings') or [])}

GEO/OIL/STRUCTURE:
{_titles(struct.get('geo_macro') or [])}

HIGH SEVERITY:
{_titles(struct.get('high_severity') or [])}

Write markdown sections exactly:
## Book-relevant (max 6 bullets)
## Trump / policy (max 4 bullets; say none if empty)
## Earnings watch (max 6 bullets)
## Geo / macro (max 4 bullets)
## Ignore / noise (max 3 bullets)
## One blind spot

Max 280 words. Hygiene only. Do not invent tickers not in context.
"""
    models = [
        os.environ.get("VOX_INTEL_MODEL", "deepseek/deepseek-v4-flash"),
        "deepseek/deepseek-chat",
        "deepseek/deepseek-v4-pro",
    ]
    last = ""
    for model in models:
        try:
            result = call_openrouter(
                system_prompt="VOX intel compressor. Soft footnote voice. No auto-trade.",
                user_prompt=user,
                model=model,
                max_tokens=700,
                temperature=0.2,
                script_name="vox_intel_distill",
                notes="intel spine digest",
            )
            text = ""
            if isinstance(result, dict):
                for k in ("content", "text", "response", "reasoning"):
                    val = result.get(k)
                    if val and str(val).strip() not in ("", "None"):
                        text = str(val).strip()
                        if k == "reasoning":
                            # keep last chunk
                            parts = [p for p in text.split("\n") if p.strip()]
                            text = "\n".join(parts[-20:])
                        break
            if text and "##" in text:
                return text[:3500] + f"\n\n_model: {model}_"
            last = str(text)[:200]
        except Exception as e:
            last = str(e)
            continue
    return f"(distill llm failed: {last})"


def render_md(day: str, struct: dict, llm: str) -> str:
    lines = [
        f"# Intel Digest — {day}",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · Intel Spine · **not SSOT**_",
        f"_Events: **{struct.get('n', 0)}** · themes `{json.dumps(struct.get('themes') or {})}`_",
        "",
        "> Soft context only. **Ops Decision Object** still owns actions. No councils.",
        "",
    ]
    if llm and not llm.startswith("("):
        lines += [llm.strip(), ""]
    else:
        lines += ["## Structural (no LLM)", f"_{llm or 'llm skipped'}_", ""]
        lines.append("### Book-linked headlines")
        for e in (struct.get("book_linked") or [])[:8]:
            lines.append(
                f"- **{','.join(e.get('tickers') or [])}** w={e.get('book_w')} — {e.get('title')}"
            )
        lines.append("### Trump / policy")
        for e in (struct.get("trump_policy") or [])[:5]:
            lines.append(f"- {e.get('title')}")
        if not struct.get("trump_policy"):
            lines.append("- _none in bus_")
        lines.append("### Earnings")
        for e in (struct.get("earnings") or [])[:8]:
            lines.append(f"- {e.get('title')}")
        lines.append("")

    lines += [
        "## Sources",
        "- Finnhub general + company + earnings calendar",
        "- Google News RSS: trump_policy · fed_macro · oil_geo · market_structure",
        f"- Bus: `~/.hermes/cron/output/intel/events_{day}.jsonl`",
        "",
        "## How to use",
        "1. Ops Card snip — EVENT / risk awareness only",
        "2. Weekly broadcast — optional macro line",
        "3. Hermes chat — ask Grok/`x_search` for depth",
        "4. Never treat this file as trade list",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    if args.no_llm:
        os.environ["VOX_INTEL_NO_LLM"] = "1"

    day = datetime.now().strftime("%Y-%m-%d")
    events = load_events()
    struct = structural_digest(events)
    llm = llm_bullets(struct)
    md = render_md(day, struct, llm)
    OBS.mkdir(parents=True, exist_ok=True)
    INTEL.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    (OBS / f"Intel-Digest-{day}.md").write_text(md)
    payload = {
        "day": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "structural": {
            "n": struct["n"],
            "themes": struct["themes"],
            "book_linked": struct["book_linked"][:12],
            "earnings": struct["earnings"][:15],
            "trump_policy": struct["trump_policy"][:8],
        },
        "llm_ok": bool(llm) and not str(llm).startswith("("),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print(f"INTEL DISTILL {day}")
    print(f"events={struct['n']} llm={'yes' if payload['llm_ok'] else 'no'}")
    print(f"Wrote {OUT_MD}")
    # short stdout for cron
    print(md[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
