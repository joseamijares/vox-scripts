#!/usr/bin/env python3
"""
VOX Research Orchestrator v2
Lightweight version — reads existing data, aggregates, updates council + watchlist
No subprocess calls (avoids timeouts)
"""

import json
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path.home() / ".hermes" / "scripts"

def load_json(filename, default=None):
    try:
        with open(SCRIPT_DIR / filename) as f:
            return json.load(f)
    except:
        return default

def aggregate_research():
    """Read all existing research files and aggregate."""
    signals = {}
    
    # Load watchlist graded data
    wl = load_json("vox_watchlist_graded.json", {})
    for item in wl.get("results", []):
        signals[item["ticker"]] = {
            "type": "watchlist",
            "score": item.get("grade", 50),
            "signal": item.get("signal", "HOLD"),
            "price": item.get("price", 0),
            "levels": {
                "buy_zone": item.get("buy_zone", 0),
                "stop_loss": item.get("stop_loss", 0),
                "target_1": item.get("target_1", 0),
                "target_2": item.get("target_2", 0)
            }
        }
    
    # Load portfolio graded data
    pf = load_json("vox_portfolio_graded.json", {})
    for item in pf.get("results", []):
        ticker = item["ticker"]
        if ticker not in signals:
            signals[ticker] = {
                "type": "portfolio",
                "score": item.get("grade", 50),
                "signal": item.get("signal", "HOLD"),
                "price": item.get("price", 0),
                "pnl_pct": item.get("pnl_pct", 0),
                "levels": {
                    "buy_zone": item.get("add_on_zone", item.get("buy_zone", 0)),
                    "stop_loss": item.get("trailing_stop", item.get("stop_loss", 0)),
                    "target_1": item.get("take_profit_1", item.get("target_1", 0)),
                    "target_2": item.get("take_profit_2", item.get("target_2", 0))
                }
            }
    
    # Load volume scan
    vol = load_json("vox_volume_scan.json", {})
    for alert in vol.get("alerts", []):
        ticker = alert.get("ticker", "")
        if ticker in signals:
            signals[ticker]["volume_ratio"] = alert.get("volume_ratio", 1)
            signals[ticker]["volume_signal"] = "SPIKE" if alert.get("volume_ratio", 1) > 2 else "NORMAL"
    
    # Load X momentum
    x = load_json("snapshots/x_momentum_latest.json", {})
    for item in x.get("results", []):
        ticker = item.get("ticker", "")
        if ticker in signals:
            signals[ticker]["x_sentiment"] = item.get("sentiment", "NEUTRAL")
            signals[ticker]["x_score"] = item.get("score", 50)
    
    # Load news digest
    news = load_json("vox_news_digest.json", {})
    if isinstance(news, dict):
        for h in news.get("headlines", [])[:10]:
            ticker = h.get("ticker", "")
            if ticker in signals:
                signals[ticker]["news_relevance"] = h.get("relevance", 50)
    
    # Load sector analysis for rotation signals
    sector = load_json("vox_sector_analysis.json", {})
    rotation = sector.get("rotation", "NEUTRAL")
    space_sector = sector.get("space_sector", {})
    space_movers = space_sector.get("movers", [])
    ai_sector = sector.get("ai_infra_sector", {})
    ai_movers = ai_sector.get("movers", [])
    quantum_sector = sector.get("quantum_sector", {})
    quantum_movers = quantum_sector.get("movers", [])
    cyber_sector = sector.get("cyber_sector", {})
    cyber_movers = cyber_sector.get("movers", [])
    bank_sector = sector.get("bank_sector", {})
    bank_movers = bank_sector.get("movers", [])
    emerging_sector = sector.get("emerging_sector", {})
    emerging_movers = emerging_sector.get("movers", [])
    aero_sector = sector.get("aero_sector", {})
    aero_movers = aero_sector.get("movers", [])
    
    # Inject space sector momentum into signals
    for mover in space_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "space_sector",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "space_momentum": mover.get("change_pct", 0),
                "catalyst": "SpaceX IPO sector rerating",
                "levels": {}
            }
        else:
            # Boost existing signal with space momentum (max +5, not +10)
            signals[ticker]["space_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject AI infra momentum into signals
    for mover in ai_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "ai_infra",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "ai_momentum": mover.get("change_pct", 0),
                "catalyst": "Leopold Aschenbrenner AI infrastructure 13F",
                "levels": {}
            }
        else:
            signals[ticker]["ai_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject quantum momentum into signals
    for mover in quantum_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "quantum",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "quantum_momentum": mover.get("change_pct", 0),
                "catalyst": "Quantum computing sector momentum",
                "levels": {}
            }
        else:
            signals[ticker]["quantum_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject cyber momentum into signals
    for mover in cyber_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "cyber",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "cyber_momentum": mover.get("change_pct", 0),
                "catalyst": "Cybersecurity sector momentum",
                "levels": {}
            }
        else:
            signals[ticker]["cyber_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject bank momentum into signals
    for mover in bank_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "banks",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "bank_momentum": mover.get("change_pct", 0),
                "catalyst": "Banking sector momentum",
                "levels": {}
            }
        else:
            signals[ticker]["bank_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject emerging momentum into signals
    for mover in emerging_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "emerging",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "emerging_momentum": mover.get("change_pct", 0),
                "catalyst": "Emerging markets sector momentum",
                "levels": {}
            }
        else:
            signals[ticker]["emerging_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    # Inject aero momentum into signals
    for mover in aero_movers:
        ticker = mover.get("ticker", "")
        if ticker not in signals:
            signals[ticker] = {
                "type": "aero",
                "score": 65,
                "signal": "BUY",
                "price": mover.get("price", 0),
                "aero_momentum": mover.get("change_pct", 0),
                "catalyst": "Aeronautics sector momentum",
                "levels": {}
            }
        else:
            signals[ticker]["aero_momentum"] = mover.get("change_pct", 0)
            signals[ticker]["score"] = min(100, signals[ticker].get("score", 50) + 5)
    
    return signals, rotation, space_movers, ai_movers, quantum_movers, cyber_movers, bank_movers, emerging_movers, aero_movers

def generate_council_input(signals):
    """Generate council votes from aggregated signals."""
    council_votes = []
    
    for ticker, data in signals.items():
        base_score = data.get("score", 50)
        volume_ratio = data.get("volume_ratio", 1)
        
        # Volume boost
        volume_boost = 0
        if volume_ratio > 3:
            volume_boost = 10
        elif volume_ratio > 2:
            volume_boost = 5
        
        final_score = min(100, base_score + volume_boost)
        
        # Determine consensus
        if final_score >= 75:
            consensus = "STRONG_BUY"
        elif final_score >= 60:
            consensus = "BUY"
        elif final_score >= 45:
            consensus = "HOLD"
        elif final_score >= 35:
            consensus = "TRIM"
        else:
            consensus = "SELL"
        
        council_votes.append({
            "ticker": ticker,
            "consensus": consensus,
            "score": final_score,
            "technical_score": base_score,
            "x_sentiment": data.get("x_sentiment", "NEUTRAL"),
            "volume_signal": data.get("volume_signal", "NEUTRAL"),
            "levels": data.get("levels", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    council_votes.sort(key=lambda x: x["score"], reverse=True)
    return council_votes

def update_watchlist(council_votes, space_movers=None, ai_movers=None, quantum_movers=None, cyber_movers=None, bank_movers=None, emerging_movers=None, aero_movers=None):
    """Update watchlist with top opportunities."""
    buy_opportunities = [v for v in council_votes if v["consensus"] in ["STRONG_BUY", "BUY"]]
    
    watchlist = []
    for vote in buy_opportunities[:50]:  # Increased from 20 to 50
        levels = vote.get("levels", {})
        watchlist.append({
            "ticker": vote["ticker"],
            "signal": vote["consensus"],
            "score": vote["score"],
            "grade": vote["score"],
            "buy_zone": levels.get("buy_zone", 0),
            "stop_loss": levels.get("stop_loss", 0),
            "target_1": levels.get("target_1", 0),
            "target_2": levels.get("target_2", 0),
            "sources": [
                f"Grade: {vote['score']}",
                f"X: {vote.get('x_sentiment', 'NEUTRAL')}",
                f"Vol: {vote.get('volume_signal', 'NEUTRAL')}"
            ],
            "added_at": datetime.now(timezone.utc).isoformat()
        })
    
    # Add space sector movers to watchlist
    if space_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in space_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                # Cap sector momentum score at 85 to prevent false 100s
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Space sector momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: SpaceX IPO ($SPCX) expected"
                    ],
                    "sector": "Space",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add AI infra movers to watchlist
    if ai_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in ai_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"AI infra momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Leopold Aschenbrenner 13F — ex-miners turned AI compute"
                    ],
                    "sector": "AI Infrastructure",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add quantum movers to watchlist
    if quantum_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in quantum_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Quantum momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Quantum computing sector — IONQ demo, Quantinuum IPO"
                    ],
                    "sector": "Quantum",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add cyber movers to watchlist
    if cyber_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in cyber_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Cyber momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Cybersecurity — AI threats, zero-trust mandates"
                    ],
                    "sector": "Cybersecurity",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add bank movers to watchlist
    if bank_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in bank_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Bank momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Banking — rate cycle, fintech disruption"
                    ],
                    "sector": "Banks",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add emerging movers to watchlist
    if emerging_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in emerging_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Emerging momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Emerging Markets — China stimulus, India growth"
                    ],
                    "sector": "Emerging Markets",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Add aero movers to watchlist
    if aero_movers:
        existing_tickers = {w["ticker"] for w in watchlist}
        for mover in aero_movers[:10]:
            ticker = mover.get("ticker", "")
            if ticker not in existing_tickers:
                raw_score = 65 + int(abs(mover.get("change_pct", 0)) / 2)
                sector_score = min(85, raw_score)
                watchlist.append({
                    "ticker": ticker,
                    "signal": "BUY",
                    "score": sector_score,
                    "grade": sector_score,
                    "buy_zone": mover.get("price", 0) * 0.95,
                    "stop_loss": mover.get("price", 0) * 0.85,
                    "target_1": mover.get("price", 0) * 1.15,
                    "target_2": mover.get("price", 0) * 1.30,
                    "sources": [
                        f"Aero momentum: {mover.get('change_pct', 0):+.1f}%",
                        "Catalyst: Aeronautics — Boeing recovery, eVTOL commercialization"
                    ],
                    "sector": "Aeronautics",
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
    
    # Save
    with open(SCRIPT_DIR / "vox_autonomous_watchlist.json", 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(watchlist),
            "watchlist": watchlist
        }, f, indent=2)
    
    # Also update vox_watchlist_graded.json for dashboard compatibility
    try:
        graded_path = SCRIPT_DIR / "vox_watchlist_graded.json"
        if graded_path.exists():
            with open(graded_path) as f:
                graded = json.load(f)
        else:
            graded = {"timestamp": "", "total": 0, "graded": 0, "errors": 0, "results": [], "errors_detail": []}
        
        graded_results = {r['ticker']: r for r in graded.get('results', [])}
        
        for w in watchlist:
            ticker = w['ticker']
            if ticker not in graded_results:
                graded_results[ticker] = {
                    'ticker': ticker,
                    'grade': w.get('grade', 65),
                    'signal': w.get('signal', 'BUY'),
                    'price': w.get('buy_zone', 0) * 1.05 if w.get('buy_zone') else 0,
                    'buy_zone': w.get('buy_zone', 0),
                    'stop_loss': w.get('stop_loss', 0),
                    'target_1': w.get('target_1', 0),
                    'target_2': w.get('target_2', 0),
                    'sector': w.get('sector', ''),
                    'sources': w.get('sources', [])
                }
            else:
                # Update existing
                graded_results[ticker]['grade'] = w.get('grade', graded_results[ticker].get('grade', 65))
                graded_results[ticker]['signal'] = w.get('signal', graded_results[ticker].get('signal', 'HOLD'))
                graded_results[ticker]['sector'] = w.get('sector', graded_results[ticker].get('sector', ''))
        
        graded['results'] = list(graded_results.values())
        graded['total'] = len(graded['results'])
        graded['graded'] = len([r for r in graded['results'] if r.get('grade')])
        graded['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        with open(graded_path, 'w') as f:
            json.dump(graded, f, indent=2)
        
        print(f"   📊 Updated vox_watchlist_graded.json: {len(graded['results'])} entries")
    except Exception as e:
        print(f"   ⚠️ Failed to update vox_watchlist_graded.json: {e}")
    
    # Sync to Supabase
    try:
        from vox_supabase_sync import sync_watchlist
        synced = sync_watchlist(watchlist)
        print(f"   ☁️  Synced {synced} to Supabase")
    except Exception as e:
        print(f"   ⚠️  Supabase sync failed: {e}")
    
    # Only print if there are opportunities
    if watchlist:
        print(f"   Watchlist: {len(watchlist)} opportunities")
        for w in watchlist[:5]:
            print(f"   🟢 {w['ticker']:6s} | {w['signal']:12s} | Score: {w['score']:2d}")

def update_council(council_votes):
    """Update council votes file."""
    with open(SCRIPT_DIR / "vox_council_votes.json", 'w') as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_votes": len(council_votes),
            "strong_buy": len([v for v in council_votes if v["consensus"] == "STRONG_BUY"]),
            "buy": len([v for v in council_votes if v["consensus"] == "BUY"]),
            "hold": len([v for v in council_votes if v["consensus"] == "HOLD"]),
            "trim": len([v for v in council_votes if v["consensus"] == "TRIM"]),
            "sell": len([v for v in council_votes if v["consensus"] == "SELL"]),
            "results": council_votes
        }, f, indent=2)

def main():
    # Aggregate existing data (no subprocess calls)
    signals, rotation, space_movers, ai_movers, quantum_movers, cyber_movers, bank_movers, emerging_movers, aero_movers = aggregate_research()
    
    # Generate council votes
    council_votes = generate_council_input(signals)
    
    # Update systems
    update_council(council_votes)
    update_watchlist(council_votes, space_movers, ai_movers, quantum_movers, cyber_movers, bank_movers, emerging_movers, aero_movers)
    
    # Only print summary if there are buy opportunities or thematic movers
    buy_count = len([v for v in council_votes if v['consensus'] in ['STRONG_BUY', 'BUY']])
    should_print = buy_count > 0 or len(space_movers) > 0 or len(ai_movers) > 0 or len(quantum_movers) > 0 or len(cyber_movers) > 0 or len(bank_movers) > 0 or len(emerging_movers) > 0 or len(aero_movers) > 0
    
    if should_print:
        if buy_count > 0:
            print(f"🤖 VOX RESEARCH — {buy_count} buy opportunities")
            for v in council_votes[:5]:
                if v['consensus'] in ['STRONG_BUY', 'BUY']:
                    print(f"   🟢 {v['ticker']:6s} | {v['consensus']:12s} | Score: {v['score']:2d}")
        
        if space_movers:
            space_tickers = [m['ticker'] for m in space_movers[:5]]
            print(f"   🚀 Space sector: {', '.join(space_tickers)}")
        
        if ai_movers:
            ai_tickers = [m['ticker'] for m in ai_movers[:5]]
            print(f"   🤖 AI infra: {', '.join(ai_tickers)}")
        
        if quantum_movers:
            quantum_tickers = [m['ticker'] for m in quantum_movers[:5]]
            print(f"   ⚛️ Quantum: {', '.join(quantum_tickers)}")
        
        if cyber_movers:
            cyber_tickers = [m['ticker'] for m in cyber_movers[:5]]
            print(f"   🔒 Cyber: {', '.join(cyber_tickers)}")
        
        if bank_movers:
            bank_tickers = [m['ticker'] for m in bank_movers[:5]]
            print(f"   🏦 Banks: {', '.join(bank_tickers)}")
        
        if emerging_movers:
            emerging_tickers = [m['ticker'] for m in emerging_movers[:5]]
            print(f"   🌍 Emerging: {', '.join(emerging_tickers)}")
        
        if aero_movers:
            aero_tickers = [m['ticker'] for m in aero_movers[:5]]
            print(f"   ✈️ Aero: {', '.join(aero_tickers)}")

if __name__ == "__main__":
    main()
