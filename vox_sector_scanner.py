#!/usr/bin/env python3
"""
VOX Sector Supply Chain Scanner
Grades all companies in hot industry supply chains.
Finds the best risk/reward plays across the value chain.

Usage: python3 vox_sector_scanner.py [sector]
  sector: AI_DataCenter, Quantum_Computing, Space, EV_Autonomous, 
          Biotech_WeightLoss, Cybersecurity, Fintech, India_Emerging
  If omitted, scans all sectors.
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

def load_supply_chain():
    with open(os.path.join(SCRIPT_DIR, 'vox_supply_chain.json')) as f:
        return json.load(f)

def run_grade(ticker):
    """Run grade_system.py and return parsed result."""
    try:
        result = subprocess.run(
            ['python3', 'grade_system.py', ticker],
            capture_output=True, text=True, timeout=120, cwd=SCRIPT_DIR
        )
        output = result.stdout
        grade = None
        recommendation = None
        technical = None
        fundamental = None
        risk_reward = None
        
        for line in output.split('\n'):
            if 'TOTAL GRADE' in line:
                try:
                    grade = float(line.split('|')[1].strip().split('/')[0])
                except:
                    pass
            if 'Recommendation:' in line:
                recommendation = line.split(':', 1)[1].strip()
            if 'Technical' in line and '|' in line:
                try:
                    technical = float(line.split('|')[1].strip().split('/')[0])
                except:
                    pass
            if 'Fundamental' in line and '|' in line:
                try:
                    fundamental = float(line.split('|')[1].strip().split('/')[0])
                except:
                    pass
            if 'Risk/Reward' in line and '|' in line:
                try:
                    risk_reward = float(line.split('|')[1].strip().split('/')[0])
                except:
                    pass
                    
        return {
            'grade': grade,
            'recommendation': recommendation,
            'technical': technical,
            'fundamental': fundamental,
            'risk_reward': risk_reward,
            'raw': output[-1000:]
        }
    except Exception as e:
        return {'grade': None, 'recommendation': f'ERROR: {e}', 'technical': None, 'fundamental': None, 'risk_reward': None, 'raw': ''}

def scan_sector(sector_name, sector_data):
    """Scan all tickers in a sector's supply chain."""
    print(f"\n{'='*60}")
    print(f"🔍 SCANNING: {sector_name}")
    print(f"   {sector_data['description']}")
    print(f"{'='*60}\n")
    
    results = []
    for layer_name, tickers in sector_data['layers'].items():
        print(f"\n📦 {layer_name}")
        print("-" * 40)
        for ticker in tickers:
            data = run_grade(ticker)
            data['ticker'] = ticker
            data['layer'] = layer_name
            data['sector'] = sector_name
            results.append(data)
            
            if data['grade']:
                emoji = "🟢" if data['grade'] >= 70 else "🟡" if data['grade'] >= 55 else "🔴"
                print(f"  {emoji} {ticker:6s} | Grade: {data['grade']:5.1f} | {data['recommendation']}")
            else:
                print(f"  ⚪ {ticker:6s} | Grade: N/A | {data['recommendation']}")
    
    return results

def rank_results(all_results):
    """Rank all results by grade, then by risk/reward."""
    valid = [r for r in all_results if r['grade'] is not None]
    valid.sort(key=lambda x: (-x['grade'], -x.get('risk_reward', 0) if x.get('risk_reward') else 0))
    return valid

def main():
    data = load_supply_chain()
    target_sector = sys.argv[1] if len(sys.argv) > 1 else None
    
    print("="*60)
    print("🎯 VOX SECTOR SUPPLY CHAIN SCANNER")
    print(f"   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    all_results = []
    
    if target_sector:
        if target_sector not in data['sectors']:
            print(f"Unknown sector: {target_sector}")
            print(f"Available: {', '.join(data['sectors'].keys())}")
            sys.exit(1)
        results = scan_sector(target_sector, data['sectors'][target_sector])
        all_results.extend(results)
    else:
        for sector_name, sector_data in data['sectors'].items():
            results = scan_sector(sector_name, sector_data)
            all_results.extend(results)
    
    # Rank and output
    ranked = rank_results(all_results)
    
    print(f"\n\n{'='*60}")
    print("🏆 TOP PLAYS ACROSS ALL SECTORS")
    print(f"{'='*60}\n")
    
    a_plus = [r for r in ranked if r['grade'] >= 80]
    strong = [r for r in ranked if 65 <= r['grade'] < 80]
    decent = [r for r in ranked if 55 <= r['grade'] < 65]
    avoid = [r for r in ranked if r['grade'] < 55]
    
    if a_plus:
        print("⚡ A+ SETUPS (Grade 80+):")
        for r in a_plus[:10]:
            print(f"  {r['ticker']:6s} | {r['grade']:5.1f} | {r['layer']:20s} | {r['sector']}")
        print()
    
    if strong:
        print("🟢 STRONG (Grade 65-79):")
        for r in strong[:15]:
            print(f"  {r['ticker']:6s} | {r['grade']:5.1f} | {r['layer']:20s} | {r['sector']}")
        print()
    
    if decent:
        print("🟡 DECENT (Grade 55-64):")
        for r in decent[:10]:
            print(f"  {r['ticker']:6s} | {r['grade']:5.1f} | {r['layer']:20s} | {r['sector']}")
        print()
    
    # Save results
    output = {
        'timestamp': datetime.datetime.now().isoformat(),
        'all_results': ranked,
        'a_plus': a_plus,
        'strong': strong,
        'decent': decent,
        'avoid': avoid,
        'summary': {
            'total_scanned': len(all_results),
            'graded': len(ranked),
            'a_plus': len(a_plus),
            'strong': len(strong),
            'decent': len(decent),
            'avoid': len(avoid)
        }
    }
    
    output_file = os.path.join(SCRIPT_DIR, 'vox_sector_scan_results.json')
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"💾 Saved to: {output_file}")
    
    # Telegram summary
    print(f"\n\n{'='*60}")
    print("📱 TELEGRAM REPORT")
    print(f"{'='*60}\n")
    print(f"🎯 VOX Sector Scan — {datetime.datetime.now().strftime('%b %d')}")
    print(f"Scanned: {len(all_results)} | A+: {len(a_plus)} | Strong: {len(strong)} | Decent: {len(decent)}")
    print()
    if a_plus:
        print("⚡ A+ PLAYS:")
        for r in a_plus[:5]:
            print(f"  • {r['ticker']} ({r['sector']}) — {r['grade']:.0f}")
    elif strong:
        print("🟢 BEST PLAYS:")
        for r in strong[:5]:
            print(f"  • {r['ticker']} ({r['sector']}) — {r['grade']:.0f}")
    else:
        print("⏸️ No strong setups found today.")

if __name__ == '__main__':
    main()
