#!/usr/bin/env python3
"""
VOX Decision Log + Thesis discipline (JOS-269)

Human action loop — not auto-trade.

  python3 vox_cron/vox_decision_log.py              # seed/refresh today from Ops
  python3 vox_cron/vox_decision_log.py status
  python3 vox_cron/vox_decision_log.py thesis TICKER [--side long|short] [--force]
  python3 vox_cron/vox_decision_log.py did "BUY ALAB small GBM" [--ticker ALAB]
  python3 vox_cron/vox_decision_log.py skip "1" --reason "wait for re-import"
  python3 vox.py log | log status | log did ... | log thesis TSLA --side long

Writes:
  memory/decisions/YYYY-MM-DD.md
  memory/theses/{TICKER}.md (ensure / upgrade stub)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

VOX = Path.home() / "Documents/Obsidian/VOX/vox"
DECISIONS = VOX / "memory" / "decisions"
THESES = VOX / "memory" / "theses"
BRAIN = VOX / "memory" / "brain"
OPS = BRAIN / "Daily-Ops-LATEST.md"
SHORT_STUBS = BRAIN / "Short-Thesis-Stubs-LATEST.md"
TEMPLATE_DECISION = DECISIONS / "Decision-Log-TEMPLATE.md"
TEMPLATE_THESIS = THESES / "_THESIS-TEMPLATE.md"
TEMPLATE_ACTION = DECISIONS / "Action-Loop-TEMPLATE.md"

MARK_OPS = "<!-- vox-ops-plan -->"
MARK_OPS_END = "<!-- vox-ops-plan-end -->"
MARK_EXEC = "<!-- vox-executed -->"
MARK_EXEC_END = "<!-- vox-executed-end -->"
MARK_SKIP = "<!-- vox-skipped -->"
MARK_SKIP_END = "<!-- vox-skipped-end -->"


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def now_hm() -> str:
    return datetime.now().strftime("%H:%M")


def ensure_dirs() -> None:
    DECISIONS.mkdir(parents=True, exist_ok=True)
    THESES.mkdir(parents=True, exist_ok=True)


def write_templates() -> None:
    TEMPLATE_DECISION.write_text(
        f"""---
date: "YYYY-MM-DD"
aum: null
generated_at: ""
---

# Decision Log — YYYY-MM-DD

_Ops Card recommends · **you** execute · grades = hygiene · multi-broker never sell reason_

## Links
- [[memory/brain/Daily-Ops-LATEST|Ops Card]]
- [[memory/brain/Outside-Ideas-LATEST|Outside]]
- [[memory/brain/Intel-Digest-LATEST|Intel Digest]]
- [[memory/brain/Earnings-Desk-LATEST|Earnings Desk]]
- [[memory/decisions/Breaking-LATEST|Breaking]]
- [[memory/decisions/Action-Loop-TEMPLATE|Action Loop template]]

## AUM / context
- AUM at open:
- Brokers refreshed: GBM [ ] Schwab [ ] IBKR [ ] Binance/API [ ]

{MARK_OPS}
## Ops plan (from card)
_Run `python3 vox.py log` to refresh_
{MARK_OPS_END}

{MARK_SKIP}
## Skipped / deferred
| # | Item | Reason | Review |
|---|------|--------|--------|
{MARK_SKIP_END}

{MARK_EXEC}
## Executed
| Time | Action | Ticker | Broker | Size/note | Thesis |
|------|--------|--------|--------|-----------|--------|
{MARK_EXEC_END}

## Thesis touchpoints today
- _Tickers touched → ensure `memory/theses/TICKER.md`_

## Next day
- [ ] Re-import if sized
- [ ] Prices / Ops tomorrow
- [ ] Update thesis invalidation if needed
"""
    )
    TEMPLATE_THESIS.write_text(
        """---
ticker: "TICKER"
status: "watch"   # watch | active | trim | exit | short_watch | short_active
side: "long"      # long | short
horizon: "medium" # long | medium | short_cleanup
opened: ""
kill_reviewed: ""
---

# Thesis — TICKER

**Status:** watch · **Side:** long · **Horizon:** medium

## Why in book / why candidate
- 

## Setup / edge
- 

## Trigger (entry or add)
- 

## Kill / invalidation (must be concrete)
- 

## Size rules
- Material ≥2.5% AUM gets full thesis
- New name: prefer Outside Tier A; AI_VETO never long
- Short: max 2% name / 8% gross sleeve; borrow check

## Links
- [[memory/brain/Daily-Ops-LATEST|Ops]]
- [[memory/brain/Outside-Ideas-LATEST|Outside]]
- [[memory/brain/Short-Thesis-Stubs-LATEST|Short stubs]]
- Decision logs: search `TICKER` under `memory/decisions/`

## Notes
- Multi-broker ownership is never a sell/cover reason alone
- Grades = hygiene only
"""
    )
    if not TEMPLATE_ACTION.exists():
        TEMPLATE_ACTION.write_text(
            """# Portfolio Action Loop — template

**Status:** open  
**Date:** YYYY-MM-DD  
**AUM at plan:** $  

## 1. Plan (VOX)
- Material SELL ≥2.5%:
- Cleanup junk:
- TRIM:
- Bucket A (owned rebalance):
- Bucket B (Outside-Ideas):

## 2. Execute (you)
| Action | Ticker | Broker | Status | Date |
|--------|--------|--------|--------|------|
| | | | pending | |

## 3. Refresh truth
- [ ] Re-import GBM / Schwab / IBKR if needed
- [ ] Confirm API brokers healthy
- [ ] Run `python3 vox.py ops` / brain
- [ ] Confirm dashboard AUM

## 4. Outcome
- What changed:
- Thesis updates:
- Next review:

_Grades = hygiene only. Multi-broker never a sell reason._
"""
        )


def parse_ops_plan(ops_text: str) -> list[str]:
    items = []
    mode = None
    for ln in ops_text.splitlines():
        if ln.startswith("## Do today"):
            mode = "do"
            continue
        if mode == "do":
            if ln.startswith("## ") or ln.startswith("### "):
                break
            m = re.match(r"^(\d+)\.\s+(.*)", ln.strip())
            if m:
                items.append(f"{m.group(1)}. {m.group(2).strip()}")
    return items[:8]


def parse_aum(ops_text: str) -> str:
    m = re.search(r"\*\*AUM:\*\*\s*\$([0-9,]+)", ops_text)
    return m.group(1) if m else "?"


def decision_path(day: str | None = None) -> Path:
    return DECISIONS / f"{day or today()}.md"


def seed_decision_log(day: str | None = None, force_ops: bool = True) -> Path:
    ensure_dirs()
    write_templates()
    day = day or today()
    path = decision_path(day)
    ops_text = OPS.read_text(errors="replace") if OPS.exists() else ""
    plan = parse_ops_plan(ops_text)
    aum = parse_aum(ops_text)

    if not path.exists():
        body = TEMPLATE_DECISION.read_text().replace("YYYY-MM-DD", day)
        body = body.replace('aum: null', f'aum: "{aum}"')
        body = body.replace('generated_at: ""', f'generated_at: "{datetime.now().isoformat()}"')
        path.write_text(body)

    text = path.read_text(errors="replace")
    # ensure markers
    if MARK_OPS not in text:
        text += f"\n{MARK_OPS}\n## Ops plan (from card)\n{MARK_OPS_END}\n"
    if MARK_EXEC not in text:
        text += f"\n{MARK_EXEC}\n## Executed\n| Time | Action | Ticker | Broker | Size/note | Thesis |\n|------|--------|--------|--------|-----------|--------|\n{MARK_EXEC_END}\n"
    if MARK_SKIP not in text:
        text += f"\n{MARK_SKIP}\n## Skipped / deferred\n| # | Item | Reason | Review |\n|---|------|--------|--------|\n{MARK_SKIP_END}\n"

    if force_ops or MARK_OPS in text:
        plan_block = ["## Ops plan (from card)", f"_Pulled {now_hm()} · AUM ~${aum}_", ""]
        if plan:
            for p in plan:
                plan_block.append(f"- [ ] {p}")
        else:
            plan_block.append("- _No Do-today lines in Ops Card_")
        plan_block.append("")
        plan_block.append(f"- Full: [[memory/brain/Daily-Ops-LATEST|Ops Card]]")
        text = replace_marked_section(text, MARK_OPS, MARK_OPS_END, "\n".join(plan_block))

    # frontmatter aum touch
    text = re.sub(r'(aum:\s*)([^\n]+)', rf'\1"{aum}"', text, count=1)
    path.write_text(text if text.endswith("\n") else text + "\n")
    return path


def replace_marked_section(text: str, start: str, end: str, inner: str) -> str:
    if start not in text or end not in text:
        return text + f"\n{start}\n{inner}\n{end}\n"
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    return f"{pre}{start}\n{inner}\n{end}{post}"


def append_in_table(text: str, start: str, end: str, row: str) -> str:
    if start not in text or end not in text:
        return text
    pre, rest = text.split(start, 1)
    mid, post = rest.split(end, 1)
    # insert before end marker content
    mid = mid.rstrip() + "\n" + row + "\n"
    return f"{pre}{start}{mid}{end}{post}"


def ensure_thesis(
    ticker: str,
    side: str = "long",
    status: str = "watch",
    reason: str = "",
    force: bool = False,
) -> Path:
    ensure_dirs()
    write_templates()
    ticker = ticker.strip().upper()
    path = THESES / f"{ticker}.md"
    if path.exists() and not force:
        # light touch: append note
        t = path.read_text(errors="replace")
        if reason and reason not in t:
            path.write_text(t.rstrip() + f"\n- Touch {today()} {now_hm()}: {reason}\n")
        return path

    # pull short stub if short
    stub_snip = ""
    if side == "short" and SHORT_STUBS.exists():
        body = SHORT_STUBS.read_text(errors="replace")
        if f"## " in body and ticker in body:
            parts = body.split(f"## ")
            for p in parts:
                if p.startswith(f"1. {ticker}") or p.lstrip().startswith(f"{ticker}") or f"{ticker} ·" in p[:40]:
                    stub_snip = p.split("## ")[0][:600]
                    break
            if not stub_snip:
                # search section containing ticker
                for block in re.split(r"\n## ", body):
                    if ticker in block[:30]:
                        stub_snip = block[:600]
                        break

    status = status or ("short_watch" if side == "short" else "watch")
    content = f"""---
ticker: "{ticker}"
status: "{status}"
side: "{side}"
horizon: "{"short_cleanup" if side == "short" else "medium"}"
opened: "{today()}"
kill_reviewed: ""
generated_at: "{datetime.now().isoformat()}"
---

# Thesis — {ticker}

**Status:** {status} · **Side:** {side} · **Opened:** {today()}

## Why in book / why candidate
- {reason or "_fill_"}

## Setup / edge
- {"See short stub below" if stub_snip else "_fill_"}

## Trigger (entry or add)
- _levels / conditions_

## Kill / invalidation (must be concrete)
- _what breaks the thesis → exit/cover_

## Size rules
- Long material ≥2.5% needs full kill criteria
- Short: ≤2% name · ≤8% gross short sleeve · borrow/liquidity first
- AI_VETO names are never clean Outside longs

## Links
- [[memory/decisions/{today()}|Decision Log today]]
- [[memory/brain/Daily-Ops-LATEST|Ops]]
- [[memory/brain/Outside-Ideas-LATEST|Outside]]
- [[memory/brain/Short-Thesis-Stubs-LATEST|Short stubs]]
- [[memory/brain/Intel-Digest-LATEST|Intel]]

"""
    if stub_snip:
        content += f"## From Short-Thesis-Stubs\n\n{stub_snip}\n\n"
    content += f"""## Notes
- Multi-broker ownership is never a sell/cover reason alone
- Grades = hygiene only
- Created by `vox_decision_log.py` on {today()}
"""
    path.write_text(content)
    return path


def log_did(action: str, ticker: str | None = None, broker: str = "", size: str = "") -> Path:
    path = seed_decision_log()
    text = path.read_text(errors="replace")
    t = (ticker or "").upper()
    if not t:
        m = re.search(r"\b([A-Z]{1,5})\b", action.upper())
        t = m.group(1) if m else ""
    thesis_link = ""
    if t:
        side = "short" if re.search(r"\bshort\b|\bcover\b", action.lower()) else "long"
        ensure_thesis(t, side=side, status="active" if side == "long" else "short_active", reason=action)
        thesis_link = f"[[memory/theses/{t}|{t}]]"
    row = f"| {now_hm()} | {action} | {t or '—'} | {broker or '—'} | {size or '—'} | {thesis_link or '—'} |"
    text = append_in_table(text, MARK_EXEC, MARK_EXEC_END, row)
    # check off matching ops plan item if numbers mentioned
    path.write_text(text)
    return path


def log_skip(item: str, reason: str) -> Path:
    path = seed_decision_log()
    text = path.read_text(errors="replace")
    row = f"| {item} | {item} | {reason} | {today()} |"
    # nicer: item is number or text
    row = f"| {item} | _{item}_ | {reason} | {today()} |"
    text = append_in_table(text, MARK_SKIP, MARK_SKIP_END, row)
    # try uncheck to deferred note in ops plan
    path.write_text(text)
    return path


def status() -> int:
    path = decision_path()
    print(f"decision_log: {path} {'OK' if path.exists() else 'MISSING'}")
    if path.exists():
        t = path.read_text(errors="replace")
        exec_n = len(re.findall(r"^\| \d{2}:\d{2} ", t, re.M))
        print(f"  executed_rows≈{exec_n}")
        print(f"  has_ops_plan={MARK_OPS in t}")
    print(f"ops_card: {'OK' if OPS.exists() else 'MISSING'}")
    print(f"theses_dir: {THESES} n={len(list(THESES.glob('*.md')))}")
    print(f"templates: decision={TEMPLATE_DECISION.exists()} thesis={TEMPLATE_THESIS.exists()}")
    # recent decision logs non-empty
    logs = sorted(DECISIONS.glob("20*.md"), reverse=True)[:5]
    for p in logs:
        print(f"  {p.name} bytes={p.stat().st_size}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="VOX decision log + thesis discipline")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("seed", help="seed/refresh today from Ops (default)")
    sub.add_parser("status")
    p_thesis = sub.add_parser("thesis")
    p_thesis.add_argument("ticker")
    p_thesis.add_argument("--side", choices=["long", "short"], default="long")
    p_thesis.add_argument("--status", default="")
    p_thesis.add_argument("--reason", default="")
    p_thesis.add_argument("--force", action="store_true")

    p_did = sub.add_parser("did")
    p_did.add_argument("action")
    p_did.add_argument("--ticker", default="")
    p_did.add_argument("--broker", default="")
    p_did.add_argument("--size", default="")

    p_skip = sub.add_parser("skip")
    p_skip.add_argument("item")
    p_skip.add_argument("--reason", required=True)

    # default seed if no cmd — support `vox_decision_log.py` bare
    args, rest = ap.parse_known_args()
    # allow `vox.py log did ...` style via argv passthrough
    if args.cmd is None:
        if rest:
            # reparse with first token as cmd
            sys.argv = [sys.argv[0]] + rest
            return main()
        path = seed_decision_log()
        print(f"Seeded {path}")
        return 0

    if args.cmd == "seed":
        path = seed_decision_log()
        print(f"Seeded {path}")
        return 0
    if args.cmd == "status":
        return status()
    if args.cmd == "thesis":
        st = args.status or ("short_watch" if args.side == "short" else "watch")
        path = ensure_thesis(args.ticker, side=args.side, status=st, reason=args.reason, force=args.force)
        print(f"Thesis {path}")
        return 0
    if args.cmd == "did":
        path = log_did(args.action, ticker=args.ticker or None, broker=args.broker, size=args.size)
        print(f"Logged execution → {path}")
        return 0
    if args.cmd == "skip":
        path = log_skip(args.item, args.reason)
        print(f"Logged skip → {path}")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
