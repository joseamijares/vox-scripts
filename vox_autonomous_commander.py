#!/usr/bin/env python3
"""
VOX Autonomous Commander — Central orchestration system
Runs daily at 8 AM ET and 6 PM ET.

Pipeline:
1. Portfolio rotation analysis (8 positions)
2. Swing screener → grade → LLM Council (new plays)
3. Sector supply chain scan (weekly)
4. X momentum tracker (trending stocks)
5. Volume scanner (unusual activity)
6. Alert system (price triggers)
7. Output: ONE clear action list per day

Usage: python3 vox_autonomous_commander.py [morning|evening]
"""
import os, sys, json, subprocess, datetime

ENV_PATH = os.path.expanduser("~/.hermes/.env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            if '=' in line and not line.startswith('#') and not line.startswith(' '):
                k, v = line.strip().split('=', 1)
                os.environ.setdefault(k, v)

SCRIPT_DIR = os.path.expanduser("~/.hermes/scripts")

def run_cmd(cmd, timeout=180):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, 
            timeout=timeout, cwd=SCRIPT_DIR
        )
        return result.stdout, result.stderr, result.returncode
    except Exception as e:
        return "", str(e), 1

def load_portfolio():
    """Load current portfolio positions."""
    try:
        with open(os.path.join(SCRIPT_DIR, 'etoro_portfolio.json')) as f:
            data = json.load(f)
            positions = data['clientPortfolio']['positions']
            return {p['instrumentID']: {
                'ticker': p['instrumentID'],
                'value': p.get('value', 0),
                'pnl': p.get('profit', 0)
            } for p in positions}
    except:
        return {}

def load_grades():
    """Load latest grades."""
    try:
        with open(os.path.join(SCRIPT_DIR, 'grade_results.json')) as f:
            data = json.load(f)
            grades = data.get('grades', [])
            # Get latest per ticker
            latest = {}
            for g in grades:
                t = g.get('ticker')
                if t and (t not in latest or g.get('timestamp', '') > latest[t].get('timestamp', '')):
                    latest[t] = g
            return latest
    except:
        return {}

def load_screener():
    """Load latest screener results."""
    try:
        with open(os.path.join(SCRIPT_DIR, 'screener_results.json')) as f:
            return json.load(f)
    except:
        return {'results': []}

def generate_morning_brief():
    """Generate morning action brief."""
    print("="*60)
    print("🌅 VOX MORNING BRIEF")
    print(f"   {datetime.datetime.now().strftime('%A, %B %d, %Y')}")
    print("="*60)
    
    # 1. Portfolio status
    portfolio = load_portfolio()
    total_value = sum(p['value'] for p in portfolio.values())
    total_pnl = sum(p['pnl'] for p in portfolio.values())
    
    print(f"\n📊 PORTFOLIO")
    print(f"   Total Value: ${total_value:,.0f}")
    print(f"   Unrealized P&L: ${total_pnl:+,.0f}")
    print(f"   Positions: {len(portfolio)}")
    
    # 2. Today's rotation
    day = datetime.datetime.now().strftime('%A').lower()
    rotation = {
        'monday': ['VOO', 'OSCR', 'CRWD', 'AAPL', 'MSFT', '0700.HK', 'BNB', 'CEG'],
        'tuesday': ['AMD', 'ETH', 'DDOG', 'BIDU', 'SNOW', 'COIN', 'IREN', 'TSM'],
        'wednesday': ['QQQ', 'META', 'WMT', 'OKLO', 'SPOT', 'SMH', 'POET', 'CBRS'],
        'thursday': ['BTC', 'VTI', 'PLTR', 'SHOP', 'XRP', 'DOGE', 'JMIA', 'DASH'],
        'friday': ['APH', 'COST', 'TSLA', 'TRX', 'NVDA', 'CRWV', 'AVGO', 'ADA']
    }
    
    today_tickers = rotation.get(day, [])
    print(f"\n📅 TODAY'S ANALYSIS ({day.title()})")
    print(f"   {', '.join(today_tickers)}")
    
    # 3. Grades for today's tickers
    grades = load_grades()
    print(f"\n📈 CURRENT GRADES")
    for t in today_tickers:
        g = grades.get(t, {})
        grade = g.get('grade', 'N/A')
        rec = g.get('recommendation', 'N/A')
        if isinstance(grade, (int, float)):
            emoji = "🟢" if grade >= 70 else "🟡" if grade >= 55 else "🔴"
            print(f"   {emoji} {t:8s} | Grade: {grade:5.1f} | {rec}")
        else:
            print(f"   ⚪ {t:8s} | Grade: N/A")
    
    # 4. Screener highlights
    screener = load_screener()
    strong_setups = screener.get('strong_setups', 0)
    print(f"\n🔍 SCREENER STATUS")
    print(f"   Last scan: {screener.get('scan_time', 'Unknown')[:10]}")
    print(f"   Strong setups: {strong_setups}")
    
    if screener.get('results'):
        print(f"\n   Top setups:")
        for r in screener['results'][:5]:
            print(f"   • {r['ticker']:6s} Score {r['score']:2d} | RSI {r['rsi']:5.1f} | {r['setup_quality']}")
    
    # 5. Action items
    print(f"\n🎯 TODAY'S ACTIONS")
    
    # Check for urgent items
    urgent = []
    
    # JMIA - broken thesis
    jmia_grade = grades.get('JMIA', {}).get('grade', 0)
    if isinstance(jmia_grade, (int, float)) and jmia_grade < 50:
        urgent.append("🔴 CUT JMIA — Grade below 50, thesis broken")
    
    # Overbought alerts
    for t in ['AMD', 'AAPL', 'CRWD']:
        g = grades.get(t, {})
        rsi = g.get('rsi', 0)
        if isinstance(rsi, (int, float)) and rsi > 70:
            urgent.append(f"🟡 Trim {t} — RSI {rsi:.1f} overbought")
    
    # Check OKLO for swap
    oklo_grade = grades.get('OKLO', {}).get('grade', 0)
    if isinstance(oklo_grade, (int, float)) and oklo_grade < 55:
        urgent.append("🟡 Consider swapping OKLO → CEG (better nuclear play)")
    
    if urgent:
        for item in urgent:
            print(f"   {item}")
    else:
        print("   ✅ No urgent actions — monitor positions")
    
    print(f"\n⏰ Next: Evening scan at 6 PM ET")
    print("="*60)

def generate_evening_brief():
    """Generate evening scan brief with new plays."""
    print("="*60)
    print("🌙 VOX EVENING BRIEF")
    print(f"   {datetime.datetime.now().strftime('%A, %B %d, %Y')}")
    print("="*60)
    
    # Run screener if stale
    screener = load_screener()
    scan_date = screener.get('scan_time', '')[:10]
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    
    if scan_date != today:
        print("\n🔍 Running fresh screener...")
        stdout, stderr, rc = run_cmd("python3 swing_screener.py", timeout=300)
        if rc == 0:
            screener = load_screener()
            print(f"   ✓ Scanned {screener.get('stocks_scanned', 0)} stocks")
        else:
            print(f"   ⚠️ Screener failed: {stderr[:100]}")
    
    # Grade top setups
    print("\n📊 Grading strong setups...")
    top_setups = screener.get('results', [])[:10]
    graded_plays = []
    
    for setup in top_setups:
        ticker = setup['ticker']
        # Skip if already graded today
        grades = load_grades()
        if ticker in grades:
            g = grades[ticker]
            graded_plays.append({
                'ticker': ticker,
                'grade': g.get('grade', 0),
                'recommendation': g.get('recommendation', 'N/A'),
                'score': setup['score']
            })
        else:
            # Grade it
            stdout, stderr, rc = run_cmd(f"python3 grade_system.py {ticker}", timeout=120)
            if rc == 0:
                grades = load_grades()
                g = grades.get(ticker, {})
                graded_plays.append({
                    'ticker': ticker,
                    'grade': g.get('grade', 0),
                    'recommendation': g.get('recommendation', 'N/A'),
                    'score': setup['score']
                })
    
    # Filter for actionable
    strong = [p for p in graded_plays if isinstance(p['grade'], (int, float)) and p['grade'] >= 65]
    strong.sort(key=lambda x: -x['grade'])
    
    print(f"\n🏆 TOP PLAYS (Grade 65+)")
    if strong:
        for p in strong[:5]:
            emoji = "🟢" if p['grade'] >= 70 else "🟡"
            print(f"   {emoji} {p['ticker']:6s} | Grade: {p['grade']:5.1f} | Screener: {p['score']}/10 | {p['recommendation']}")
    else:
        print("   ⏸️ No grade 65+ setups today")
    
    # Council on top 3
    if strong:
        print(f"\n🧠 LLM COUNCIL (Top 3)")
        for p in strong[:3]:
            print(f"   Running council on {p['ticker']}...")
            stdout, stderr, rc = run_cmd(
                f"python3 llm_council_v2.py {p['ticker']} 'Swing setup analysis'",
                timeout=180
            )
            # Extract consensus
            consensus = "UNKNOWN"
            for line in stdout.split('\n'):
                if 'CONSENSUS:' in line:
                    consensus = line.split(':', 1)[1].strip()
            print(f"   → {p['ticker']}: {consensus}")
    
    # Final action list
    print(f"\n🎯 SUGGESTED PLAYS")
    if strong:
        for p in strong[:3]:
            print(f"   • {p['ticker']} — Grade {p['grade']:.0f} — {p['recommendation']}")
    else:
        print("   • No new plays today — market extended, wait for pullback")
    
    print(f"\n⏰ Next: Morning brief at 8 AM ET")
    print("="*60)

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'evening':
        generate_evening_brief()
    else:
        generate_morning_brief()

if __name__ == '__main__':
    main()
