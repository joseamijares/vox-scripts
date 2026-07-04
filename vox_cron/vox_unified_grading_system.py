#!/usr/bin/env python3
"""
VOX UNIFIED GRADING SYSTEM v4.1 — FIXED FOR WATCHLIST STOCKS (OPTIMIZED)

Bug fixed: Previous versions only processed tickers that existed in ALL three
sources (vox_grades, sp500_grades, trade_signals) and limited to top 100.
Watchlist stocks (IONQ, SE, MCO, VEEV) were dropped because they only exist
in vox_grades/watchlist_grades but not sp500 or trade tables.

Changes in v4.1:
- Includes watchlist_grades as a VOX source (often fresher/higher quality)
- Processes ALL tickers from ANY source (no top-N limit)
- VOX grade gets minimum 50% weight (from vox_grades OR watchlist_grades)
- When both vox_grades and watchlist_grades exist, uses the HIGHER/fresher one
- Other sources (sp500, trade, technical) are blended in with remaining weight
- Stocks with only VOX grade get that grade directly (100% weight)
- OPTIMIZED: Single batch SQL for all inserts, no per-ticker subprocess calls

Target: 20% yearly profit
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class VoxUnifiedGradingSystem:
    """Single source of truth for VOX grades."""
    
    def __init__(self):
        self.db_host = 'acela.proxy.rlwy.net'
        self.db_port = '35577'
        self.db_user = 'postgres'
        self.db_name = 'railway'
        self.db_password = os.environ.get('PGPASSWORD') or os.environ.get('DB_PASSWORD') or ''
        self.grades = {}
        self.contradictions = []
        
    def query(self, sql: str) -> List[Tuple]:
        """Execute SQL query and return results."""
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password
        
        result = subprocess.run([
            'psql', '-h', self.db_host, '-p', self.db_port, '-U', self.db_user,
            '-d', self.db_name, '-t', '-c', sql
        ], capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            print(f"SQL Error: {result.stderr}")
            return []
        
        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        return [tuple(l.split('|')) for l in lines]
    
    def query_file(self, sql_path: str) -> str:
        """Execute SQL from file."""
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password
        
        result = subprocess.run([
            'psql', '-h', self.db_host, '-p', self.db_port, '-U', self.db_user,
            '-d', self.db_name, '-t', '-f', sql_path
        ], capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            print(f"SQL Error: {result.stderr}")
            return ""
        return result.stdout
    
    def get_latest_vox_grades(self) -> Dict[str, Dict]:
        """Get latest VOX grades for all tickers."""
        print("Fetching latest VOX grades...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, vox_grade, action, generated_at
            FROM vox_grades 
            WHERE generated_at > NOW() - INTERVAL '7 days'
            ORDER BY ticker, generated_at DESC
        """)
        
        grades = {}
        for row in result:
            if len(row) >= 3:
                ticker = row[0].strip()
                try:
                    grade = int(row[1].strip())
                    action = row[2].strip()
                    grades[ticker] = {'grade': grade, 'action': action}
                except:
                    pass
        
        print(f"  Found {len(grades)} VOX grades")
        return grades
    
    def get_latest_watchlist_grades(self) -> Dict[str, Dict]:
        """Get latest watchlist grades for all tickers."""
        print("Fetching latest watchlist grades...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, graded_at
            FROM watchlist_grades 
            WHERE graded_at > NOW() - INTERVAL '7 days'
            ORDER BY ticker, graded_at DESC
        """)
        
        grades = {}
        for row in result:
            if len(row) >= 8:
                ticker = row[0].strip()
                try:
                    grade = int(row[1].strip())
                    technical = int(row[2].strip()) if row[2].strip().isdigit() else None
                    fundamental = int(row[3].strip()) if row[3].strip().isdigit() else None
                    macro = int(row[4].strip()) if row[4].strip().isdigit() else None
                    sector = int(row[5].strip()) if row[5].strip().isdigit() else None
                    weather = int(row[6].strip()) if row[6].strip().isdigit() else None
                    sentiment = int(row[7].strip()) if row[7].strip().isdigit() else None
                    grades[ticker] = {
                        'grade': grade, 'action': None,
                        'technical': technical, 'fundamental': fundamental,
                        'macro': macro, 'sector': sector,
                        'weather': weather, 'sentiment': sentiment
                    }
                except:
                    pass
        
        print(f"  Found {len(grades)} watchlist grades")
        return grades
    
    def get_latest_sp500_grades(self) -> Dict[str, Dict]:
        """Get latest SP500 grades for all tickers."""
        print("Fetching latest SP500 grades...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, computed_at
            FROM sp500_grades 
            WHERE computed_at > NOW() - INTERVAL '7 days'
            ORDER BY ticker, computed_at DESC
        """)
        
        grades = {}
        for row in result:
            if len(row) >= 6:
                ticker = row[0].strip()
                try:
                    grade = int(row[1].strip())
                    tech = int(row[2].strip())
                    fund = int(row[3].strip())
                    macro = int(row[4].strip())
                    sector = int(row[5].strip())
                    grades[ticker] = {
                        'grade': grade, 'tech': tech, 'fund': fund, 
                        'macro': macro, 'sector': sector
                    }
                except:
                    pass
        
        print(f"  Found {len(grades)} SP500 grades")
        return grades
    
    def get_latest_trade_signals(self) -> Dict[str, Dict]:
        """Get latest trade signals for all tickers."""
        print("Fetching latest trade signals...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, grade, signal_type, composite_score, created_at
            FROM trade_signals 
            WHERE created_at > NOW() - INTERVAL '7 days'
            ORDER BY ticker, created_at DESC
        """)
        
        signals = {}
        for row in result:
            if len(row) >= 3:
                ticker = row[0].strip()
                try:
                    grade = int(row[1].strip())
                    signal_type = row[2].strip()
                    signals[ticker] = {'grade': grade, 'signal': signal_type}
                except:
                    pass
        
        print(f"  Found {len(signals)} trade signals")
        return signals
    
    def get_latest_technical_signals(self) -> Dict[str, Dict]:
        """Get latest technical signals for all tickers."""
        print("Fetching latest technical signals...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, score, alpha_zoo_score, computed_at
            FROM technical_signals 
            ORDER BY ticker, computed_at DESC
        """)
        
        signals = {}
        for row in result:
            if len(row) >= 2:
                ticker = row[0].strip()
                try:
                    score = int(row[1].strip())
                    alpha = int(row[2].strip()) if len(row) > 2 else None
                    signals[ticker] = {'score': score, 'alpha': alpha}
                except:
                    pass
        
        print(f"  Found {len(signals)} technical signals")
        return signals
    
    def get_latest_pattern_alerts(self) -> Dict[str, Dict]:
        """Get latest pattern alerts for all tickers."""
        print("Fetching latest pattern alerts...")
        result = self.query("""
            SELECT DISTINCT ON (ticker) 
                ticker, pattern_type, conviction, detected_at
            FROM pattern_alerts 
            ORDER BY ticker, detected_at DESC
        """)
        
        alerts = {}
        for row in result:
            if len(row) >= 3:
                ticker = row[0].strip()
                try:
                    pattern_type = row[1].strip()
                    conviction = int(row[2].strip())
                    alerts[ticker] = {'pattern': pattern_type, 'conviction': conviction}
                except:
                    pass
        
        print(f"  Found {len(alerts)} pattern alerts")
        return alerts
    
    def select_vox_grade(self, ticker: str, vox: Dict, watchlist: Dict) -> Tuple[Optional[int], Optional[str], str]:
        """Select the best VOX grade from vox_grades and watchlist_grades.
        
        Returns: (grade, action, source_name)
        If both exist, prefer watchlist if it's significantly higher (>= 5 points)
        or if they're close (within 4 points), use the higher one.
        """
        vox_grade = vox.get('grade')
        vox_action = vox.get('action')
        wl_grade = watchlist.get('grade')
        wl_action = watchlist.get('action')
        
        if vox_grade is not None and wl_grade is not None:
            # Both exist - prefer watchlist if it's higher (watchlist is often fresher)
            if wl_grade >= vox_grade:
                return wl_grade, wl_action, 'watchlist'
            else:
                return vox_grade, vox_action, 'vox_grades'
        elif wl_grade is not None:
            return wl_grade, wl_action, 'watchlist'
        elif vox_grade is not None:
            return vox_grade, vox_action, 'vox_grades'
        else:
            return None, None, 'none'
    
    def compute_unified_grade(self, ticker: str, vox: Dict, watchlist: Dict,
                              sp500: Dict, trade: Dict, tech: Dict, pattern: Dict) -> Optional[Dict]:
        """Compute unified grade from ALL available sources.
        
        VOX grade (from vox_grades or watchlist_grades) gets minimum 50% weight.
        Other sources are blended with remaining weight.
        """
        # Select the authoritative VOX grade
        vox_grade, vox_action, vox_source = self.select_vox_grade(ticker, vox, watchlist)
        
        sp500_grade = sp500.get('grade')
        sp500_tech = sp500.get('tech')
        sp500_fund = sp500.get('fund')
        sp500_macro = sp500.get('macro')
        sp500_sector = sp500.get('sector')
        
        trade_grade = trade.get('grade')
        trade_signal = trade.get('signal')
        
        tech_score = tech.get('score')
        tech_alpha = tech.get('alpha')
        
        pattern_type = pattern.get('pattern')
        pattern_conviction = pattern.get('conviction')
        
        # If no VOX grade at all, we can't compute a unified grade
        if vox_grade is None:
            # Fall back to other sources if available
            other_grades = []
            if sp500_grade is not None:
                other_grades.append(sp500_grade)
            if trade_grade is not None:
                other_grades.append(trade_grade)
            if tech_score is not None:
                other_grades.append(tech_score)
            
            if not other_grades:
                return None
            
            # No VOX grade - use average of other sources
            unified_grade = round(sum(other_grades) / len(other_grades))
            vox_grade = None
            vox_action = None
            vox_source = 'none'
        else:
            # We have a VOX grade. Build weighted average with VOX >= 50%.
            # VOX gets 50%, other sources share the remaining 50% equally.
            other_sources = []
            if sp500_grade is not None:
                other_sources.append(sp500_grade)
            if trade_grade is not None:
                other_sources.append(trade_grade)
            if tech_score is not None:
                other_sources.append(tech_score)
            
            if not other_sources:
                # Only VOX grade available - use it 100%
                unified_grade = vox_grade
            else:
                # VOX gets 50%, other sources share 50% equally
                other_avg = sum(other_sources) / len(other_sources)
                unified_grade = round(vox_grade * 0.50 + other_avg * 0.50)
        
        # Determine action based on unified grade AND VOX action
        # If VOX says SELL and unified is below 65, respect VOX
        if vox_action == 'SELL' and unified_grade < 65:
            action = 'SELL'
        elif vox_action == 'SELL' and unified_grade < 70:
            action = 'TRIM'
        elif unified_grade >= 80:
            action = 'STRONG_BUY'
        elif unified_grade >= 65:
            action = 'BUY'
        elif unified_grade >= 50:
            action = 'HOLD'
        elif unified_grade >= 40:
            action = 'TRIM'
        else:
            action = 'SELL'
        
        # Check for contradictions
        contradiction = None
        if vox_grade and sp500_grade and abs(vox_grade - sp500_grade) > 10:
            contradiction = f"VOX {vox_grade} vs SP500 {sp500_grade}"
        if vox_grade and trade_grade and vox_action == 'SELL' and trade_signal == 'BUY':
            contradiction = f"VOX SELL vs Trade BUY {trade_grade}"
        
        return {
            'ticker': ticker,
            'unified_grade': unified_grade,
            'action': action,
            'vox_grade': vox_grade,
            'vox_action': vox_action,
            'vox_source': vox_source,
            'sp500_grade': sp500_grade,
            'sp500_tech': sp500_tech,
            'sp500_fund': sp500_fund,
            'sp500_macro': sp500_macro,
            'sp500_sector': sp500_sector,
            'trade_grade': trade_grade,
            'trade_signal': trade_signal,
            'tech_score': tech_score,
            'tech_alpha': tech_alpha,
            'pattern_type': pattern_type,
            'pattern_conviction': pattern_conviction,
            'contradiction': contradiction,
            'computed_at': datetime.now().isoformat()
        }
    
    def compute_all_grades(self) -> Dict:
        """Compute unified grades for ALL tickers from ANY source."""
        print("Computing unified grades for ALL tickers from ANY source...")
        
        # Fetch all data sources
        vox_grades = self.get_latest_vox_grades()
        watchlist_grades = self.get_latest_watchlist_grades()
        sp500_grades = self.get_latest_sp500_grades()
        trade_signals = self.get_latest_trade_signals()
        technical_signals = self.get_latest_technical_signals()
        pattern_alerts = self.get_latest_pattern_alerts()
        
        # Get ALL unique tickers from ALL sources (not just VOX)
        all_tickers = set(vox_grades.keys()) | set(watchlist_grades.keys()) | set(sp500_grades.keys()) | set(trade_signals.keys()) | set(technical_signals.keys()) | set(pattern_alerts.keys())
        
        print(f"Processing ALL {len(all_tickers)} tickers...")
        
        unified_grades = {}
        contradictions = []
        missing_vox = []
        
        for i, ticker in enumerate(sorted(all_tickers)):
            result = self.compute_unified_grade(
                ticker,
                vox_grades.get(ticker, {}),
                watchlist_grades.get(ticker, {}),
                sp500_grades.get(ticker, {}),
                trade_signals.get(ticker, {}),
                technical_signals.get(ticker, {}),
                pattern_alerts.get(ticker, {})
            )
            
            if result:
                unified_grades[ticker] = result
                
                if result['vox_source'] == 'none':
                    missing_vox.append(ticker)
                
                if result['contradiction']:
                    contradictions.append({
                        'ticker': ticker,
                        'contradiction': result['contradiction'],
                        'unified_grade': result['unified_grade'],
                        'action': result['action']
                    })
            
            if (i + 1) % 100 == 0:
                print(f"  Processed {i + 1}/{len(all_tickers)}...")
        
        print(f"Done. {len(unified_grades)} grades computed.")
        print(f"  {len(missing_vox)} tickers without VOX grade (using other sources only)")
        print(f"  {len(contradictions)} contradictions found.")
        
        return {
            'unified_grades': unified_grades,
            'contradictions': contradictions,
            'missing_vox': missing_vox,
            'total_tickers': len(all_tickers),
            'computed_at': datetime.now().isoformat()
        }
    
    def save_to_database(self, data: Dict):
        """Save unified grades to database using batch SQL file."""
        print("Saving unified grades to database...")
        
        # Create table if not exists (add vox_source column)
        self.query("""
            CREATE TABLE IF NOT EXISTS unified_grades (
                id SERIAL PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                unified_grade INTEGER NOT NULL,
                action VARCHAR(20) NOT NULL,
                vox_grade INTEGER,
                vox_source VARCHAR(20),
                sp500_grade INTEGER,
                trade_grade INTEGER,
                tech_score INTEGER,
                contradiction TEXT,
                computed_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(ticker)
            )
        """)
        
        # Also add vox_source column if table exists but column doesn't
        self.query("""
            ALTER TABLE unified_grades 
            ADD COLUMN IF NOT EXISTS vox_source VARCHAR(20)
        """)
        
        # Clear old grades
        self.query("TRUNCATE TABLE unified_grades")
        
        # Build batch insert SQL
        values_lines = []
        for ticker, grade_data in data['unified_grades'].items():
            vg = grade_data['vox_grade'] if grade_data['vox_grade'] is not None else 'NULL'
            vs = f"'{grade_data['vox_source']}'" if grade_data['vox_source'] else 'NULL'
            sg = grade_data['sp500_grade'] if grade_data['sp500_grade'] is not None else 'NULL'
            tg = grade_data['trade_grade'] if grade_data['trade_grade'] is not None else 'NULL'
            ts = grade_data['tech_score'] if grade_data['tech_score'] is not None else 'NULL'
            ct = f"'{grade_data['contradiction'].replace(chr(39), chr(39)+chr(39))}'" if grade_data['contradiction'] else 'NULL'
            
            values_lines.append(
                f"('{ticker}', {grade_data['unified_grade']}, '{grade_data['action']}', {vg}, {vs}, {sg}, {tg}, {ts}, {ct}, NOW())"
            )
        
        # Write to temp file and execute in batches of 100
        batch_size = 100
        total_inserted = 0
        for batch_start in range(0, len(values_lines), batch_size):
            batch = values_lines[batch_start:batch_start + batch_size]
            sql = "INSERT INTO unified_grades (ticker, unified_grade, action, vox_grade, vox_source, sp500_grade, trade_grade, tech_score, contradiction, computed_at) VALUES\n"
            sql += ",\n".join(batch)
            sql += ";"
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
                f.write(sql)
                tmp_path = f.name
            
            self.query_file(tmp_path)
            os.unlink(tmp_path)
            total_inserted += len(batch)
            print(f"  Inserted batch {total_inserted}/{len(values_lines)}...")
        
        print(f"Saved {total_inserted} grades to database.")
    
    def save_to_json(self, data: Dict):
        """Save unified grades to JSON file."""
        output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_unified_grades_{datetime.now().strftime('%Y%m%d')}.json"
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        print(f"Saved to JSON: {output_file}")
        return output_file
    
    def run(self):
        """Run the unified grading system."""
        print("="*70)
        print("VOX UNIFIED GRADING SYSTEM v4.1")
        print("Watchlist bug fixed — ALL tickers from ANY source")
        print("VOX grade minimum 50% weight")
        print("="*70)
        print()
        
        # Compute all grades
        data = self.compute_all_grades()
        
        # Save to database
        self.save_to_database(data)
        
        # Save to JSON
        json_file = self.save_to_json(data)
        
        # Print watchlist stocks specifically
        print("\n" + "="*70)
        print("WATCHLIST STOCKS CHECK")
        print("="*70)
        for ticker in ['IONQ', 'SE', 'MCO', 'VEEV']:
            if ticker in data['unified_grades']:
                g = data['unified_grades'][ticker]
                print(f"{ticker:6} | Unified: {g['unified_grade']:3} | VOX: {g['vox_grade'] or 'N/A'} ({g['vox_source']}) | SP500: {g['sp500_grade'] or 'N/A'} | Trade: {g['trade_grade'] or 'N/A'} | Action: {g['action']}")
            else:
                print(f"{ticker:6} | MISSING from unified grades!")
        
        # Print top 20
        print("\n" + "="*70)
        print("TOP 20 UNIFIED GRADES")
        print("="*70)
        
        sorted_grades = sorted(
            data['unified_grades'].items(), 
            key=lambda x: x[1]['unified_grade'], 
            reverse=True
        )[:20]
        
        for ticker, grade_data in sorted_grades:
            print(f"{ticker:6} | {grade_data['unified_grade']:3} | {grade_data['action']:12} | VOX:{grade_data['vox_grade'] or 'N/A'}({grade_data['vox_source'][:3]}) | SP500:{grade_data['sp500_grade'] or 'N/A'} | Trade:{grade_data['trade_grade'] or 'N/A'} | Tech:{grade_data['tech_score'] or 'N/A'}")
        
        # Print contradictions
        if data['contradictions']:
            print("\n" + "="*70)
            print(f"CONTRADICTIONS ({len(data['contradictions'])})")
            print("="*70)
            
            for c in data['contradictions'][:10]:
                print(f"{c['ticker']:6} | {c['unified_grade']:3} | {c['action']:12} | {c['contradiction']}")
        
        # Print missing VOX
        if data['missing_vox']:
            print("\n" + "="*70)
            print(f"NO VOX GRADE ({len(data['missing_vox'])} tickers using other sources only)")
            print("="*70)
            print(f"  {', '.join(data['missing_vox'][:20])}")
            if len(data['missing_vox']) > 20:
                print(f"  ... and {len(data['missing_vox']) - 20} more")
        
        print("\n" + "="*70)
        print("UNIFIED GRADING COMPLETE")
        print(f"Total tickers: {len(data['unified_grades'])}")
        print("="*70)
        
        return data

if __name__ == '__main__':
    system = VoxUnifiedGradingSystem()
    result = system.run()
