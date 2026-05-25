#!/usr/bin/env python3
"""
VOX Autonomous Watchlist Screener
Scans for new opportunities, grades strong setups, runs LLM Council.
Runs daily after market close.

Pipeline:
1. Load watchlist from vox_watchlist.json
2. Run swing_screener.py on watchlist
3. Filter score >= 7
4. Run grade_system.py on filtered tickers
5. Run llm_council_v2.py on grade >= 65 tickers
6. Output: Suggested Plays (grade 80+) + Monitored (grade 65-79)
"""
import os, sys, json, subprocess, datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if '=' in line and not line.startswith('#') and not line.startswith(' '):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k, v)

WATCHLIST_FILE = os.path.expanduser("~/.hermes/scripts/vox_watchlist.json")
OUTPUT_FILE = os.path.expanduser("~/.hermes/scripts/vox_suggested_plays.json")

def load_watchlist():
    """Load tickers from watchlist or use default high-potential universe."""
    if os.path.exists(WATCHLIST_FILE):
        with open(WATCHLIST_FILE) as f:
            data = json.load(f)
            return [w['ticker'] for w in data.get('watchlist', [])]
    # Default high-potential universe
    return [
        # AI / Data Center
        'NVDA', 'AVGO', 'LRCX', 'TSLA', 'PLTR', 'CRWD', 'DDOG', 'SNOW',
        # Energy / Nuclear
        'CEG', 'VST', 'VRT', 'OKLO', 'SMR', 'NNE',
        # Semiconductors
        'AMD', 'TSM', 'INTC', 'QCOM', 'MRVL', 'MPWR',
        # Space
        'RKLB', 'ASTS', 'SPIR',
        # Quantum
        'RGTI', 'IONQ',
        # Biotech / Health
        'LLY', 'UNH', 'OSCR', 'VEEV',
        # Fintech
        'COIN', 'HOOD', 'SOFI',
        # Emerging / High Potential
        'POET', 'BE', 'GEV', 'ASTS', 'JOBY', 'ARCH',
        # ETFs
        'VOO', 'QQQ', 'VTI', 'SMH', 'XLK', 'XLE',
    ]

def run_screener(tickers):
    """Run swing screener on watchlist."""
    print(f"Running screener on {len(tickers)} tickers...")
    # For now, use grade_system as proxy since screener may not be available
    results = []
    for ticker in tickers[:15]:  # Limit to 15 per run due to API limits
        try:
            result = subprocess.run(
                ['python3', 'grade_system.py', ticker],
                capture_output=True, text=True, timeout=120,
                cwd=os.path.expanduser('~/.hermes/scripts')
            )
            output = result.stdout
            grade = None
            rec = None
            for line in output.split('\n'):
                if 'TOTAL GRADE' in line:
                    try:
                        grade = float(line.split('|')[1].strip().split('/')[0])
                    except:
                        pass
                if 'Recommendation:' in line:
                    rec = line.split(':', 1)[1].strip()
            if grade:
                results.append({'ticker': ticker, 'grade': grade, 'recommendation': rec})
                print(f"  {ticker}: {grade:.1f} — {rec}")
        except Exception as e:
            print(f"  {ticker}: ERROR — {e}")
    return results

def run_council_batch(tickers):
    """Run LLM Council on strong setups."""
    print(f"\nRunning LLM Council on {len(tickers)} strong setups...")
    results = []
    for t in tickers:
        try:
            result = subprocess.run(
                ['python3', 'llm_council_v2.py', t['ticker'], 'Swing setup analysis'],
                capture_output=True, text=True, timeout=180,
                cwd=os.path.expanduser('~/.hermes/scripts')
            )
            consensus = "UNKNOWN"
            for line in result.stdout.split('\n'):
                if 'CONSENSUS:' in line:
                    consensus = line.split(':', 1)[1].strip()
            t['council'] = consensus
            results.append(t)
            print(f"  {t['ticker']}: Council = {consensus}")
        except Exception as e:
            print(f"  {t['ticker']}: Council ERROR — {e}")
    return results

def main():
    print("=== VOX AUTONOMOUS SCREENER ===\n")
    print(f"Time: {datetime.datetime.now().isoformat()}\n")
    
    tickers = load_watchlist()
    print(f"Watchlist: {len(tickers)} tickers\n")
    
    # Step 1: Grade all
    graded = run_screener(tickers)
    
    # Step 2: Filter strong
    strong = [g for g in graded if g['grade'] >= 65]
    a_plus = [g for g in graded if g['grade'] >= 80]
    
    print(f"\nStrong setups (65+): {len(strong)}")
    print(f"A+ setups (80+): {len(a_plus)}")
    
    # Step 3: Council on strong
    if strong:
        counseled = run_council_batch(strong[:5])  # Top 5 only
        
        # Step 4: Filter for BULLISH consensus
        bullish = [c for c in counseled if 'BULLISH' in c.get('council', '')]
        print(f"\nBULLISH consensus: {len(bullish)}")
        
        # Save output
        output = {
            'timestamp': datetime.datetime.now().isoformat(),
            'all_graded': graded,
            'strong_setups': strong,
            'a_plus_setups': a_plus,
            'council_approved': bullish,
            'summary': {
                'total_scanned': len(tickers),
                'strong_count': len(strong),
                'a_plus_count': len(a_plus),
                'bullish_count': len(bullish)
            }
        }
        
        with open(OUTPUT_FILE, 'w') as f:
            json.dump(output, f, indent=2)
        
        # Telegram output
        print("\n\n=== TELEGRAM REPORT ===\n")
        print(f"🎯 VOX Screener — {datetime.datetime.now().strftime('%b %d')}")
        print(f"Scanned: {len(tickers)} | Strong: {len(strong)} | A+: {len(a_plus)} | BULLISH: {len(bullish)}\n")
        
        if bullish:
            print("⚡ COUNCIL-APPROVED PLAYS:")
            for b in bullish:
                print(f"  • {b['ticker']} — Grade {b['grade']:.1f}")
        elif a_plus:
            print("⚡ A+ SETUPS (no bullish consensus yet):")
            for a in a_plus:
                print(f"  • {a['ticker']} — Grade {a['grade']:.1f}")
        else:
            print("⏸️ No A+ setups today. Market may be extended.")
    else:
        print("\nNo strong setups found. Market may be extended.")

if __name__ == '__main__':
    main()
