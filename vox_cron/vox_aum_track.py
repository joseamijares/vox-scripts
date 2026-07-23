#!/usr/bin/env python3
"""
VOX AUM tracker — daily snapshots + week/month Δ (JOS hygiene).

Truth:
  - Snapshot AUM from live positions (same book as Ops)
  - DoD / WTD / WoW / MoM from snap file once history exists
  - Optional cashflow notes (deposits/withdrawals) adjust "performance" Δ

Estimate (labeled):
  - Constant-share mark-to-market over N trading days via price_history
    (ignores trades/deposits — useful when snap history is thin)

Writes:
  ~/.hermes/cron/output/brain/aum_daily_snaps.json
  brain/AUM-Track-LATEST.md
  brain/AUM-Track-LATEST.json

Usage:
  python3 vox_cron/vox_aum_track.py
  python3 vox_cron/vox_aum_track.py --no-save
  python3 vox_cron/vox_aum_track.py --cashflow 1000 --note "deposit GBM"
  python3 vox.py aum
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts" / "vox_cron"))
try:
    import hermes_secrets_bootstrap  # noqa: F401
except Exception:
    pass

import psycopg2
from psycopg2.extras import RealDictCursor

OUT_DIR = Path.home() / ".hermes" / "cron" / "output" / "brain"
OBS = Path.home() / "Documents/Obsidian/VOX/vox/memory/brain"
SNAP_PATH = OUT_DIR / "aum_daily_snaps.json"
# keep weekly file in sync for Sunday bot
WEEKLY_SNAP = OUT_DIR / "weekly_aum_snapshots.json"
RADAR_SNAP = OUT_DIR / "radar_aum_snaps.json"
CASHFLOW_PATH = OUT_DIR / "aum_cashflows.json"
OUT_MD = OBS / "AUM-Track-LATEST.md"
OUT_JSON = OBS / "AUM-Track-LATEST.json"

JUNK = {
    "MIRROR_TOTAL", "CASH", "GBM O", "BI 270121", "TOTAL", "VAULTA", "KITE", "FF",
}
CRYPTO = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "BNB", "TRX", "HBAR", "AVAX",
    "DOT", "BONK", "PENGU", "VAULTA", "VANA", "MORPHO", "KAITO", "NIGHT",
}


def connect():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST") or os.environ.get("PGHOST", "acela.proxy.rlwy.net"),
        port=int(os.environ.get("DB_PORT") or os.environ.get("PGPORT", 35577)),
        dbname=os.environ.get("DB_NAME") or os.environ.get("PGDATABASE", "railway"),
        user=os.environ.get("DB_USER") or os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD"),
        connect_timeout=25,
    )


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str) + "\n")


def book_now() -> dict:
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT UPPER(ticker) t,
               COALESCE(shares, 0)::float sh,
               COALESCE(live_value_usd, live_value, 0)::float v,
               live_price::float px,
               day_chg_pct::float daychg,
               grade, sector
        FROM positions
        WHERE COALESCE(live_value_usd, live_value, 0) > 0
           OR COALESCE(shares, 0) > 0
        ORDER BY v DESC
        """
    )
    rows = cur.fetchall()
    conn.close()
    held = []
    aum = 0.0
    by_sec = defaultdict(float)
    crypto_v = energy_v = tech_v = 0.0
    for r in rows:
        t = (r["t"] or "").strip().upper()
        if not t or t in JUNK or " " in t:
            continue
        v = float(r["v"] or 0)
        aum += v
        sec = (r.get("sector") or "Other") or "Other"
        by_sec[sec] += v
        if t in CRYPTO:
            crypto_v += v
        if "energy" in str(sec).lower() or t in {"XLE", "XOM", "CVX", "OXY", "COP"}:
            energy_v += v
        if "tech" in str(sec).lower() or t in {"NVDA", "AMD", "MSFT", "AAPL", "GOOGL", "META", "AVGO"}:
            tech_v += v
        held.append(
            {
                "ticker": t,
                "shares": float(r["sh"] or 0),
                "v": v,
                "px": r.get("px"),
                "daychg": r.get("daychg"),
                "grade": r.get("grade"),
                "sector": sec,
            }
        )
    aum = aum or 1.0
    return {
        "day": datetime.now().strftime("%Y-%m-%d"),
        "ts": datetime.now(timezone.utc).isoformat(),
        "aum": round(aum, 2),
        "n": len(held),
        "tech_pct": round(tech_v / aum * 100, 1),
        "energy_pct": round(energy_v / aum * 100, 1),
        "crypto_pct": round(crypto_v / aum * 100, 1),
        "held": held,
    }


def upsert_snap(book: dict, note: str = "") -> list[dict]:
    data = load_json(SNAP_PATH, {"snaps": []})
    snaps = list(data.get("snaps") or [])
    day = book["day"]
    entry = {
        "day": day,
        "aum": book["aum"],
        "n": book["n"],
        "tech_pct": book["tech_pct"],
        "energy_pct": book["energy_pct"],
        "crypto_pct": book["crypto_pct"],
        "ts": book["ts"],
        "note": note or None,
    }
    # one per day (last write wins)
    snaps = [s for s in snaps if s.get("day") != day]
    snaps.append(entry)
    snaps.sort(key=lambda s: s.get("day") or "")
    # keep ~400 days
    snaps = snaps[-400:]
    save_json(SNAP_PATH, {"snaps": snaps, "updated_at": datetime.now(timezone.utc).isoformat()})

    # mirror into weekly/radar files (Sunday bot / radar panel A)
    for path in (WEEKLY_SNAP, RADAR_SNAP):
        w = load_json(path, {"snaps": []})
        ws = list(w.get("snaps") or [])
        ws = [s for s in ws if s.get("day") != day]
        ws.append({"day": day, "aum": book["aum"], "n": book["n"], "ts": book["ts"]})
        ws.sort(key=lambda s: s.get("day") or "")
        save_json(path, {"snaps": ws[-120:], "updated_at": datetime.now(timezone.utc).isoformat()})
    return snaps


def add_cashflow(amount: float, note: str = "", day: str | None = None) -> None:
    day = day or datetime.now().strftime("%Y-%m-%d")
    data = load_json(CASHFLOW_PATH, {"flows": []})
    flows = list(data.get("flows") or [])
    flows.append(
        {
            "day": day,
            "amount": float(amount),
            "note": note or ("deposit" if amount > 0 else "withdrawal"),
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_json(CASHFLOW_PATH, {"flows": flows, "updated_at": datetime.now(timezone.utc).isoformat()})


def cashflow_between(start: str, end: str) -> float:
    data = load_json(CASHFLOW_PATH, {"flows": []})
    total = 0.0
    for f in data.get("flows") or []:
        d = f.get("day") or ""
        if start < d <= end:  # flows after start through end
            total += float(f.get("amount") or 0)
        elif d == start and start == end:
            total += float(f.get("amount") or 0)
    return total


def nearest_snap(snaps: list[dict], target: str, window: int = 3) -> dict | None:
    """Nearest snap on or before target within window days."""
    t = date.fromisoformat(target)
    best = None
    best_delta: int | None = None
    for s in snaps:
        try:
            d = date.fromisoformat(s["day"])
        except Exception:
            continue
        if d > t:
            continue
        delta = (t - d).days
        if best is None or best_delta is None or delta < best_delta:
            best = s
            best_delta = delta
    if best is not None and best_delta is not None and best_delta <= window:
        return best
    # fallback: any on/before target
    cands = []
    for s in snaps:
        try:
            d = date.fromisoformat(s["day"])
        except Exception:
            continue
        if d <= t:
            cands.append((d, s))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0])
    return cands[-1][1]


def delta_block(snaps: list[dict], today: str, days: int, label: str) -> dict:
    cur = nearest_snap(snaps, today, window=0) or nearest_snap(snaps, today, window=2)
    if not cur:
        return {"label": label, "ok": False, "note": "no current snap"}
    target = (date.fromisoformat(today) - timedelta(days=days)).isoformat()
    prev = nearest_snap(snaps, target, window=4)
    if not prev or prev.get("day") == cur.get("day"):
        return {
            "label": label,
            "ok": False,
            "note": f"need prior snap near {target}",
            "current_day": cur.get("day"),
            "current_aum": cur.get("aum"),
        }
    # Avoid mixing estimate backfill with live AUM (apples/oranges)
    if bool(prev.get("estimate")) != bool(cur.get("estimate")):
        return {
            "label": label,
            "ok": False,
            "note": (
                f"mixed basis ({'est' if prev.get('estimate') else 'live'} "
                f"{prev.get('day')} → {'est' if cur.get('estimate') else 'live'} {cur.get('day')}) "
                "— wait for 2+ live daily snaps"
            ),
            "from_day": prev.get("day"),
            "to_day": cur.get("day"),
        }
    a0 = float(prev["aum"])
    a1 = float(cur["aum"])
    raw = a1 - a0
    flows = cashflow_between(prev["day"], cur["day"])
    perf = raw - flows
    pct = (raw / a0 * 100.0) if a0 else 0.0
    perf_pct = (perf / a0 * 100.0) if a0 else 0.0
    return {
        "label": label,
        "ok": True,
        "from_day": prev["day"],
        "to_day": cur["day"],
        "from_aum": round(a0, 2),
        "to_aum": round(a1, 2),
        "delta_usd": round(raw, 2),
        "delta_pct": round(pct, 2),
        "cashflow_usd": round(flows, 2),
        "perf_usd": round(perf, 2),
        "perf_pct": round(perf_pct, 2),
        "delta_str": f"{raw:+,.0f} ({pct:+.2f}%)",
        "perf_str": f"{perf:+,.0f} ({perf_pct:+.2f}%)" if flows else f"{raw:+,.0f} ({pct:+.2f}%)",
        "estimate": bool(cur.get("estimate") or prev.get("estimate")),
    }


def wtd_block(snaps: list[dict], today: str) -> dict:
    """Week-to-date from Monday (or nearest prior snap)."""
    t = date.fromisoformat(today)
    monday = t - timedelta(days=t.weekday())  # Mon=0
    return delta_block(
        snaps,
        today,
        days=(t - monday).days or 0,
        label="WTD",
    ) if (t - monday).days > 0 else {
        "label": "WTD",
        "ok": False,
        "note": "Monday baseline — WTD starts tomorrow",
        "current_day": today,
    }


def mtm_estimate(held: list[dict], lookback_trading_days: int = 5) -> dict:
    """Constant-share MTM using price_history closes."""
    if not held:
        return {"ok": False, "note": "no held"}
    tickers = [h["ticker"] for h in held if h.get("shares")]
    if not tickers:
        return {"ok": False, "note": "no shares"}
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT UPPER(ticker) t, date, close::float c
        FROM price_history
        WHERE UPPER(ticker) = ANY(%s)
          AND date >= CURRENT_DATE - 21
          AND close IS NOT NULL AND close > 0
        ORDER BY date
        """,
        (tickers,),
    )
    by_t: dict[str, list[tuple]] = defaultdict(list)
    for r in cur.fetchall():
        by_t[r["t"]].append((r["date"], float(r["c"])))
    conn.close()

    # global trading dates union
    all_dates = sorted({d for series in by_t.values() for d, _ in series})
    if len(all_dates) < 2:
        return {"ok": False, "note": "insufficient price_history"}
    end_d = all_dates[-1]
    # pick start = lookback trading days before end
    if len(all_dates) <= lookback_trading_days:
        start_d = all_dates[0]
    else:
        start_d = all_dates[-(lookback_trading_days + 1)]

    contrib = []
    v0 = v1 = 0.0
    missing = []
    for h in held:
        t = h["ticker"]
        sh = float(h.get("shares") or 0)
        if sh == 0:
            continue
        series = {d: c for d, c in by_t.get(t, [])}
        # nearest available on/before
        def px_on(target):
            if target in series:
                return series[target]
            cands = [d for d in series if d <= target]
            return series[max(cands)] if cands else None

        p0 = px_on(start_d)
        p1 = px_on(end_d)
        if p0 is None or p1 is None:
            missing.append(t)
            # fall back to live value only on end
            if h.get("v"):
                v1 += float(h["v"])
            continue
        a0 = sh * p0
        a1 = sh * p1
        v0 += a0
        v1 += a1
        dlt = a1 - a0
        if abs(dlt) >= 50:  # material-ish
            contrib.append(
                {
                    "ticker": t,
                    "delta": round(dlt, 2),
                    "pct": round((p1 / p0 - 1) * 100, 2) if p0 else 0,
                    "w0": round(a0, 2),
                }
            )
    contrib.sort(key=lambda x: -abs(x["delta"]))
    if v0 <= 0:
        return {"ok": False, "note": "could not value start", "missing": missing[:10]}
    raw = v1 - v0
    return {
        "ok": True,
        "kind": "constant_share_mtm",
        "from_date": str(start_d),
        "to_date": str(end_d),
        "lookback_trading_days": lookback_trading_days,
        "from_aum_est": round(v0, 2),
        "to_aum_est": round(v1, 2),
        "delta_usd": round(raw, 2),
        "delta_pct": round(raw / v0 * 100, 2),
        "delta_str": f"{raw:+,.0f} ({raw / v0 * 100:+.2f}%)",
        "top_contrib": contrib[:8],
        "missing_px": missing[:12],
        "coverage_names": len(held) - len(missing),
        "note": "ESTIMATE — constant shares; ignores trades & deposits",
    }


def fmt_block(b: dict) -> str:
    if not b.get("ok"):
        return f"- **{b.get('label')}:** n/a — {b.get('note')}"
    cf = b.get("cashflow_usd") or 0
    line = (
        f"- **{b['label']}:** {b['delta_str']} · "
        f"`{b['from_day']}` ${b['from_aum']:,.0f} → `{b['to_day']}` ${b['to_aum']:,.0f}"
    )
    if cf:
        line += f" · cashflow {cf:+,.0f} → perf {b.get('perf_str')}"
    return line


def render(book: dict, snaps: list[dict], blocks: dict, mtm: dict) -> str:
    day = book["day"]
    lines = [
        f"# AUM Track — {day}",
        "",
        f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · snapshots + optional MTM estimate_",
        "",
        f"## Now",
        f"- **AUM:** ${book['aum']:,.0f} · **names:** {book['n']}",
        f"- Tech ~{book['tech_pct']}% · Energy ~{book['energy_pct']}% · Crypto ~{book['crypto_pct']}%",
        f"- Snap file: `{SNAP_PATH}` · history days: **{len(snaps)}**",
        "",
        "## Snapshot deltas (book truth when 2+ snaps)",
        fmt_block(blocks["dod"]),
        fmt_block(blocks["wtd"]),
        fmt_block(blocks["wow"]),
        fmt_block(blocks["mom"]),
        "",
        "> AUM Δ = market + deposits − withdrawals + trades. "
        "Log cashflows: `python3 vox.py aum --cashflow 5000 --note deposit`",
        "",
        "## Mark-to-market estimate (constant shares)",
    ]
    if mtm.get("ok"):
        lines += [
            f"- **~{mtm.get('lookback_trading_days')}d MTM:** {mtm['delta_str']}",
            f"- Window `{mtm['from_date']}` → `{mtm['to_date']}` · "
            f"est ${mtm['from_aum_est']:,.0f} → ${mtm['to_aum_est']:,.0f}",
            f"- _{mtm.get('note')}_ · priced names {mtm.get('coverage_names')}",
            "",
            "### Top contributors (|Δ| ≥ $50)",
        ]
        for c in mtm.get("top_contrib") or []:
            lines.append(
                f"- **{c['ticker']}** {c['delta']:+,.0f} ({c['pct']:+.1f}%)"
            )
        if mtm.get("missing_px"):
            lines.append(f"- Missing px (partial): {', '.join(mtm['missing_px'][:8])}")
    else:
        lines.append(f"- n/a — {mtm.get('note')}")

    lines += [
        "",
        "## Recent snaps",
        "| Day | AUM | N | Crypto% |",
        "|-----|----:|--:|--------:|",
    ]
    for s in snaps[-10:]:
        lines.append(
            f"| {s.get('day')} | ${float(s.get('aum') or 0):,.0f} | {s.get('n')} | "
            f"{s.get('crypto_pct', '—')} |"
        )
    lines += [
        "",
        "## How to use",
        "1. Cron daily (post pricing) writes snap",
        "2. Sunday Weekly bot reads same history for WoW/MoM",
        "3. Log deposits/withdrawals so perf ≠ vanity AUM",
        "4. MTM estimate is hygiene when snap history is short — not SSOT",
        "",
    ]
    return "\n".join(lines) + "\n"


def backfill_mtm_snaps(held: list[dict], trading_days: int = 7) -> int:
    """Write estimate snaps for recent sessions from constant-share MTM (labeled)."""
    if trading_days < 2:
        return 0
    tickers = [h["ticker"] for h in held if h.get("shares")]
    sh_map = {h["ticker"]: float(h["shares"]) for h in held if h.get("shares")}
    if not tickers:
        return 0
    conn = connect()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute(
        """
        SELECT UPPER(ticker) t, date, close::float c
        FROM price_history
        WHERE UPPER(ticker) = ANY(%s)
          AND date >= CURRENT_DATE - 30
          AND close IS NOT NULL AND close > 0
        ORDER BY date
        """,
        (tickers,),
    )
    by_t: dict[str, dict] = defaultdict(dict)
    dates = set()
    for r in cur.fetchall():
        by_t[r["t"]][r["date"]] = float(r["c"])
        dates.add(r["date"])
    conn.close()
    all_dates = sorted(dates)
    if len(all_dates) < 2:
        return 0
    use_dates = all_dates[-(trading_days):]
    data = load_json(SNAP_PATH, {"snaps": []})
    snaps = list(data.get("snaps") or [])
    existing = {s.get("day") for s in snaps}
    added = 0
    for d in use_dates:
        day_s = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if day_s in existing:
            continue
        # value portfolio on day d with nearest prior px
        total = 0.0
        n = 0
        for t, sh in sh_map.items():
            series = by_t.get(t) or {}
            if d in series:
                px = series[d]
            else:
                cands = [dd for dd in series if dd <= d]
                if not cands:
                    continue
                px = series[max(cands)]
            total += sh * px
            n += 1
        if total <= 0 or n < 10:
            continue
        snaps.append(
            {
                "day": day_s,
                "aum": round(total, 2),
                "n": n,
                "ts": datetime.now(timezone.utc).isoformat(),
                "note": "backfill_mtm_estimate",
                "estimate": True,
            }
        )
        existing.add(day_s)
        added += 1
    snaps.sort(key=lambda s: s.get("day") or "")
    save_json(SNAP_PATH, {"snaps": snaps[-400:], "updated_at": datetime.now(timezone.utc).isoformat()})
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-save", action="store_true", help="compute only, do not write snap")
    ap.add_argument("--cashflow", type=float, default=None, help="signed USD (+deposit / -withdraw)")
    ap.add_argument("--note", default="", help="cashflow or snap note")
    ap.add_argument("--lookback", type=int, default=5, help="MTM trading days")
    ap.add_argument(
        "--backfill-mtm",
        type=int,
        default=0,
        metavar="N",
        help="seed N trading-day estimate snaps from price_history (test/bootstrap)",
    )
    args = ap.parse_args()

    if args.cashflow is not None:
        add_cashflow(args.cashflow, note=args.note)
        print(f"Cashflow logged: {args.cashflow:+.2f} ({args.note or '—'})")

    book = book_now()
    if args.backfill_mtm:
        n = backfill_mtm_snaps(book["held"], trading_days=args.backfill_mtm)
        print(f"Backfill MTM snaps added: {n}")

    if args.no_save:
        snaps = list(load_json(SNAP_PATH, {"snaps": []}).get("snaps") or [])
        if not any(s.get("day") == book["day"] for s in snaps):
            snaps = snaps + [
                {
                    "day": book["day"],
                    "aum": book["aum"],
                    "n": book["n"],
                    "tech_pct": book["tech_pct"],
                    "energy_pct": book["energy_pct"],
                    "crypto_pct": book["crypto_pct"],
                    "ts": book["ts"],
                }
            ]
    else:
        snaps = upsert_snap(book, note=args.note)

    day = book["day"]
    # DoD: 1 calendar day back
    blocks = {
        "dod": delta_block(snaps, day, 1, "DoD"),
        "wtd": wtd_block(snaps, day),
        "wow": delta_block(snaps, day, 7, "WoW"),
        "mom": delta_block(snaps, day, 30, "MoM"),
    }
    # if WTD used days=0 path already handled; if monday-distance and delta_block with 0
    if (date.fromisoformat(day).weekday()) > 0:
        mon = date.fromisoformat(day) - timedelta(days=date.fromisoformat(day).weekday())
        days_since_mon = (date.fromisoformat(day) - mon).days
        blocks["wtd"] = delta_block(snaps, day, days_since_mon, "WTD")

    mtm = mtm_estimate(book["held"], lookback_trading_days=args.lookback)
    md = render(book, snaps, blocks, mtm)
    OBS.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    payload = {
        "day": day,
        "aum": book["aum"],
        "n": book["n"],
        "snaps_n": len(snaps),
        "blocks": blocks,
        "mtm_estimate": mtm,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    (OBS / f"AUM-Track-{day}.md").write_text(md)

    print(f"AUM TRACK {day}")
    print(f"AUM ${book['aum']:,.0f} · n={book['n']} · snaps={len(snaps)}")
    for k in ("dod", "wtd", "wow", "mom"):
        b = blocks[k]
        if b.get("ok"):
            print(f"  {b['label']}: {b['delta_str']}" + (f" perf {b.get('perf_str')}" if b.get("cashflow_usd") else ""))
        else:
            print(f"  {b['label']}: n/a ({b.get('note')})")
    if mtm.get("ok"):
        print(f"  MTM~{args.lookback}d EST: {mtm['delta_str']} ({mtm['from_date']}→{mtm['to_date']})")
        for c in (mtm.get("top_contrib") or [])[:5]:
            print(f"    · {c['ticker']} {c['delta']:+,.0f} ({c['pct']:+.1f}%)")
    else:
        print(f"  MTM: n/a ({mtm.get('note')})")
    print(f"Wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
