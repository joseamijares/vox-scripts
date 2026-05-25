#!/usr/bin/env python3
"""
VOX Daily Rotation Analysis
Analyzes 8 holdings per day on a rotating schedule.
Runs grade + research + LLM Council for each.
Outputs Telegram-formatted report.

Usage: python3 vox_daily_analysis.py [day_of_week]
  day_of_week: monday, tuesday, wednesday, thursday, friday
  If omitted, uses today's day.
"""
import os, sys, json, subprocess, datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if '=' in line and not line.startswith('#') and not line.startswith(' '):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k, v)

# Daily rotation schedule
SCHEDULE = {
    'monday':    ['VOO', 'OSCR', 'CRWD', 'AAPL', 'MSFT', '0700.HK', 'BNB', 'CEG'],
    'tuesday':   ['AMD', 'ETH', 'DDOG', 'BIDU', 'SNOW', 'COIN', 'IREN', 'TSM'],
    'wednesday': ['QQQ', 'META', 'WMT', 'OKLO', 'SPOT', 'SMH', 'POET', 'CBRS'],
    'thursday':  ['BTC', 'VTI', 'PLTR', 'SHOP', 'XRP', 'DOGE', 'JMIA', 'DASH'],
    'friday':    ['APH', 'COST', 'TSLA', 'TRX', 'NVDA', 'CRWV', 'AVGO', 'ADA'],
}

def run_grade(ticker):
    """Run grade_system.py and return parsed result."""
    try:
        result = subprocess.run(
            ['python3', 'grade_system.py', ticker],
            capture_output=True, text=True, timeout=120, cwd=os.path.expanduser('~/.hermes/scripts')
        )
        output = result.stdout
        # Parse grade from output
        grade = None
        recommendation = None
        for line in output.split('\n'):
            if 'TOTAL GRADE' in line:
                try:
                    grade = float(line.split('|')[1].strip().split('/')[0])
                except:
                    pass
            if 'Recommendation:' in line:
                recommendation = line.split(':', 1)[1].strip()
        return {'grade': grade, 'recommendation': recommendation, 'raw': output[-2000:]}
    except Exception as e:
        return {'grade': None, 'recommendation': f'ERROR: {e}', 'raw': ''}

def run_research(ticker):
    """Run finance_research.py and return summary."""
    try:
        result = subprocess.run(
            ['python3', 'finance_research.py', ticker],
            capture_output=True, text=True, timeout=180, cwd=os.path.expanduser('~/.hermes/scripts')
        )
        output = result.stdout
        # Extract AI synthesis
        synthesis = ""
        in_synthesis = False
        for line in output.split('\n'):
            if 'AI SYNTHESIS' in line:
                in_synthesis = True
            elif in_synthesis and line.startswith('==='):
                break
            elif in_synthesis:
                synthesis += line + '\n'
        return {'synthesis': synthesis.strip()[:500], 'raw': output[-1500:]}
    except Exception as e:
        return {'synthesis': f'ERROR: {e}', 'raw': ''}

def run_council(ticker, context=""):
    """Run LLM Council v2."""
    try:
        result = subprocess.run(
            ['python3', 'llm_council_v2.py', ticker, context],
            capture_output=True, text=True, timeout=180, cwd=os.path.expanduser('~/.hermes/scripts')
        )
        output = result.stdout
        consensus = "UNKNOWN"
        for line in output.split('\n'):
            if 'CONSENSUS:' in line:
                consensus = line.split(':', 1)[1].strip()
        return {'consensus': consensus, 'raw': output[-2000:]}
    except Exception as e:
        return {'consensus': f'ERROR: {e}', 'raw': ''}

def main():
    day = sys.argv[1].lower() if len(sys.argv) > 1 else datetime.datetime.now().strftime('%A').lower()
    
    if day not in SCHEDULE:
        print(f"Unknown day: {day}. Use: monday, tuesday, wednesday, thursday, friday")
        sys.exit(1)
    
    tickers = SCHEDULE[day]
    print(f"=== VOX DAILY ANALYSIS: {day.upper()} ===\n")
    print(f"Analyzing {len(tickers)} positions...\n")
    
    results = []
    for ticker in tickers:
        print(f"\n--- {ticker} ---")
        grade_data = run_grade(ticker)
        research_data = run_research(ticker)
        council_data = run_council(ticker, f"Portfolio position, analyze for hold/trim/sell")
        
        results.append({
            'ticker': ticker,
            'grade': grade_data['grade'],
            'recommendation': grade_data['recommendation'],
            'consensus': council_data['consensus'],
            'synthesis': research_data['synthesis']
        })
        
        print(f"Grade: {grade_data['grade']:.1f if grade_data['grade'] else 'N/A'} | {grade_data['recommendation']}")
        print(f"Council: {council_data['consensus']}")
    
    # Output Telegram-formatted summary
    print("\n\n=== TELEGRAM REPORT ===\n")
    print(f"📊 VOX Daily Analysis — {day.title()}")
    print(f"Analyzed {len(tickers)} positions\n")
    
    for r in results:
        emoji = "🟢" if r['grade'] and r['grade'] >= 70 else "🟡" if r['grade'] and r['grade'] >= 55 else "🔴"
        print(f"{emoji} {r['ticker']:6s} Grade: {r['grade']:.1f if r['grade'] else 'N/A'}/100")
        print(f"   Rec: {r['recommendation']}")
        print(f"   Council: {r['consensus']}")
        print()

if __name__ == '__main__':
    main()
