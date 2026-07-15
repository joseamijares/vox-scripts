#!/usr/bin/env python3
"""
Reliable price quotes via Yahoo Chart API (v8) — more current than stale yfinance cache.
Also used for backfill / crash detection.
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def yahoo_chart(
    symbol: str,
    range_: str = "1mo",
    interval: str = "1d",
    timeout: int = 20,
) -> Tuple[dict, List[dict]]:
    """Return (meta, daily bars). Bars have date/open/high/low/close/volume/adj_close."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?range={range_}&interval={interval}"
    )
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 VOX-PriceQuote/1.1"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        err = (data.get("chart") or {}).get("error")
        raise RuntimeError(f"Yahoo chart empty for {symbol}: {err}")
    result = result[0]
    meta = result.get("meta") or {}
    ts = result.get("timestamp") or []
    q = (result.get("indicators") or {}).get("quote") or [{}]
    q = q[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0].get(
        "adjclose"
    ) or []
    rows = []
    for i, t in enumerate(ts):
        if q.get("close") is None or i >= len(q["close"]) or q["close"][i] is None:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).date()
        rows.append(
            {
                "ticker": symbol.upper(),
                "date": d,
                "open": q["open"][i] if q.get("open") else None,
                "high": q["high"][i] if q.get("high") else None,
                "low": q["low"][i] if q.get("low") else None,
                "close": float(q["close"][i]),
                "volume": q["volume"][i] if q.get("volume") else None,
                "adj_close": float(adj[i])
                if i < len(adj) and adj[i] is not None
                else float(q["close"][i]),
                "source": "yahoo_chart",
            }
        )
    return meta, rows


def live_quote(symbol: str) -> Dict[str, Any]:
    meta, rows = yahoo_chart(symbol, range_="5d", interval="1d")
    last = rows[-1] if rows else {}
    prev = rows[-2] if len(rows) >= 2 else {}
    px = meta.get("regularMarketPrice") or last.get("close")
    prev_close = (
        meta.get("previousClose")
        or meta.get("chartPreviousClose")
        or prev.get("close")
    )
    chg = None
    if px and prev_close:
        chg = 100.0 * (float(px) - float(prev_close)) / float(prev_close)
    return {
        "ticker": symbol.upper(),
        "price": float(px) if px is not None else None,
        "prev_close": float(prev_close) if prev_close is not None else None,
        "change_pct": chg,
        "last_bar_date": last.get("date"),
        "last_bar_close": last.get("close"),
        "currency": meta.get("currency"),
        "exchange": meta.get("exchangeName"),
        "bars": rows,
    }
