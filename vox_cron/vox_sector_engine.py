#!/usr/bin/env python3
"""
VOX Sector Engine
Merges three legacy crons into one idempotent entrypoint:
1. Portfolio sector scan via dashboard API (positions/watchlist).
2. S&P 500 sector leaders screener -> sp500_sector_leaders table.
3. Sector rotation detector via yfinance ETF proxies -> sector_rotation table.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: E402

import json
import os
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import yfinance as yf

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DASHBOARD_API = "https://web-production-9e321.up.railway.app/api"

DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_NAME = os.environ.get("DB_NAME", "railway")

SECTOR_ETFS = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Materials": "XLB",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_db_password() -> str:
    """Read DB password from environment, populated by hermes_secrets_bootstrap."""
    return os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD") or ""


def connect_db() -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=get_db_password(),
        dbname=DB_NAME,
        sslmode="require",
    )


def load_unified_grades() -> Dict[str, Any]:
    unified_path = SCRIPT_DIR / "vox_unified_grades.json"
    if not unified_path.exists():
        return {}
    with open(unified_path) as f:
        return json.load(f)


def get_unified_grade(ticker: str, unified_grades: Dict[str, Any]) -> float:
    if ticker in unified_grades.get("grades", {}):
        return unified_grades["grades"][ticker].get("grade", 0) or 0
    return 0


def dashboard_request(path: str) -> Any:
    req = urllib.request.Request(f"{DASHBOARD_API}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def record_cron_run(job_name: str, status: str, output: str, error: Optional[str] = None) -> None:
    try:
        body = json.dumps(
            {"job_name": job_name, "status": status, "output": output, "error": error}
        ).encode()
        req = urllib.request.Request(
            f"{DASHBOARD_API}/admin/cron-runs",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Workflow 1: Sector scan (portfolio + watchlist)
# ---------------------------------------------------------------------------
def fetch_positions() -> List[Dict[str, Any]]:
    try:
        data = dashboard_request("/positions")
        return data.get("positions", [])
    except Exception as e:
        print(f"❌ Failed to fetch positions: {e}")
        return []


def fetch_watchlist() -> List[Dict[str, Any]]:
    try:
        data = dashboard_request("/watchlist")
        return data.get("watchlist", [])
    except Exception as e:
        print(f"⚠️ Failed to fetch watchlist: {e}")
        return []


def scan_sectors(positions: List[Dict[str, Any]], watchlist: List[Dict[str, Any]]) -> str:
    sector_values = defaultdict(float)
    sector_positions = defaultdict(list)
    sector_pnl = defaultdict(float)

    for p in positions:
        sector = p.get("sector") or "Unknown"
        sector_values[sector] += float(p.get("live_value", 0) or 0)
        sector_positions[sector].append(p)
        sector_pnl[sector] += float(p.get("pnl", 0) or 0)

    sector_avg_grade: Dict[str, float] = {}
    sector_count: Dict[str, int] = {}
    for sector, pos_list in sector_positions.items():
        grades = [p.get("grade", 0) for p in pos_list if p.get("grade", 0) > 0]
        sector_avg_grade[sector] = sum(grades) / len(grades) if grades else 0
        sector_count[sector] = len(pos_list)

    total_value = sum(sector_values.values())
    sorted_sectors = sorted(sector_values.keys(), key=lambda s: sector_values[s], reverse=True)

    lines = []
    lines.append("=" * 70)
    lines.append(f"📊 VOX SECTOR SCAN — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)
    lines.append("")
    lines.append(
        f"{'Sector':<20} {'Value':>12} {'%':>6} {'Grade':>6} {'Positions':>10} {'P&L':>12}"
    )
    lines.append("-" * 70)

    for sector in sorted_sectors:
        val = sector_values[sector]
        pct = (val / total_value * 100) if total_value > 0 else 0
        avg_grade = sector_avg_grade.get(sector, 0)
        count = sector_count.get(sector, 0)
        pnl = sector_pnl[sector]
        lines.append(
            f"{sector:<20} ${val:>10,.0f} {pct:>5.1f}% {avg_grade:>5.1f} {count:>9} ${pnl:>10,.0f}"
        )

    lines.append("")

    weak_sectors = [
        s for s in sorted_sectors if sector_avg_grade.get(s, 0) < 50 and sector_values[s] > 1000
    ]
    if weak_sectors:
        lines.append("⚠️  WEAK SECTORS (avg grade < 50, value > $1K):")
        for sector in weak_sectors:
            lines.append(
                f"   {sector}: grade {sector_avg_grade[sector]:.1f}, ${sector_values[sector]:,.0f}"
            )
        lines.append("")

    strong_sectors = [s for s in sorted_sectors if sector_avg_grade.get(s, 0) >= 60]
    if strong_sectors:
        lines.append("✅ STRONG SECTORS (avg grade ≥ 60):")
        for sector in strong_sectors:
            lines.append(
                f"   {sector}: grade {sector_avg_grade[sector]:.1f}, ${sector_values[sector]:,.0f}"
            )
        lines.append("")

    watchlist_by_sector = defaultdict(list)
    for w in watchlist:
        sector = w.get("sector") or "Unknown"
        watchlist_by_sector[sector].append(w)

    lines.append("🔄 SECTOR ROTATION OPPORTUNITIES:")
    for sector in sorted_sectors[:5]:
        if sector_avg_grade.get(sector, 0) < 55:
            watch_tickers = [
                w["ticker"]
                for w in watchlist_by_sector.get(sector, [])
                if w.get("grade", 0) >= 60
            ]
            if watch_tickers:
                lines.append(f"   {sector}: Consider rotating to {', '.join(watch_tickers[:3])}")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow 2: S&P 500 sector leaders screener
# ---------------------------------------------------------------------------
def get_sp500_universe(conn: psycopg2.extensions.connection) -> List[Tuple[str, str]]:
    cur = conn.cursor()
    cur.execute("SELECT ticker, sector FROM sp500_universe WHERE is_active = TRUE")
    rows = cur.fetchall()
    cur.close()
    return rows


def store_leaders(
    conn: psycopg2.extensions.connection,
    leaders: List[Tuple[str, str, float, float, int]],
    run_date: datetime.date,
) -> int:
    cur = conn.cursor()
    for leader in leaders:
        ticker, sector, momentum, return_5d, rank = leader
        cur.execute(
            """
            INSERT INTO sp500_sector_leaders
            (run_date, sector, ticker, momentum_score, return_5d, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (run_date, sector, ticker) DO UPDATE SET
                momentum_score = EXCLUDED.momentum_score,
                return_5d = EXCLUDED.return_5d,
                created_at = NOW()
        """,
            (run_date, sector, ticker, momentum, return_5d),
        )
    conn.commit()
    cur.close()
    return len(leaders)


def run_sp500_sector_screener(conn: psycopg2.extensions.connection) -> Tuple[int, int]:
    universe = get_sp500_universe(conn)
    sectors: Dict[str, List[str]] = {}
    for ticker, sector in universe:
        sectors.setdefault(sector, []).append(ticker)

    leaders: List[Tuple[str, str, float, float, int]] = []
    run_date = datetime.now().date()  # type: ignore
    for sector, tickers in sectors.items():
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ticker, vox_grade, technical_score
            FROM vox_grades
            WHERE ticker = ANY(%s)
            ORDER BY vox_grade DESC, technical_score DESC
            LIMIT 3
        """,
            (tickers,),
        )
        for rank, row in enumerate(cur.fetchall(), 1):
            ticker, grade, tech = row
            momentum = tech or 0
            return_5d = 0.0
            leaders.append((ticker, sector, momentum, return_5d, rank))
        cur.close()

    stored = store_leaders(conn, leaders, run_date)
    return len(sectors), stored


# ---------------------------------------------------------------------------
# Workflow 3: Sector rotation detector
# ---------------------------------------------------------------------------
def create_sector_rotation_table(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sector_rotation (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(50) NOT NULL,
            etf_ticker VARCHAR(10) NOT NULL,
            snapshot_date DATE NOT NULL,
            price NUMERIC(10,2),
            volume BIGINT,
            return_1w NUMERIC(8,4),
            return_1m NUMERIC(8,4),
            return_3m NUMERIC(8,4),
            relative_strength NUMERIC(8,4),
            momentum_score NUMERIC(8,4),
            flow_intensity NUMERIC(8,4),
            rotation_signal VARCHAR(20),
            rank INTEGER,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(sector, snapshot_date)
        )
    """
    )
    conn.commit()
    cur.close()


def fetch_etf_data(etf: str, period: str = "3mo") -> Optional[Dict[str, Any]]:
    try:
        ticker = yf.Ticker(etf)
        hist = ticker.history(period=period)
        if hist.empty:
            return None

        current_price = float(hist["Close"].iloc[-1])
        current_volume = int(hist["Volume"].iloc[-1])

        price_1w = float(hist["Close"].iloc[-5]) if len(hist) >= 5 else current_price
        price_1m = float(hist["Close"].iloc[-20]) if len(hist) >= 20 else current_price
        price_3m = float(hist["Close"].iloc[0])

        return_1w = ((current_price - price_1w) / price_1w) * 100 if price_1w > 0 else 0
        return_1m = ((current_price - price_1m) / price_1m) * 100 if price_1m > 0 else 0
        return_3m = ((current_price - price_3m) / price_3m) * 100 if price_3m > 0 else 0

        return {
            "price": current_price,
            "volume": current_volume,
            "return_1w": return_1w,
            "return_1m": return_1m,
            "return_3m": return_3m,
        }
    except Exception as e:
        print(f"  Error fetching {etf}: {e}")
        return None


def relative_strength(sector_return: float, spy_return: float) -> float:
    return sector_return - spy_return if spy_return != 0 else 0


def momentum_score(data: Dict[str, Any]) -> float:
    return data["return_1w"] * 0.4 + data["return_1m"] * 0.35 + data["return_3m"] * 0.25


def flow_intensity(data: Dict[str, Any]) -> float:
    return abs(data["return_1w"]) * (data["volume"] / 1_000_000)


def rotation_signal(data: Dict[str, Any], rank: int) -> str:
    mom = data["momentum_score"]
    if rank <= 3 and mom > 5 and data["return_1w"] > data["return_1m"]:
        return "early"
    elif rank <= 3 and mom > 3:
        return "confirmed"
    elif rank <= 3 and mom > 0 and data["return_1w"] < data["return_1m"]:
        return "late"
    return "none"


def run_sector_rotation(conn: psycopg2.extensions.connection) -> Tuple[int, List[Dict[str, Any]]]:
    create_sector_rotation_table(conn)

    spy_data = fetch_etf_data("SPY")
    spy_return_1m = spy_data["return_1m"] if spy_data else 0

    sector_data: Dict[str, Dict[str, Any]] = {}
    for sector, etf in SECTOR_ETFS.items():
        data = fetch_etf_data(etf)
        if data:
            data["relative_strength"] = relative_strength(data["return_1m"], spy_return_1m)
            data["momentum_score"] = momentum_score(data)
            data["flow_intensity"] = flow_intensity(data)
            sector_data[sector] = data

    today = datetime.now().date()
    stored = 0
    ranked = sorted(sector_data.items(), key=lambda x: x[1]["momentum_score"], reverse=True)
    cur = conn.cursor()
    for rank, (sector, data) in enumerate(ranked, 1):
        signal = rotation_signal(data, rank)
        cur.execute(
            """
            INSERT INTO sector_rotation
            (sector, etf_ticker, snapshot_date, price, volume, return_1w, return_1m, return_3m,
             relative_strength, momentum_score, flow_intensity, rotation_signal, rank)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (sector, snapshot_date) DO UPDATE SET
                price = EXCLUDED.price,
                volume = EXCLUDED.volume,
                return_1w = EXCLUDED.return_1w,
                return_1m = EXCLUDED.return_1m,
                return_3m = EXCLUDED.return_3m,
                relative_strength = EXCLUDED.relative_strength,
                momentum_score = EXCLUDED.momentum_score,
                flow_intensity = EXCLUDED.flow_intensity,
                rotation_signal = EXCLUDED.rotation_signal,
                rank = EXCLUDED.rank,
                created_at = NOW()
        """,
            (
                sector,
                SECTOR_ETFS[sector],
                today,
                data["price"],
                data["volume"],
                data["return_1w"],
                data["return_1m"],
                data["return_3m"],
                data["relative_strength"],
                data["momentum_score"],
                data["flow_intensity"],
                signal,
                rank,
            ),
        )
        if cur.rowcount > 0:
            stored += 1
    conn.commit()
    cur.close()

    rotation_sectors = [
        {"sector": sector, "etf": SECTOR_ETFS[sector], "signal": rotation_signal(data, rank)}
        for rank, (sector, data) in enumerate(ranked, 1)
        if rotation_signal(data, rank) in ("early", "confirmed")
    ]
    return stored, rotation_sectors


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------
def main() -> None:
    started = datetime.now()
    print("=" * 70)
    print(f"🚀 VOX SECTOR ENGINE — {started.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # Workflow 1
    print("\n[1/3] Sector scan (positions + watchlist)")
    positions = fetch_positions()
    watchlist = fetch_watchlist()
    sector_report = scan_sectors(positions, watchlist)
    print(sector_report)
    record_cron_run("vox-sector-engine/scan", "ok", sector_report[:1000])

    # Workflows 2 & 3 share one DB connection
    conn = connect_db()
    try:
        # Workflow 2
        print("\n[2/3] S&P 500 sector leaders screener")
        num_sectors, leaders_stored = run_sp500_sector_screener(conn)
        print(f"  Sectors: {num_sectors} | Leaders stored: {leaders_stored}")

        # Workflow 3
        print("\n[3/3] Sector rotation detector")
        rotation_stored, rotation_opportunities = run_sector_rotation(conn)
        print(f"  ETF records stored/updated: {rotation_stored}")
        if rotation_opportunities:
            print("  🎯 Rotation signals:")
            for op in rotation_opportunities:
                print(f"     {op['signal'].upper()}: {op['sector']} ({op['etf']})")
    finally:
        conn.close()

    elapsed = (datetime.now() - started).total_seconds()
    print("\n" + "=" * 70)
    print(f"✅ Done in {elapsed:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
