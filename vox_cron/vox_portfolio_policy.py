#!/usr/bin/env python3
"""VOX portfolio policy — top-tier balanced mandate (2026-07-12).

Single source of truth for:
- quality compounders (never auto-SELL for being 'defensive')
- asset aliases (VAULTA≠Agilent, SPCX=SpaceX)
- sleeve classification + target weights
- sell/trim decisions that ignore multi-broker ownership
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# --- Mandate ---
# Top-tier balanced ~20% annual aim. Quality compounders welcome.
# Multi-broker ownership is NEVER a sell reason.

QUALITY_HOLD = {
    "COST", "WMT", "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSM",
    "AVGO", "APH", "MELI", "IBM", "MNST", "ORCL", "CRM", "HD", "NFLX", "V", "MA",
}

INDEX = {"VOO", "QQQ", "VTI", "SPY", "IWM", "CBRS"}

MOMENTUM = {
    "CRWD", "AMD", "SHOP", "TSLA", "SNOW", "MU", "DDOG", "ESTC", "NUTX", "APP",
    "SPOT", "SE", "NBIS", "OSCR", "AXS", "QLYS", "CRDO",
}

THEME = {"SPCX", "OKLO", "IONQ", "CEG", "SMH", "TECK"}  # SPCX = SpaceX

CRYPTO_CORE = {"BTC", "ETH"}

CRYPTO_ALT = {
    "DOGE", "BNB", "ADA", "XRP", "TRX", "HBAR", "SOL", "VAULTA", "BONK", "PENGU",
    "KAITO", "KITE", "MORPHO", "FF", "NXPC", "NIGHT", "XPL", "ALLO", "VANA", "HUMA",
    "COIN", "BNB-USD", "DOGE-USD", "SOL-USD", "ETH-USD", "BTC-USD",
}

# Low-quality / clutter — sell candidates when size matters
EXIT_DEFAULT = {
    "JMIA", "POET", "TE", "CRWV", "IREN", "CPSH", "SIDU", "SPRB", "BYND", "BIVI",
    "DASH", "BIDU", "CRSP", "ARKG", "GBM O", "XLE", "SCCO",
}

# Never treat these tickers as the Yahoo equity with same symbol
TICKER_ALIASES = {
    # eToro instrument 100022 symbolFull=A is VAULTA crypto, not Agilent
    "A": "VAULTA",
}

ASSET_LABELS = {
    "SPCX": "SpaceX (eToro private/proxy) — NOT SPAC ETF",
    "VAULTA": "VAULTA crypto (eToro) — NOT Agilent",
    "MIRROR_TOTAL": "Copy-trading bucket",
}

SLEEVE_TARGETS = {
    "QUALITY": 0.45,
    "INDEX": 0.20,
    "MOMENTUM": 0.12,
    "THEME": 0.08,
    "CRYPTO_CORE": 0.08,
    "COPY": 0.05,
    "CASH": 0.02,
    "CRYPTO_ALT": 0.0,
    "EXIT": 0.0,
    "OTHER": 0.0,
    "SATELLITE": 0.0,
}

# Soft single-name caps (fraction of book) for drift reporting
NAME_CAPS = {
    "NVDA": 0.08, "TSM": 0.07, "CRWD": 0.06, "AMD": 0.05, "TSLA": 0.04,
    "SHOP": 0.04, "BTC": 0.07, "ETH": 0.04, "VOO": 0.10, "QQQ": 0.08,
    "SPCX": 0.04, "COST": 0.04, "APH": 0.05, "MIRROR_TOTAL": 0.05,
}


def normalize_ticker(ticker: str) -> str:
    t = (ticker or "").strip().upper()
    return TICKER_ALIASES.get(t, t)


def sleeve_for(ticker: str) -> str:
    t = normalize_ticker(ticker)
    if t == "MIRROR_TOTAL":
        return "COPY"
    if t in QUALITY_HOLD:
        return "QUALITY"
    if t in INDEX:
        return "INDEX"
    if t in MOMENTUM:
        return "MOMENTUM"
    if t in THEME:
        return "THEME"
    if t in CRYPTO_CORE:
        return "CRYPTO_CORE"
    if t in CRYPTO_ALT or t.endswith("-USD"):
        return "CRYPTO_ALT"
    if t in EXIT_DEFAULT:
        return "EXIT"
    return "OTHER"


def classify_action(
    ticker: str,
    grade: Optional[float],
    council: Optional[str],
    value_usd: float,
    weight_pct: float,
    n_brokers: int = 1,
    min_weight_pct: float = 2.5,
) -> Dict[str, Any]:
    """Return decision for a holding under balanced top-tier mandate.

    Multi-broker count is IGNORED as a sell reason.
    """
    t = normalize_ticker(ticker)
    council_u = (council or "").upper()
    sleeve = sleeve_for(t)
    reasons: List[str] = []
    keep: List[str] = []
    decision = "HOLD"

    # Copy bucket
    if t == "MIRROR_TOTAL":
        return {
            "ticker": t,
            "decision": "HOLD_BUCKET",
            "sleeve": "COPY",
            "reasons": ["Copy-trading bucket — manage people size, not ticker SELL"],
            "keep": ["Intentional copy book"],
            "alert": False,
        }

    # Quality compounders — never auto-SELL for defensive label
    if t in QUALITY_HOLD:
        keep.append("quality compounder / top-tier core")
        if grade is not None and grade < 38:
            decision = "WATCH"
            reasons.append(f"quality name but grade cracked ({grade})")
        else:
            decision = "HOLD"
            if t == "COST":
                keep.append("steady compounder — user mandate keep/grow")
            if t == "APH":
                keep.append("multi-broker ownership is fine")
            if t == "WMT":
                keep.append("quality retail compounder — small core OK")
        return _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct)

    # SpaceX theme
    if t == "SPCX":
        return _pack(
            t, "HOLD", "THEME",
            ["SpaceX thematic — not SPAC ETF"],
            ["High-conviction theme if thesis intact"],
            weight_pct, min_weight_pct,
        )

    # Crypto core
    if t in CRYPTO_CORE:
        keep.append("core crypto beta")
        if weight_pct > 7 and t == "BTC":
            decision = "TRIM"
            reasons.append(f"BTC overweight {weight_pct:.1f}% vs ~5% target")
        elif weight_pct > 12:
            decision = "TRIM"
            reasons.append(f"crypto core sleeve heavy ({weight_pct:.1f}% on this name)")
        else:
            decision = "HOLD"
        return _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct)

    # Crypto alts / dust
    if sleeve == "CRYPTO_ALT":
        if value_usd < 50:
            decision = "SELL"
            reasons.append("dust crypto alt — clean up")
        elif grade is not None and grade < 50:
            decision = "SELL" if weight_pct >= min_weight_pct or value_usd >= 300 else "TRIM"
            reasons.append("non-core crypto alt under balanced book")
        else:
            decision = "TRIM"
            reasons.append("non-core crypto — prefer BTC/ETH only")
        return _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct)

    # Explicit exit list
    if t in EXIT_DEFAULT:
        decision = "SELL"
        reasons.append("fails top-tier bar / low-quality clutter")
        if grade is not None and grade >= 55:
            decision = "TRIM"
            reasons.append("grade not terrible — cut size")
        return _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct)

    # Spec themes — satellite only
    if t in ("OKLO", "IONQ"):
        decision = "TRIM" if weight_pct >= 1.0 or value_usd >= 500 else "WATCH"
        reasons.append("spec theme — keep only small satellite")
        return _pack(t, decision, "THEME", reasons, keep, weight_pct, min_weight_pct)

    # Generic grade path
    if grade is not None:
        if grade < 40:
            decision = "SELL"
            reasons.append(f"very weak grade {grade}")
        elif grade < 48:
            decision = "TRIM"
            reasons.append(f"weak grade {grade} — not best-of-best")
        elif grade < 55:
            decision = "WATCH"
            reasons.append(f"soft grade {grade}")
        else:
            decision = "HOLD"
            keep.append(f"grade OK {grade}")
    else:
        decision = "WATCH"
        reasons.append("no grade")

    # Council SELL only matters if not protected quality and grade not solid
    if council_u == "SELL" and decision == "HOLD" and (grade is None or grade < 58):
        decision = "WATCH"
        reasons.append("system SELL flag — review")
    if council_u in ("BUY", "STRONG_BUY", "ACCUMULATE", "CORE BUY"):
        keep.append(council_u)

    # Name cap trim
    cap = NAME_CAPS.get(t)
    if cap is not None and weight_pct > cap * 100 + 0.5 and decision in ("HOLD", "WATCH"):
        decision = "TRIM"
        reasons.append(f"above size cap {cap*100:.0f}%")

    return _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct)


def _pack(t, decision, sleeve, reasons, keep, weight_pct, min_weight_pct):
    # Alerts only for material weights (except full SELL of known junk any size > $100 handled by caller)
    alert = decision in ("SELL", "TRIM") and weight_pct >= min_weight_pct
    return {
        "ticker": t,
        "decision": decision,
        "sleeve": sleeve,
        "reasons": reasons,
        "keep": keep,
        "alert": alert,
        "label": ASSET_LABELS.get(t),
    }


def sleeve_snapshot(positions: List[Dict[str, Any]], aum: float) -> Dict[str, Any]:
    """positions: list of {ticker, value_usd}"""
    from collections import defaultdict

    cur = defaultdict(float)
    for p in positions:
        t = normalize_ticker(p.get("ticker") or "")
        v = float(p.get("value_usd") or 0)
        cur[sleeve_for(t)] += v
    aum = aum or sum(cur.values()) or 1.0
    rows = []
    for s, tgt in SLEEVE_TARGETS.items():
        if s in ("OTHER", "SATELLITE", "EXIT", "CRYPTO_ALT") and cur.get(s, 0) <= 0 and tgt == 0:
            # still show EXIT/ALT if capital sits there
            if cur.get(s, 0) <= 0:
                continue
        now = cur.get(s, 0)
        rows.append({
            "sleeve": s,
            "now_usd": round(now, 2),
            "now_pct": round(now * 100 / aum, 2),
            "target_pct": round(tgt * 100, 1),
            "gap_pp": round(tgt * 100 - now * 100 / aum, 2),
            "gap_usd": round(tgt * aum - now, 2),
        })
    # ensure EXIT/ALT shown if present
    for s in ("EXIT", "CRYPTO_ALT", "OTHER"):
        if cur.get(s, 0) > 0 and not any(r["sleeve"] == s for r in rows):
            now = cur[s]
            rows.append({
                "sleeve": s,
                "now_usd": round(now, 2),
                "now_pct": round(now * 100 / aum, 2),
                "target_pct": 0.0,
                "gap_pp": round(-now * 100 / aum, 2),
                "gap_usd": round(-now, 2),
            })
    rows.sort(key=lambda r: -abs(r["gap_pp"]))
    return {"aum": aum, "sleeves": rows, "targets": SLEEVE_TARGETS}
