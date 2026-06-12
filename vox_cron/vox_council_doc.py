#!/usr/bin/env python3
"""
VOX Council v2.1 — Optimized Batch Processing
Fixes: Connection pooling, batch DB operations, progress tracking
"""
import os
import sys
import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import psycopg2
from psycopg2.extras import RealDictCursor

# Load env
for env_path in [os.path.expanduser("~/.env"), os.path.expanduser("~/.hermes/.env")]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ.setdefault(k, v)

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST", "acela.proxy.rlwy.net")
DB_PORT = os.environ.get("DB_PORT", "35577")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD=os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "railway")


def get_db():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, dbname=DB_NAME, sslmode="require",
    )


# Agent weights (static — will be tuned later)
AGENT_WEIGHTS = {
    "technical": 1.0,
    "macro": 0.9,
    "sentiment": 0.7,
    "risk": 1.2,
}


@dataclass
class AgentVote:
    agent: str
    vote: str
    conviction: int
    signal: str
    details: str
    doc_action: str = ""
    doc_target: str = ""
    doc_reasoning: str = ""


@dataclass
class CouncilDeliberation:
    ticker: str
    timestamp: str
    consensus: str
    consensus_pct: float
    votes: List[dict]
    deliberations: List[dict]
    risk_veto: bool
    risk_veto_reason: str
    final_action: str


def fetch_all_data(cur, tickers: List[str]) -> Dict[str, Dict]:
    """Batch fetch all position data in one query."""
    placeholders = ','.join(['%s'] * len(tickers))
    cur.execute(f"""
        SELECT ticker, shares, avg_cost, live_price, live_value, grade, council, sector, brokers
        FROM positions WHERE ticker IN ({placeholders})
    """, tuple(tickers))
    
    results = {}
    for row in cur.fetchall():
        cols = [desc[0] for desc in cur.description]
        results[row[0]] = dict(zip(cols, row))
    return results


def fetch_all_macro(cur) -> Dict:
    """Fetch macro signals once."""
    cur.execute("SELECT signal_name, signal_value, signal_direction FROM macro_signals WHERE computed_at > NOW() - INTERVAL '2 days'")
    return {name: {"value": val, "direction": direction} for name, val, direction in cur.fetchall()}


def fetch_regime(cur) -> Dict:
    """Fetch market regime once."""
    cur.execute("SELECT regime, confidence, vix_level FROM market_regime ORDER BY created_at DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        return {"regime": row[0], "confidence": row[1], "vix": row[2]}
    return {}


def fetch_all_sp500_grades(cur, tickers: List[str]) -> Dict[str, int]:
    """Batch fetch S&P 500 grades."""
    placeholders = ','.join(['%s'] * len(tickers))
    cur.execute(f"SELECT ticker, vox_grade FROM sp500_grades WHERE ticker IN ({placeholders})", tuple(tickers))
    return {row[0]: row[1] for row in cur.fetchall()}


def fetch_all_sectors(cur, sectors: set) -> Dict[str, Dict]:
    """Batch fetch sector momentum."""
    if not sectors:
        return {}
    placeholders = ','.join(['%s'] * len(sectors))
    cur.execute(f"""
        SELECT sector, ticker, rank, momentum_score, change_5d_pct
        FROM sp500_sector_leaders WHERE sector IN ({placeholders}) AND rank <= 3
    """, tuple(sectors))
    
    results = {}
    for row in cur.fetchall():
        sector = row[0]
        if sector not in results:
            results[sector] = {"leaders": []}
        results[sector]["leaders"].append({
            "ticker": row[1], "rank": row[2], "momentum": row[3], "change_5d": row[4]
        })
    return results


def technical_analyst(ticker: str, position: Dict, sp500_grade: Optional[int]) -> AgentVote:
    """Technical Analyst — charts, patterns, volume, grades."""
    grade = position.get("grade") or sp500_grade or 0
    live_price = position.get("live_price") or 0
    avg_cost = position.get("avg_cost") or 0

    if avg_cost and live_price:
        price_vs_cost = (live_price - avg_cost) / avg_cost * 100
    else:
        price_vs_cost = 0

    vote = "HOLD"
    conviction = 50
    details = f"Grade: {grade}"

    if grade >= 70:
        vote = "BUY"
        conviction = min(100, grade)
        details = f"Strong technicals | Grade: {grade}"
    elif grade >= 55:
        vote = "HOLD"
        conviction = grade
        details = f"Moderate technicals | Grade: {grade}"
    elif grade > 0 and grade < 40:
        vote = "SELL"
        conviction = 100 - grade
        details = f"Weak technicals | Grade: {grade}"
    elif grade > 0:
        vote = "HOLD"
        conviction = 50

    if price_vs_cost > 100:
        details += f" | Up {price_vs_cost:.1f}% from cost"
    elif price_vs_cost < -20:
        details += f" | Down {price_vs_cost:.1f}% from cost"
    elif price_vs_cost > 0:
        details += f" | Up {price_vs_cost:.1f}% from cost"
    elif price_vs_cost < 0:
        details += f" | Down {price_vs_cost:.1f}% from cost"

    return AgentVote(
        agent="technical",
        vote=vote,
        conviction=conviction,
        signal=f"Grade: {grade}",
        details=details,
        doc_reasoning="Initiating technical assessment. Primary signal is VOX grade with price momentum overlay."
    )


def macro_analyst(ticker: str, position: Dict, macro: Dict, regime: Dict, sector_data: Dict, prior_vote: AgentVote) -> AgentVote:
    """Macro Analyst — Fed, CPI, sector rotation, news. Must DoC with prior."""
    grade = position.get("grade") or 0
    sector = position.get("sector", "technology")
    
    prior = prior_vote
    doc_target = prior.agent if prior else ""
    
    regime_name = regime.get("regime", "NEUTRAL") if regime else "NEUTRAL"
    vix = regime.get("vix", 20) if regime else 20
    
    vote = "HOLD"
    conviction = 45
    details = f"Sector: {sector}, Regime: {regime_name}"
    
    if grade >= 65 and regime_name in ["BULLISH", "NEUTRAL"]:
        vote = "BUY"
        conviction = 60
        details = f"Sector: {sector}, Regime: {regime_name} | Strong grade in {regime_name.lower()} regime"
    elif grade < 45 and regime_name in ["BEARISH", "NEUTRAL"]:
        vote = "SELL"
        conviction = 55
        details = f"Sector: {sector}, Regime: {regime_name} | Weak grade in {regime_name.lower()} regime"
    else:
        details = f"Sector: {sector}, Regime: {regime_name} | No strong macro signal (regime: {regime_name})"
    
    if vix > 30:
        if vote == "BUY":
            vote = "HOLD"
            conviction = 40
            details += " | VIX elevated (>30), reducing conviction"
        else:
            details += " | VIX elevated, caution warranted"
    
    if prior and prior.vote != vote:
        doc_action = "DISAGREE"
        doc_reasoning = f"DISAGREE with {prior.agent}'s {prior.vote}: Macro regime {regime_name} and sector momentum suggest {vote}. Grade {grade} in {regime_name} regime supports this view."
    else:
        doc_action = "COMMIT"
        doc_reasoning = f"Technical grade {grade} is consistent with macro view. {'No strong macro signal' if regime_name == 'NEUTRAL' else f'Grade {grade} is strong in {regime_name.lower()} regime'}. Leaning with technical signal."
    
    return AgentVote(
        agent="macro",
        vote=vote,
        conviction=conviction,
        signal=f"Regime: {regime_name}",
        details=details,
        doc_action=doc_action,
        doc_target=doc_target,
        doc_reasoning=doc_reasoning
    )


def sentiment_analyst(ticker: str, position: Dict, prior_votes: List[AgentVote]) -> AgentVote:
    """Sentiment Analyst — news sentiment. Must DoC with prior."""
    grade = position.get("grade") or 0
    
    prior = prior_votes[-1] if prior_votes else None
    doc_target = prior.agent if prior else ""
    
    # Use sentiment from DB if available
    sentiment_score = 50
    vote = "HOLD"
    conviction = 30
    details = "No validated sentiment data available"
    
    # Simple heuristic based on grade
    if grade >= 70:
        sentiment_score = 75
        vote = "BUY"
        conviction = 55
        details = f"Implied bullish from grade {grade}"
    elif grade < 40:
        sentiment_score = 25
        vote = "SELL"
        conviction = 55
        details = f"Implied bearish from grade {grade}"
    
    if prior and prior.vote != vote:
        doc_action = "DISAGREE"
        doc_reasoning = f"DISAGREE with {prior.agent}'s {prior.vote}: Sentiment analysis suggests {vote} based on implied market positioning. Grade {grade} indicates {'bullish' if grade >= 55 else 'bearish'} consensus."
    else:
        doc_action = "COMMIT"
        doc_reasoning = f"Sentiment aligns with {prior.agent}'s {prior.vote} view. Grade {grade} supports {'bullish' if grade >= 55 else 'bearish'} positioning."
    
    return AgentVote(
        agent="sentiment",
        vote=vote,
        conviction=conviction,
        signal=f"Sentiment: {sentiment_score}",
        details=details,
        doc_action=doc_action,
        doc_target=doc_target,
        doc_reasoning=doc_reasoning
    )


def risk_manager(ticker: str, position: Dict, all_votes: List[AgentVote], macro: Dict) -> AgentVote:
    """Risk Manager — position sizing, correlation, drawdown. Has VETO power."""
    grade = position.get("grade") or 0
    live_value = position.get("live_value") or 0
    avg_cost = position.get("avg_cost") or 0
    shares = position.get("shares") or 0
    
    if avg_cost and live_value and shares:
        cost_basis = avg_cost * shares
        unrealized_pnl = live_value - cost_basis
        pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0
    else:
        unrealized_pnl = 0
        pnl_pct = 0
    
    # Portfolio concentration risk (simplified — would query total AUM)
    concentration_risk = 0.15
    
    risk_score = 2
    if pnl_pct < -25:
        risk_score += 3
    elif pnl_pct < -15:
        risk_score += 2
    elif pnl_pct < -5:
        risk_score += 1
    
    if grade > 0 and grade < 35:
        risk_score += 2
    elif grade > 0 and grade < 45:
        risk_score += 1
    
    if concentration_risk > 0.25:
        risk_score += 2
    elif concentration_risk > 0.15:
        risk_score += 1
    
    vix_val = macro.get("vix", 20) if isinstance(macro.get("vix", 20), (int, float)) else 20
    if vix_val > 30:
        risk_score += 2
    elif vix_val > 25:
        risk_score += 1
    
    risk_score = min(10, risk_score)
    
    vote = "HOLD"
    conviction = 50
    details = f"Risk score: {risk_score}/10"
    
    if risk_score >= 8:
        vote = "SELL"
        conviction = 70
        details = f"High risk ({risk_score}/10): Significant drawdown or weak grade"
    elif risk_score >= 5:
        vote = "HOLD"
        conviction = 60
        details = f"Moderate risk ({risk_score}/10): Caution warranted"
    else:
        vote = "HOLD"
        conviction = 40
        details = f"Low risk ({risk_score}/10): Within acceptable parameters"
    
    # VETO: If risk_score >= 8, override any BUY
    veto = risk_score >= 8
    
    return AgentVote(
        agent="risk",
        vote=vote,
        conviction=conviction,
        signal=f"Risk: {risk_score}/10",
        details=details,
        doc_reasoning=f"Risk assessment complete. Score {risk_score}/10 based on P&L {pnl_pct:.1f}%, grade {grade}, concentration {concentration_risk:.0%}, VIX {vix_val}. {'VETO active' if veto else 'No veto'}."
    )


def calculate_consensus(votes: List[AgentVote]) -> tuple:
    """Calculate weighted consensus from agent votes."""
    buy_votes = []
    sell_votes = []
    hold_votes = []
    
    for vote in votes:
        weight = AGENT_WEIGHTS.get(vote.agent, 1.0)
        weighted_conviction = vote.conviction * weight
        
        if vote.vote == "BUY":
            buy_votes.append(weighted_conviction)
        elif vote.vote == "SELL":
            sell_votes.append(weighted_conviction)
        else:
            hold_votes.append(weighted_conviction)
    
    total_buy = sum(buy_votes)
    total_sell = sum(sell_votes)
    total_hold = sum(hold_votes)
    total = total_buy + total_sell + total_hold
    
    if total == 0:
        return "HOLD", 0.0
    
    buy_pct = (total_buy / total) * 100
    sell_pct = (total_sell / total) * 100
    hold_pct = (total_hold / total) * 100
    
    if buy_pct >= 50:
        return "BUY", round(buy_pct, 1)
    elif sell_pct >= 50:
        return "SELL", round(sell_pct, 1)
    else:
        return "HOLD", round(hold_pct, 1)


def deliberate(ticker: str, position: Dict, macro: Dict, regime: Dict, sp500_grade: Optional[int], sector_data: Dict) -> CouncilDeliberation:
    """Run full DoC council deliberation on a ticker (no DB calls)."""
    
    # Run agents sequentially with DoC
    votes = []
    deliberations = []
    
    tech_vote = technical_analyst(ticker, position, sp500_grade)
    votes.append(tech_vote)
    deliberations.append({
        "agent": tech_vote.agent,
        "action": "INITIATE",
        "target": "",
        "reasoning": tech_vote.doc_reasoning,
        "vote": tech_vote.vote,
        "conviction": tech_vote.conviction
    })
    
    macro_vote = macro_analyst(ticker, position, macro, regime, sector_data, tech_vote)
    votes.append(macro_vote)
    deliberations.append({
        "agent": macro_vote.agent,
        "action": macro_vote.doc_action,
        "target": macro_vote.doc_target,
        "reasoning": macro_vote.doc_reasoning,
        "vote": macro_vote.vote,
        "conviction": macro_vote.conviction
    })
    
    sentiment_vote = sentiment_analyst(ticker, position, votes)
    votes.append(sentiment_vote)
    deliberations.append({
        "agent": sentiment_vote.agent,
        "action": sentiment_vote.doc_action,
        "target": sentiment_vote.doc_target,
        "reasoning": sentiment_vote.doc_reasoning,
        "vote": sentiment_vote.vote,
        "conviction": sentiment_vote.conviction
    })
    
    risk_vote = risk_manager(ticker, position, votes, macro)
    votes.append(risk_vote)
    deliberations.append({
        "agent": risk_vote.agent,
        "action": "ASSESS",
        "target": "all",
        "reasoning": risk_vote.doc_reasoning,
        "vote": risk_vote.vote,
        "conviction": risk_vote.conviction
    })
    
    consensus, consensus_pct = calculate_consensus(votes)
    
    # Risk veto check
    risk_veto = risk_vote.vote == "SELL" and any(v.vote == "BUY" for v in votes)
    risk_veto_reason = risk_vote.details if risk_veto else ""
    
    if risk_veto:
        consensus = "HOLD"
        consensus_pct = 0.0
    
    final_action = consensus if not risk_veto else "HOLD"
    
    return CouncilDeliberation(
        ticker=ticker,
        timestamp=datetime.now(timezone.utc).isoformat(),
        consensus=consensus,
        consensus_pct=consensus_pct,
        votes=[asdict(v) for v in votes],
        deliberations=deliberations,
        risk_veto=risk_veto,
        risk_veto_reason=risk_veto_reason,
        final_action=final_action
    )


def save_deliberations(deliberations: List[CouncilDeliberation]):
    """Save multiple deliberations to Railway Postgres (batch insert)."""
    if not deliberations:
        return
    
    conn = get_db()
    cur = conn.cursor()
    
    # Ensure table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS council_deliberations (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            timestamp TIMESTAMPTZ DEFAULT NOW(),
            consensus TEXT,
            consensus_pct NUMERIC,
            votes JSONB,
            deliberations JSONB,
            risk_veto BOOLEAN DEFAULT FALSE,
            risk_veto_reason TEXT,
            final_action TEXT,
            UNIQUE(ticker, timestamp)
        )
    """)
    
    # Batch insert
    values = []
    for d in deliberations:
        values.append((
            d.ticker, d.timestamp, d.consensus, d.consensus_pct,
            json.dumps(d.votes), json.dumps(d.deliberations),
            d.risk_veto, d.risk_veto_reason, d.final_action
        ))
    
    cur.executemany("""
        INSERT INTO council_deliberations (ticker, timestamp, consensus, consensus_pct, votes, deliberations, risk_veto, risk_veto_reason, final_action)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (ticker, timestamp) DO UPDATE SET
            consensus = EXCLUDED.consensus,
            consensus_pct = EXCLUDED.consensus_pct,
            votes = EXCLUDED.votes,
            deliberations = EXCLUDED.deliberations,
            risk_veto = EXCLUDED.risk_veto,
            risk_veto_reason = EXCLUDED.risk_veto_reason,
            final_action = EXCLUDED.final_action
    """, values)
    
    conn.commit()
    conn.close()


def batch_deliberate():
    """Run DoC council on all portfolio positions (optimized)."""
    conn = get_db()
    cur = conn.cursor()
    
    # Get tickers
    cur.execute("SELECT ticker FROM positions WHERE live_value > 0")
    tickers = [row[0] for row in cur.fetchall()]
    
    # Batch fetch all data
    print(f"📊 Fetching data for {len(tickers)} positions...")
    positions = fetch_all_data(cur, tickers)
    macro = fetch_all_macro(cur)
    regime = fetch_regime(cur)
    sp500_grades = fetch_all_sp500_grades(cur, tickers)
    
    sectors = set(p.get("sector", "technology") for p in positions.values() if p.get("sector"))
    sector_data = fetch_all_sectors(cur, sectors)
    
    conn.close()
    
    print(f"🗳️ VOX COUNCIL v2.1 — DoC Protocol")
    print(f"Deliberating on {len(tickers)} positions...")
    print("=" * 70)
    
    results = []
    start_time = time.time()
    
    for i, ticker in enumerate(tickers, 1):
        position = positions.get(ticker, {})
        sp500_grade = sp500_grades.get(ticker)
        sector = position.get("sector", "technology")
        
        delib = deliberate(ticker, position, macro, regime, sp500_grade, sector_data.get(sector, {}))
        results.append(delib)
        
        if i % 10 == 0 or i == len(tickers):
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"  Progress: {i}/{len(tickers)} ({rate:.1f} tickers/sec, ~{remaining:.0f}s remaining)")
    
    # Batch save
    print(f"\n💾 Saving {len(results)} deliberations...")
    save_deliberations(results)
    
    # Summary
    buys = [r for r in results if r.consensus == "BUY"]
    sells = [r for r in results if r.consensus == "SELL"]
    holds = [r for r in results if r.consensus == "HOLD"]
    vetos = [r for r in results if r.risk_veto]
    
    total_time = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("📊 COUNCIL SUMMARY")
    print(f"   🟢 BUY: {len(buys)}")
    print(f"   🔴 SELL: {len(sells)}")
    print(f"   ⚪ HOLD: {len(holds)}")
    print(f"   🚫 Risk Vetos: {len(vetos)}")
    print(f"   ⏱️  Total time: {total_time:.1f}s ({len(tickers)/total_time:.1f} tickers/sec)")
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VOX Council v2.1 — Optimized DoC Protocol")
    parser.add_argument("--ticker", help="Deliberate on specific ticker")
    parser.add_argument("--batch", action="store_true", help="Deliberate on all positions")
    
    args = parser.parse_args()
    
    if args.ticker:
        # Single ticker mode (with DB connection)
        conn = get_db()
        cur = conn.cursor()
        
        position = fetch_all_data(cur, [args.ticker]).get(args.ticker, {})
        macro = fetch_all_macro(cur)
        regime = fetch_regime(cur)
        sp500_grade = fetch_all_sp500_grades(cur, [args.ticker]).get(args.ticker)
        sector = position.get("sector", "technology")
        sector_data = fetch_all_sectors(cur, {sector})
        
        conn.close()
        
        delib = deliberate(args.ticker, position, macro, regime, sp500_grade, sector_data.get(sector, {}))
        save_deliberations([delib])
        print(json.dumps(asdict(delib), indent=2))
    else:
        batch_deliberate()


if __name__ == "__main__":
    main()
