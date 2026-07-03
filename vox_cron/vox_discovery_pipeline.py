#!/usr/bin/env python3
"""
VOX Discovery Pipeline v2.0
Merged single entrypoint for:
  - vox_discovery_engine.py (weekly full discovery)
  - vox_discovery_alert.py (Monday top-5 alert)
  - vox_proactive_discovery.py (Mon/Wed/Fri proactive scans)

Sources: momentum, sector momentum, trade signals, proactive themes/gaps/earnings,
         Yahoo Finance high-momentum candidates.
Outputs: discovery_queue, discovery_history, sector_opportunities, theme_alignment.

Usage:
  python vox_discovery_pipeline.py              # run full pipeline
  python vox_discovery_pipeline.py --monday-alert  # emit top-5 alert only
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap  # noqa: E402

import argparse
import os
import psycopg2
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "railway")

AGGRESSIVE_SECTORS = [
    "Quantum Computing",
    "Artificial Intelligence",
    "Nuclear Energy",
    "Hydrogen",
    "Cryptocurrency",
    "Emerging Markets Fintech",
    "Space",
    "Biotechnology",
    "Robotics",
    "Autonomous Vehicles",
]

DEFENSIVE_TICKERS = [
    "PG",
    "KO",
    "VZ",
    "JNJ",
    "PEP",
    "WMT",
    "COST",
    "HD",
    "LOW",
    "TGT",
    "SPG",
    "FRT",
    "O",
    "NNN",
    "STAG",
    "ADC",
    "SRC",
    "VICI",
    "EPR",
    "NEM",
    "GOLD",
    "AEM",
    "WPM",
    "RGLD",
    "KGC",
    "NG",
    "AU",
    "XLU",
    "NEE",
    "DUK",
    "SO",
    "AEP",
    "SRE",
    "EXC",
    "ED",
    "ETR",
    "FE",
]

THEME_CANDIDATES = {
    "quantum_computing": ["RGTI", "QBTS", "ARQQ", "IONQ"],
    "nuclear_energy": ["OKLO", "SMR", "NNE", "BWXT", "CCJ"],
    "space": ["ASTS", "RKLB", "SPCE", "MNTS", "LUNR"],
    "robotics_automation": ["TER", "ISRG", "SYNA", "CGNX"],
    "biotech_gene": ["CRSP", "EDIT", "NTLA", "BEAM", "VRTX"],
    "ai_infrastructure": ["CRDO", "VICR", "SMCI", "MRVL", "AVGO"],
    "hydrogen": ["PLUG", "BE", "BLDP", "FCEL", "CWR"],
    "em_fintech": ["DLO", "PAGS", "STNE", "AFRM", "SOFI"],
}

MOMENTUM_TICKERS = ["IONQ", "RGTI", "QBTS", "SE", "DUOL", "APP", "CRDO", "VICR", "TWST", "OKTA"]
EARNINGS_CANDIDATES = ["NVO", "APP", "CRDO", "IONQ", "DUOL", "SE", "CRWV", "OKLO"]


def connect_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
        sslmode="require",
    )


# ---------------------------------------------------------------------------
# Idempotency helpers
# ---------------------------------------------------------------------------
def is_in_portfolio(cur, ticker):
    cur.execute("SELECT 1 FROM positions WHERE ticker = %s", (ticker,))
    return cur.fetchone() is not None


def is_in_queue_pending(cur, ticker):
    cur.execute("SELECT 1 FROM discovery_queue WHERE ticker = %s AND status = 'pending'", (ticker,))
    return cur.fetchone() is not None


def is_in_active_universe(cur, ticker):
    cur.execute("SELECT 1 FROM universe_tiers WHERE ticker = %s AND active = TRUE", (ticker,))
    return cur.fetchone() is not None


def priority_from_grade(grade, default=5):
    return min(10, max(1, (grade - 60) // 3 if grade >= 65 else default))


def infer_theme(sector):
    sector = (sector or "").lower()
    if any(k in sector for k in ("quantum", "ai", "artificial")):
        return "Artificial Intelligence"
    if any(k in sector for k in ("nuclear", "energy")):
        return "Nuclear Energy"
    if any(k in sector for k in ("crypto", "bitcoin", "blockchain")):
        return "Cryptocurrency"
    if any(k in sector for k in ("fintech", "payments", "banking")):
        return "Emerging Markets Fintech"
    if any(k in sector for k in ("biotech", "gene", "health")):
        return "Biotechnology"
    return "General"


# ---------------------------------------------------------------------------
# Table setup
# ---------------------------------------------------------------------------
def init_tables():
    conn = connect_db()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_queue (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            discovery_source VARCHAR(50) NOT NULL,
            vox_grade INTEGER,
            technical_score INTEGER,
            fundamental_score INTEGER,
            sector VARCHAR(50),
            theme_alignment VARCHAR(50),
            discovery_date DATE DEFAULT NOW(),
            status VARCHAR(20) DEFAULT 'pending',
            priority INTEGER DEFAULT 5,
            notes TEXT,
            added_to_portfolio BOOLEAN DEFAULT FALSE,
            added_date DATE,
            outcome_return_pct DECIMAL(5,2),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(ticker, status)
        )
    """
    )
    cur.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'discovery_queue_ticker_status_key' AND conrelid = 'discovery_queue'::regclass
            ) THEN
                ALTER TABLE discovery_queue ADD CONSTRAINT discovery_queue_ticker_status_key UNIQUE (ticker, status);
            END IF;
        END
        $$;
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS discovery_history (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            discovery_week DATE NOT NULL,
            discovery_source VARCHAR(50),
            initial_grade INTEGER,
            final_grade INTEGER,
            action_taken VARCHAR(20),
            return_pct DECIMAL(5,2),
            lessons TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS sector_opportunities (
            id SERIAL PRIMARY KEY,
            sector VARCHAR(50) NOT NULL,
            momentum_score INTEGER,
            top_tickers TEXT,
            buy_count INTEGER,
            hold_count INTEGER,
            sell_count INTEGER,
            avg_sector_grade DECIMAL(5,2),
            best_ticker VARCHAR(10),
            best_grade INTEGER,
            week_date DATE DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS theme_alignment (
            id SERIAL PRIMARY KEY,
            theme VARCHAR(50) NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            alignment_score INTEGER,
            vox_grade INTEGER,
            sector VARCHAR(50),
            macro_signal VARCHAR(50),
            confidence INTEGER,
            week_date DATE DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    )

    conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Discovery sources
# ---------------------------------------------------------------------------
def discover_from_momentum(cur):
    """Top momentum from vox_grades (grade 75+, BUY actions, not in portfolio)."""
    cur.execute(
        """
        SELECT vg.ticker, vg.vox_grade, vg.technical_score, vg.fundamental_score, p.sector
        FROM vox_grades vg
        LEFT JOIN positions p ON vg.ticker = p.ticker
        WHERE vg.vox_grade >= 75
          AND vg.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
          AND p.ticker IS NULL
          AND vg.ticker NOT IN %s
        ORDER BY vg.vox_grade DESC
        LIMIT 20
    """,
        (tuple(DEFENSIVE_TICKERS),),
    )

    new = 0
    for ticker, grade, tech, fund, sector in cur.fetchall():
        if is_in_queue_pending(cur, ticker):
            continue
        theme = infer_theme(sector)
        priority = priority_from_grade(grade)
        cur.execute(
            """
            INSERT INTO discovery_queue
                (ticker, discovery_source, vox_grade, technical_score, fundamental_score,
                 sector, theme_alignment, priority, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, status) DO NOTHING
        """,
            (
                ticker,
                "momentum_scan",
                grade,
                tech,
                fund,
                sector,
                theme,
                priority,
                f"Grade {grade} momentum stock from full market scan",
            ),
        )
        if cur.rowcount:
            new += 1
    return new


def discover_from_sectors(cur):
    """Sector leaders from sector_momentum."""
    cur.execute(
        """
        SELECT sector, momentum_score, top_tickers, buy_count, hold_count, sell_count
        FROM sector_momentum
        WHERE momentum_score >= 50
        ORDER BY momentum_score DESC
        LIMIT 10
    """
    )

    new = 0
    for sector, momentum, tickers, buy_count, hold_count, sell_count in cur.fetchall():
        ticker_list = []
        if tickers:
            if isinstance(tickers, list):
                ticker_list = tickers
            else:
                ticker_list = [t.strip() for t in tickers.split(",")]

        for ticker in ticker_list[:3]:
            if is_in_portfolio(cur, ticker) or is_in_queue_pending(cur, ticker):
                continue
            cur.execute(
                "SELECT vox_grade, technical_score, fundamental_score FROM vox_grades WHERE ticker = %s",
                (ticker,),
            )
            grade_row = cur.fetchone()
            grade = grade_row[0] if grade_row else 50
            tech = grade_row[1] if grade_row else 50
            fund = grade_row[2] if grade_row else 50
            priority = min(10, max(1, momentum // 10))
            cur.execute(
                """
                INSERT INTO discovery_queue
                    (ticker, discovery_source, vox_grade, technical_score, fundamental_score,
                     sector, theme_alignment, priority, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, status) DO NOTHING
            """,
                (
                    ticker,
                    "sector_momentum",
                    grade,
                    tech,
                    fund,
                    sector,
                    infer_theme(sector),
                    priority,
                    f"Top {sector} stock, sector momentum {momentum}",
                ),
            )
            if cur.rowcount:
                new += 1
    return new


def discover_from_trade_signals(cur):
    """High composite trade signals not already held."""
    cur.execute(
        """
        SELECT ticker, composite_score, signal_type, target_price, stop_price
        FROM trade_signals
        WHERE composite_score >= 70
          AND ticker NOT IN (SELECT ticker FROM positions)
        ORDER BY composite_score DESC
        LIMIT 15
    """
    )

    new = 0
    for ticker, composite, signal_type, target, stop in cur.fetchall():
        if is_in_queue_pending(cur, ticker):
            continue
        cur.execute(
            """
            SELECT vg.vox_grade, vg.technical_score, vg.fundamental_score, p.sector
            FROM vox_grades vg
            LEFT JOIN positions p ON vg.ticker = p.ticker
            WHERE vg.ticker = %s
        """,
            (ticker,),
        )
        grade_row = cur.fetchone()
        grade = grade_row[0] if grade_row else 50
        tech = grade_row[1] if grade_row else 50
        fund = grade_row[2] if grade_row else 50
        sector = grade_row[3] if grade_row else "Unknown"
        priority = min(10, max(1, composite // 10))
        cur.execute(
            """
            INSERT INTO discovery_queue
                (ticker, discovery_source, vox_grade, technical_score, fundamental_score,
                 sector, theme_alignment, priority, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, status) DO NOTHING
        """,
            (
                ticker,
                "trade_signal",
                grade,
                tech,
                fund,
                sector,
                infer_theme(sector),
                priority,
                f"Trade signal {signal_type}, composite {composite}, target ${target}",
            ),
        )
        if cur.rowcount:
            new += 1
    return new


def discover_from_yahoo_gainers(cur):
    """Hardcoded high-momentum list; optionally fetches metadata via yfinance."""
    discovered = []
    try:
        import yfinance as yf
    except Exception as exc:
        print(f"  yfinance unavailable: {exc}")
        yf = None

    for ticker in MOMENTUM_TICKERS:
        info = None
        if yf:
            try:
                info = yf.Ticker(ticker).info
            except Exception as exc:
                print(f"  Skip {ticker}: {exc}")
        price = None
        market_cap = 0
        sector = "Unknown"
        industry = "Unknown"
        if info:
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            market_cap = info.get("marketCap", 0)
            sector = info.get("sector", "Unknown")
            industry = info.get("industry", "Unknown")
        if not yf or (price and market_cap > 500_000_000):
            discovered.append(
                {
                    "ticker": ticker,
                    "source": "yahoo_momentum",
                    "reason": f"High momentum stock: {sector}/{industry}",
                    "sector": sector,
                }
            )

    new = 0
    for disc in discovered:
        ticker = disc["ticker"]
        if is_in_portfolio(cur, ticker) or is_in_queue_pending(cur, ticker) or is_in_active_universe(cur, ticker):
            continue
        sector = disc.get("sector", "Unknown")
        cur.execute(
            """
            INSERT INTO discovery_queue
                (ticker, discovery_source, notes, sector, theme_alignment, priority, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'pending')
            ON CONFLICT (ticker, status) DO NOTHING
        """,
            (
                ticker,
                disc["source"],
                disc["reason"],
                sector,
                infer_theme(sector),
                5,
            ),
        )
        if cur.rowcount:
            new += 1
    return new


def discover_from_theme_gaps(cur):
    """Candidates in underrepresented aggressive themes."""
    new = 0
    for theme, tickers in THEME_CANDIDATES.items():
        for ticker in tickers:
            if is_in_portfolio(cur, ticker) or is_in_queue_pending(cur, ticker) or is_in_active_universe(cur, ticker):
                continue
            cur.execute(
                """
                INSERT INTO discovery_queue
                    (ticker, discovery_source, notes, theme_alignment, priority, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                ON CONFLICT (ticker, status) DO NOTHING
            """,
                (
                    ticker,
                    "theme_gap",
                    f"Underrepresented theme: {theme}",
                    theme.replace("_", " ").title(),
                    6,
                ),
            )
            if cur.rowcount:
                new += 1
    return new


def discover_from_earnings_surprises(cur):
    """Known recent earnings surprise candidates."""
    new = 0
    for ticker in EARNINGS_CANDIDATES:
        if is_in_portfolio(cur, ticker) or is_in_queue_pending(cur, ticker) or is_in_active_universe(cur, ticker):
            continue
        cur.execute(
            """
            INSERT INTO discovery_queue
                (ticker, discovery_source, notes, priority, status)
            VALUES (%s, %s, %s, %s, 'pending')
            ON CONFLICT (ticker, status) DO NOTHING
        """,
            (ticker, "earnings_surprise", "Recent earnings surprise/breakout", 6),
        )
        if cur.rowcount:
            new += 1
    return new


def refresh_sector_opportunities(cur):
    """Mirror current sector_momentum into sector_opportunities."""
    cur.execute(
        """
        SELECT sector, momentum_score, top_tickers, buy_count, hold_count, sell_count
        FROM sector_momentum
        ORDER BY momentum_score DESC
    """
    )
    rows = cur.fetchall()

    inserted = 0
    for sector, momentum, tickers, buy_count, hold_count, sell_count in rows:
        ticker_list = [t.strip() for t in tickers.split(",")] if isinstance(tickers, str) else (tickers or [])
        best_ticker = ticker_list[0] if ticker_list else None
        best_grade = None
        if best_ticker:
            cur.execute("SELECT vox_grade FROM vox_grades WHERE ticker = %s", (best_ticker,))
            gr = cur.fetchone()
            best_grade = gr[0] if gr else None

        avg_grade = None
        grades = []
        for t in ticker_list:
            cur.execute("SELECT vox_grade FROM vox_grades WHERE ticker = %s", (t,))
            gr = cur.fetchone()
            if gr is not None and gr[0] is not None:
                grades.append(gr[0])
        if grades:
            avg_grade = sum(grades) / len(grades)

        cur.execute(
            """
            INSERT INTO sector_opportunities
                (sector, momentum_score, top_tickers, buy_count, hold_count, sell_count,
                 avg_sector_grade, best_ticker, best_grade, week_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT DO NOTHING
        """,
            (
                sector,
                momentum,
                ",".join(ticker_list),
                buy_count,
                hold_count,
                sell_count,
                avg_grade,
                best_ticker,
                best_grade,
            ),
        )
        if cur.rowcount:
            inserted += 1
    return inserted


def refresh_theme_alignment(cur):
    """Populate theme_alignment from aggressive-sector queue entries."""
    cur.execute(
        """
        SELECT ticker, theme_alignment, sector, vox_grade, priority
        FROM discovery_queue
        WHERE theme_alignment != 'General'
          AND status = 'pending'
    """
    )
    inserted = 0
    for ticker, theme, sector, grade, priority in cur.fetchall():
        confidence = min(100, max(0, (grade or 50) + (priority or 5) * 3))
        cur.execute(
            """
            INSERT INTO theme_alignment
                (theme, ticker, alignment_score, vox_grade, sector, macro_signal, confidence, week_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            ON CONFLICT DO NOTHING
        """,
            (theme, ticker, confidence, grade, sector, "risk_on", confidence,),
        )
        if cur.rowcount:
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Monday alert
# ---------------------------------------------------------------------------
def get_top_discoveries(limit=5):
    conn = connect_db()
    cur = conn.cursor()

    # Prefer recent grade 80+ candidates not in portfolio, with active universe tier.
    cur.execute(
        """
        SELECT
            vg.ticker,
            vg.vox_grade,
            vg.action,
            vg.technical_score,
            vg.fundamental_score,
            ut.theme,
            dq.discovery_source,
            vg.catalysts
        FROM vox_grades vg
        JOIN universe_tiers ut ON vg.ticker = ut.ticker
        LEFT JOIN positions p ON vg.ticker = p.ticker
        LEFT JOIN discovery_queue dq ON vg.ticker = dq.ticker
        WHERE vg.vox_grade >= 80
          AND vg.action IN ('BUY', 'STRONG_BUY', 'ACCUMULATE')
          AND p.ticker IS NULL
          AND ut.active = TRUE
          AND (vg.generated_at > NOW() - INTERVAL '7 days'
               OR ut.discovery_date > NOW() - INTERVAL '30 days'
               OR dq.created_at > NOW() - INTERVAL '7 days')
        ORDER BY vg.vox_grade DESC, ut.priority DESC NULLS LAST
        LIMIT %s
    """,
        (limit,),
    )

    rows = cur.fetchall()
    conn.close()
    return rows


def format_alert(discoveries):
    if not discoveries:
        return (
            "🎯 VOX Weekly Discovery Alert\n"
            "=" * 60 + "\n"
            f"Date: {datetime.now().strftime('%Y-%m-%d')}\n"
            "No new grade 80+ discoveries this week. Your current portfolio is well-positioned."
        )

    lines = [
        "🚀 VOX WEEKLY DISCOVERY ALERT",
        "=" * 60,
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "Market Regime: RISK_ON",
        "",
        f"📊 TOP {len(discoveries)} NEW DISCOVERIES",
        "-" * 60,
    ]

    for i, (ticker, grade, action, tech, fund, theme, source, catalysts) in enumerate(discoveries, 1):
        lines.append(f"\n#{i} {ticker}")
        lines.append(f"   Grade: {grade} | Action: {action}")
        lines.append(f"   Tech: {tech} | Fund: {fund}")
        lines.append(f"   Theme: {theme or 'General'} | Source: {source or 'pipeline'}")
        if catalysts:
            lines.append(f"   Catalyst: {catalysts}")

    lines.extend(
        [
            "",
            "-" * 60,
            "💡 RECOMMENDATION: Review these tickers for potential allocation.",
            "   Consider position sizing based on your risk tolerance.",
            "",
            "📈 Next Steps:",
            "   1. Run deep-dive analysis on top 3",
            "   2. Check technical charts",
            "   3. Verify liquidity and volume",
            "   4. Allocate if thesis aligns with goals",
        ]
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_full_pipeline():
    print("\n🚀 VOX DISCOVERY PIPELINE — Full Scan")
    print("=" * 60)
    init_tables()

    conn = connect_db()
    cur = conn.cursor()

    totals = {}
    totals["momentum"] = discover_from_momentum(cur)
    totals["sectors"] = discover_from_sectors(cur)
    totals["trade_signals"] = discover_from_trade_signals(cur)
    totals["yahoo_gainers"] = discover_from_yahoo_gainers(cur)
    totals["theme_gaps"] = discover_from_theme_gaps(cur)
    totals["earnings_surprises"] = discover_from_earnings_surprises(cur)

    conn.commit()

    totals["sector_opportunities"] = refresh_sector_opportunities(cur)
    totals["theme_alignment"] = refresh_theme_alignment(cur)

    conn.commit()

    # Summary counts
    cur.execute("SELECT COUNT(*) FROM discovery_queue WHERE status = 'pending'")
    pending = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM discovery_queue WHERE discovery_date = CURRENT_DATE")
    today_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    print("\n📊 Discovery Summary:")
    for source, count in totals.items():
        print(f"  {source}: +{count}")
    print(f"  Pending queue total: {pending}")
    print(f"  Today's discoveries: {today_count}")

    # Always emit Monday-style alert summary (top 5) at the end of full run.
    alert = format_alert(get_top_discoveries(5))
    print("\n" + alert)
    return totals


def run_monday_alert_only():
    alert = format_alert(get_top_discoveries(5))
    print(alert)


def main():
    parser = argparse.ArgumentParser(description="VOX discovery pipeline")
    parser.add_argument(
        "--monday-alert",
        action="store_true",
        help="Emit the top-5 Monday alert summary only",
    )
    parser.add_argument("--init", action="store_true", help="Initialize tables only")
    args = parser.parse_args()

    if args.monday_alert:
        run_monday_alert_only()
    elif args.init:
        init_tables()
        print("✅ Discovery tables initialized")
    else:
        run_full_pipeline()


if __name__ == "__main__":
    main()
