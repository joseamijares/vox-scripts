#!/usr/bin/env python3
"""
VOX FMP (Financial Modeling Prep) client — stable API only.
Free tier: ~250 calls/day. Prefer ratios-ttm + financial-scores.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

BASE = "https://financialmodelingprep.com"


def _key() -> str:
    k = os.environ.get("FMP_API_KEY") or ""
    if not k:
        # bootstrap
        try:
            import hermes_secrets_bootstrap  # noqa: F401
        except Exception:
            pass
        k = os.environ.get("FMP_API_KEY") or ""
    if not k:
        # .env fallback
        env = os.path.expanduser("~/.hermes/.env")
        if os.path.exists(env):
            for line in open(env):
                if line.startswith("FMP_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"').strip("'")
                    os.environ["FMP_API_KEY"] = k
                    break
    if not k:
        raise RuntimeError("FMP_API_KEY not set")
    return k


def fmp_get(path: str, params: Optional[Dict[str, Any]] = None, retries: int = 2) -> Any:
    """GET /stable/... path. path like '/stable/ratios-ttm'."""
    params = dict(params or {})
    params["apikey"] = _key()
    qs = urllib.parse.urlencode(params)
    url = f"{BASE}{path}?{qs}"
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "VOX-Hermes/1.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            last_err = RuntimeError(f"FMP HTTP {e.code}: {body}")
            if e.code in (429, 500, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            raise last_err
        except Exception as e:
            last_err = e
            time.sleep(0.8 * (attempt + 1))
    raise last_err  # type: ignore


def get_profile(symbol: str) -> Optional[dict]:
    data = fmp_get("/stable/profile", {"symbol": symbol})
    return data[0] if isinstance(data, list) and data else None


def get_ratios_ttm(symbol: str) -> Optional[dict]:
    data = fmp_get("/stable/ratios-ttm", {"symbol": symbol})
    return data[0] if isinstance(data, list) and data else None


def get_key_metrics_ttm(symbol: str) -> Optional[dict]:
    data = fmp_get("/stable/key-metrics-ttm", {"symbol": symbol})
    return data[0] if isinstance(data, list) and data else None


def get_financial_scores(symbol: str) -> Optional[dict]:
    data = fmp_get("/stable/financial-scores", {"symbol": symbol})
    return data[0] if isinstance(data, list) and data else None


def get_growth(symbol: str) -> Optional[dict]:
    data = fmp_get("/stable/financial-growth", {"symbol": symbol, "limit": 1})
    return data[0] if isinstance(data, list) and data else None


def compute_fund_score(
    ratios: Optional[dict],
    scores: Optional[dict],
    growth: Optional[dict] = None,
    profile: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Map FMP fundamentals → 0–100 hygiene fund score.
    Not alpha — better ranking than empty Yahoo mush.
    """
    parts: List[float] = []
    notes: List[str] = []

    # Piotroski 0–9 → 0–100
    if scores and scores.get("piotroskiScore") is not None:
        try:
            pio = float(scores["piotroskiScore"])
            parts.append(min(100, max(0, pio / 9.0 * 100)))
            notes.append(f"Piotroski {pio:.0f}/9")
        except (TypeError, ValueError):
            pass

    # Altman Z (rough bands)
    if scores and scores.get("altmanZScore") is not None:
        try:
            z = float(scores["altmanZScore"])
            if z >= 3:
                parts.append(85)
            elif z >= 1.8:
                parts.append(60)
            elif z >= 1.1:
                parts.append(40)
            else:
                parts.append(20)
            notes.append(f"AltmanZ {z:.2f}")
        except (TypeError, ValueError):
            pass

    # Margins
    if ratios:
        npm = ratios.get("netProfitMarginTTM")
        if npm is not None:
            try:
                m = float(npm)
                # 0–30%+ maps to score
                parts.append(min(100, max(0, m * 250)))  # 20% → 50, 40% → 100
                notes.append(f"NPM {m*100:.1f}%")
            except (TypeError, ValueError):
                pass
        roe = ratios.get("returnOnEquityTTM") or ratios.get("roeTTM")
        if roe is not None:
            try:
                r = float(roe)
                parts.append(min(100, max(0, r * 200)))  # 15% → 30, 50% → 100
                notes.append(f"ROE {r*100:.1f}%")
            except (TypeError, ValueError):
                pass
        de = ratios.get("debtToEquityTTM") or ratios.get("debtEquityRatioTTM")
        if de is not None:
            try:
                d = float(de)
                # lower better; 0 → 90, 1 → 60, 2 → 35, 4+ → 15
                if d <= 0:
                    parts.append(90)
                elif d < 1:
                    parts.append(75)
                elif d < 2:
                    parts.append(55)
                elif d < 3:
                    parts.append(35)
                else:
                    parts.append(15)
                notes.append(f"D/E {d:.2f}")
            except (TypeError, ValueError):
                pass

    # Growth
    if growth and growth.get("revenueGrowth") is not None:
        try:
            g = float(growth["revenueGrowth"])
            parts.append(min(100, max(0, 50 + g * 100)))  # 0%→50, 20%→70, -20%→30
            notes.append(f"RevG {g*100:.1f}%")
        except (TypeError, ValueError):
            pass

    # Sector quality tilt from market cap stability (tiny)
    if profile and profile.get("marketCap"):
        try:
            mc = float(profile["marketCap"])
            if mc > 200e9:
                parts.append(70)
            elif mc > 20e9:
                parts.append(60)
            elif mc > 2e9:
                parts.append(50)
            else:
                parts.append(40)
        except (TypeError, ValueError):
            pass

    if not parts:
        return {"fund_score": None, "notes": "no_data", "components": {}}

    score = sum(parts) / len(parts)
    score = round(min(100, max(0, score)), 1)
    return {
        "fund_score": score,
        "notes": "; ".join(notes[:6]),
        "piotroski": scores.get("piotroskiScore") if scores else None,
        "altman_z": scores.get("altmanZScore") if scores else None,
        "net_margin": ratios.get("netProfitMarginTTM") if ratios else None,
        "roe": (ratios.get("returnOnEquityTTM") or ratios.get("roeTTM")) if ratios else None,
        "debt_equity": (ratios.get("debtToEquityTTM") or ratios.get("debtEquityRatioTTM"))
        if ratios
        else None,
        "rev_growth": growth.get("revenueGrowth") if growth else None,
    }
