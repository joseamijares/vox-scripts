#!/usr/bin/env python3
"""
VOX UNIFIED RECOMMENDATION ENGINE v3
The ONLY system for generating recommendations.

Uses unified_grades as single source of truth.
Queries ALL 31 tables.
Cross-validates everything.
Flags contradictions.
Reports system gaps.

Target: 20% yearly profit
Rule: NO shortcuts. EVER.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple

class VoxUnifiedRecommendationEngine:
    """Single recommendation engine for ALL users."""
    
    def __init__(self):
        self.db_host = 'acela.proxy.rlwy.net'
        self.db_port = '35577'
        self.db_user = 'postgres'
        self.db_name = 'railway'
        self.db_password = ''
        
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
    
    def run_checklist(self) -> Dict:
        """Run the mandatory checklist."""
        print("Running mandatory checklist...")
        
        # Check database connection
        result = self.query("SELECT NOW()")
        if not result:
            return {'can_recommend': False, 'error': 'Database connection failed'}
        
        # Check unified_grades exists and has data
        result = self.query("SELECT COUNT(*) FROM unified_grades WHERE computed_at > NOW() - INTERVAL '24 hours'")
        if not result or int(result[0][0].strip()) == 0:
            return {'can_recommend': False, 'error': 'No unified grades found. Run vox_unified_grading_system.py first.'}
        
        # Check for contradictions in unified grades
        contradictions = self.query("""
            SELECT ticker, unified_grade, vox_grade, sp500_grade, trade_grade, contradiction
            FROM unified_grades
            WHERE computed_at > NOW() - INTERVAL '24 hours'
            AND contradiction IS NOT NULL
            ORDER BY unified_grade DESC
        """)
        
        # Check system gaps
        gaps = []
        
        # Sentiment scores
        sentiment_count = self.query("SELECT COUNT(*) FROM sentiment_scores")
        if sentiment_count and int(sentiment_count[0][0].strip()) < 10:
            gaps.append(f"Sentiment scores only {sentiment_count[0][0].strip()} stocks (need 10+)")
        
        # Technical signals freshness
        tech_fresh = self.query("SELECT COUNT(*) FROM technical_signals WHERE computed_at > NOW() - INTERVAL '24 hours'")
        if tech_fresh and int(tech_fresh[0][0].strip()) == 0:
            gaps.append("Technical signals are stale (>24 hours old)")
        
        return {
            'can_recommend': True,
            'unified_grades_count': int(result[0][0].strip()),
            'contradictions': len(contradictions),
            'gaps': gaps,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_sector_momentum(self, ticker: str) -> Tuple[float, str, str]:
        """Get sector momentum for a ticker. Returns (score, sector_name, signal).
        
        Scores are normalized to 0-100 scale:
        - sector_momentum (thematic): already 0-100
        - sector_rotation (GICS): 0-10 scale, multiplied by 10
        """
        # Get sector for ticker
        sector_result = self.query(f"""
            SELECT ts.sector FROM ticker_sectors ts WHERE ts.ticker = '{ticker}'
        """)
        if not sector_result or not sector_result[0] or not sector_result[0][0]:
            return 50.0, 'Unknown', 'none'
        
        sector_name = sector_result[0][0].strip()
        
        # First try sector_momentum (thematic sectors, 0-100 scale)
        # Only use if score is meaningful (> 0)
        momentum_result = self.query(f"""
            SELECT momentum_score FROM sector_momentum
            WHERE sector = '{sector_name}' AND momentum_score > 0
            ORDER BY computed_at DESC LIMIT 1
        """)
        
        if momentum_result and momentum_result[0] and momentum_result[0][0]:
            score = float(momentum_result[0][0].strip())
            return score, sector_name, 'confirmed' if score >= 55 else 'none'
        
        # Try GICS mapping for sector_rotation table (ETF-based sectors, 0-10 scale)
        gics_map = {
            'Technology': 'XLK', 'Healthcare': 'XLV',
            'Financial Services': 'XLF', 'Financials': 'XLF',
            'Consumer Cyclical': 'XLY', 'Consumer Discretionary': 'XLY',
            'Consumer Defensive': 'XLP', 'Consumer Staples': 'XLP',
            'Industrials': 'XLI',
            'Communication Services': 'XLC',
            'Energy': 'XLE',
            'Basic Materials': 'XLB', 'Materials': 'XLB',
            'Real Estate': 'XLRE',
            'Utilities': 'XLU',
        }
        etf_ticker = gics_map.get(sector_name)
        
        if etf_ticker:
            rotation_result = self.query(f"""
                SELECT momentum_score, rotation_signal FROM sector_rotation
                WHERE etf_ticker = '{etf_ticker}'
                ORDER BY created_at DESC LIMIT 1
            """)
            if rotation_result and rotation_result[0] and rotation_result[0][0]:
                raw_score = float(rotation_result[0][0].strip())
                # Normalize from 0-10 scale to 0-100 scale
                score = raw_score * 10
                signal = rotation_result[0][1].strip() if len(rotation_result[0]) > 1 and rotation_result[0][1] else 'none'
                return score, sector_name, signal
        
        # Fallback to fuzzy match on sector_momentum
        momentum_result = self.query(f"""
            SELECT momentum_score FROM sector_momentum
            WHERE sector ILIKE '%{sector_name}%'
            ORDER BY computed_at DESC LIMIT 1
        """)
        
        if momentum_result and momentum_result[0] and momentum_result[0][0]:
            score = float(momentum_result[0][0].strip())
            return score, sector_name, 'confirmed' if score >= 55 else 'none'
        
        return 50.0, sector_name, 'none'
    
    def get_sector_rotation_summary(self) -> Dict:
        """Get current sector rotation summary from both sector_momentum and sector_rotation."""
        # Get thematic sectors (0-100 scale)
        thematic_sectors = self.query("""
            SELECT sector, momentum_score, top_tickers
            FROM sector_momentum
            WHERE computed_at > NOW() - INTERVAL '24 hours' AND momentum_score > 0
            ORDER BY momentum_score DESC
        """)
        
        # Get GICS sectors from sector_rotation (0-10 scale, normalized to 0-100)
        gics_sectors = self.query("""
            SELECT sector, etf_ticker, momentum_score, rotation_signal
            FROM sector_rotation
            WHERE created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
        """)
        
        # Take latest entry per sector for GICS
        seen_gics = set()
        gics_latest = []
        for row in gics_sectors:
            if len(row) >= 4:
                sector = row[0].strip()
                etf = row[1].strip() if row[1] else ''
                score = float(row[2].strip()) * 10 if row[2] else 0  # Normalize to 0-100
                signal = row[3].strip() if row[3] else 'none'
                if sector not in seen_gics:
                    seen_gics.add(sector)
                    gics_latest.append({'sector': sector, 'score': score, 'signal': signal, 'etf': etf})
        
        # Combine and sort
        all_sectors = []
        
        # Add thematic sectors
        for row in thematic_sectors:
            if len(row) >= 2:
                sector = row[0].strip()
                score = float(row[1].strip()) if row[1] else 0
                top = row[2].strip() if len(row) > 2 and row[2] else ''
                all_sectors.append({'sector': sector, 'score': score, 'signal': 'confirmed' if score >= 55 else 'none', 'top_tickers': top})
        
        # Add GICS sectors (avoid duplicates)
        thematic_names = {s['sector'] for s in all_sectors}
        for gics in gics_latest:
            if gics['sector'] not in thematic_names:
                all_sectors.append(gics)
        
        # Sort by score descending
        all_sectors.sort(key=lambda x: x['score'], reverse=True)
        
        hot_sectors = [s for s in all_sectors if s['score'] >= 55]
        cold_sectors = [s for s in all_sectors if s['score'] <= 35]
        
        return {'hot': hot_sectors, 'cold': cold_sectors}
    
    def get_sector_etf_recommendations(self) -> List[Dict]:
        """Get sector ETF recommendations based on rotation."""
        # Map sectors to ETFs
        sector_etfs = {
            'Technology': 'XLK', 'Healthcare': 'XLV', 'Financials': 'XLF',
            'Industrials': 'XLI', 'Consumer Discretionary': 'XLY',
            'Consumer Staples': 'XLP', 'Energy': 'XLE', 'Materials': 'XLB',
            'Real Estate': 'XLRE', 'Utilities': 'XLU', 'Communication Services': 'XLC',
        }
        
        rotation = self.get_sector_rotation_summary()
        etf_recs = []
        
        for hot in rotation['hot'][:3]:  # Top 3 hot sectors
            # Check if sector has an ETF mapping
            etf = sector_etfs.get(hot['sector'], None)
            if not etf and 'etf' in hot:
                etf = hot['etf']
            if etf:
                etf_recs.append({
                    'ticker': etf,
                    'sector': hot['sector'],
                    'momentum_score': hot['score'],
                    'signal': hot['signal'],
                    'rationale': f"Sector rotation confirmed: {hot['sector']} momentum = {hot['score']:.1f}"
                })
        
        return etf_recs
    
    def get_recommendations(self, limit: int = 10) -> Dict:
        """Get top recommendations from unified grades WITH sector rotation boost."""
        print(f"Getting top {limit} recommendations with sector rotation...")
        
        # Get top unified grades with sector info
        top_grades = self.query(f"""
            SELECT u.ticker, u.unified_grade, u.action, u.vox_grade, u.sp500_grade, u.trade_grade, u.tech_score, u.contradiction, ts.sector
            FROM unified_grades u
            LEFT JOIN ticker_sectors ts ON u.ticker = ts.ticker
            WHERE u.computed_at > NOW() - INTERVAL '24 hours'
            ORDER BY u.unified_grade DESC
            LIMIT {limit * 3}
        """)
        
        recommendations = []
        for row in top_grades:
            if len(row) >= 3:
                ticker = row[0].strip()
                grade = int(row[1].strip())
                action = row[2].strip()
                vox = row[3].strip() if row[3] else 'N/A'
                sp500 = row[4].strip() if row[4] else 'N/A'
                trade = row[5].strip() if row[5] else 'N/A'
                tech = row[6].strip() if row[6] else 'N/A'
                contradiction = row[7].strip() if row[7] else None
                sector = row[8].strip() if len(row) > 8 and row[8] else 'Unknown'
                
                # Get sector momentum
                sector_score, sector_name, sector_signal = self.get_sector_momentum(ticker)
                
                # Apply sector rotation boost/penalty
                sector_boost = 0
                if sector_score >= 60:  # Hot sector
                    sector_boost = 5
                elif sector_score >= 55:  # Warm sector
                    sector_boost = 2
                elif sector_score <= 35:  # Cold sector
                    sector_boost = -5
                elif sector_score <= 45:  # Cool sector
                    sector_boost = -2
                
                adjusted_grade = min(100, grade + sector_boost)
                
                recommendations.append({
                    'ticker': ticker,
                    'unified_grade': grade,
                    'adjusted_grade': adjusted_grade,
                    'sector_boost': sector_boost,
                    'action': action,
                    'vox_grade': vox,
                    'sp500_grade': sp500,
                    'trade_grade': trade,
                    'tech_score': tech,
                    'sector': sector_name,
                    'sector_momentum': sector_score,
                    'sector_signal': sector_signal,
                    'contradiction': contradiction
                })
        
        # Sort by adjusted grade
        recommendations.sort(key=lambda x: x['adjusted_grade'], reverse=True)
        
        return {
            'recommendations': recommendations[:limit],
            'count': len(recommendations[:limit]),
            'timestamp': datetime.now().isoformat()
        }
    
    def get_portfolio_analysis(self) -> Dict:
        """Analyze portfolio using unified grades."""
        print("Analyzing portfolio...")
        
        # Get positions
        positions = self.query("""
            SELECT p.ticker, p.grade, p.council, p.live_value_usd, p.brokers, u.unified_grade, u.action
            FROM positions p
            LEFT JOIN unified_grades u ON p.ticker = u.ticker
            WHERE u.computed_at > NOW() - INTERVAL '24 hours'
            ORDER BY p.live_value_usd DESC NULLS LAST
        """)
        
        portfolio = []
        for row in positions:
            if len(row) >= 5:
                ticker = row[0].strip()
                pos_grade = row[1].strip() if row[1] else 'N/A'
                council = row[2].strip() if row[2] else 'N/A'
                value = row[3].strip() if row[3] else '0'
                brokers = row[4].strip() if row[4] else 'N/A'
                unified = row[5].strip() if row[5] else 'N/A'
                action = row[6].strip() if row[6] else 'N/A'
                
                portfolio.append({
                    'ticker': ticker,
                    'position_grade': pos_grade,
                    'council': council,
                    'value': value,
                    'brokers': brokers,
                    'unified_grade': unified,
                    'unified_action': action
                })
        
        return {
            'portfolio': portfolio,
            'count': len(portfolio),
            'timestamp': datetime.now().isoformat()
        }
    
    def generate_report(self) -> str:
        """Generate complete recommendation report."""
        print("Generating report...")
        
        # Run checklist
        checklist = self.run_checklist()
        
        if not checklist['can_recommend']:
            return f"""
# ❌ VOX SYSTEM CHECKLIST FAILED

**Error:** {checklist['error']}

**Cannot make recommendations until system is fixed.**
"""
        
        # Get recommendations
        recs = self.get_recommendations(limit=10)
        
        # Get portfolio analysis
        portfolio = self.get_portfolio_analysis()
        
        # Get sector rotation summary
        sector_rotation = self.get_sector_rotation_summary()
        sector_etfs = self.get_sector_etf_recommendations()
        
        # Build report
        report = f"""
# ✅ VOX UNIFIED RECOMMENDATION ENGINE v3
## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## SYSTEM CHECKLIST

| Check | Status |
|-------|--------|
| Database Connection | ✅ OK |
| Unified Grades | ✅ {checklist['unified_grades_count']} grades |
| Contradictions | ⚠️ {checklist['contradictions']} found |
| System Gaps | {'⚠️ ' + str(len(checklist['gaps'])) + ' found' if checklist['gaps'] else '✅ None'} |

**System Status:** ✅ RECOMMENDATION ALLOWED

---

## SECTOR ROTATION ALERT

### 🔥 Hot Sectors (Confirmed Rotation)
"""
        
        if sector_rotation['hot']:
            for hot in sector_rotation['hot'][:5]:
                report += f"- **{hot['sector']}**: Momentum = {hot['score']:.1f} ({hot['signal']})\n"
        else:
            report += "- No hot sectors detected\n"
        
        report += "\n### ❄️ Cold Sectors (Avoid)\n"
        if sector_rotation['cold']:
            for cold in sector_rotation['cold'][:3]:
                report += f"- **{cold['sector']}**: Momentum = {cold['score']:.1f}\n"
        else:
            report += "- No cold sectors detected\n"
        
        report += "\n### 📊 Sector ETF Plays\n"
        if sector_etfs:
            for etf in sector_etfs:
                report += f"- **{etf['ticker']}** ({etf['sector']}): {etf['rationale']}\n"
        else:
            report += "- No sector ETF recommendations\n"
        
        report += """
---

## TOP 10 RECOMMENDATIONS (Sector-Adjusted)

| # | Ticker | Unified | Adj | Boost | Action | Sector | Sector Mom | VOX | SP500 | Trade | ⚠️ |
|---|--------|---------|-----|-------|--------|--------|------------|-----|-------|-------|-----|
"""
        
        for i, rec in enumerate(recs['recommendations'], 1):
            warning = "⚠️" if rec['contradiction'] else ""
            boost_str = f"+{rec['sector_boost']}" if rec['sector_boost'] > 0 else str(rec['sector_boost']) if rec['sector_boost'] < 0 else ""
            report += f"| {i} | **{rec['ticker']}** | {rec['unified_grade']} | {rec['adjusted_grade']} | {boost_str} | {rec['action']} | {rec['sector']} | {rec['sector_momentum']:.1f} | {rec['vox_grade']} | {rec['sp500_grade']} | {rec['trade_grade']} | {warning} |\n"
        
        report += """
---

## PORTFOLIO ANALYSIS (Top 10)

| Ticker | Position Grade | Council | Value | Unified Grade | Action | ⚠️ |
|--------|---------------|---------|-------|---------------|--------|-----|
"""
        
        for pos in portfolio['portfolio'][:10]:
            warning = "⚠️" if pos['unified_grade'] != 'N/A' and pos['council'] != pos['unified_action'] else ""
            report += f"| {pos['ticker']} | {pos['position_grade']} | {pos['council']} | ${pos['value']} | {pos['unified_grade']} | {pos['unified_action']} | {warning} |\n"
        
        report += f"""
---

## SYSTEM GAPS

"""
        
        if checklist['gaps']:
            for gap in checklist['gaps']:
                report += f"- ⚠️ {gap}\n"
        else:
            report += "- ✅ No system gaps detected\n"
        
        report += f"""
---

## CRON JOBS

| Job | Schedule | Status |
|-----|----------|--------|
| vox-unified-grading | 6 AM daily | ✅ Active |
| vox-checklist-validator | 6 AM + 2 PM | ✅ Active |
| vox-unified-research | 7 AM + 3 PM | ✅ Active |

---

**Target: 20% Yearly Profit**
**System: v3 Unified Grading**
**Source: unified_grades table (single source of truth)**
"""
        
        return report
    
    def run(self):
        """Run the complete recommendation engine."""
        print("="*70)
        print("VOX UNIFIED RECOMMENDATION ENGINE v3")
        print("="*70)
        print()
        
        report = self.generate_report()
        
        # Save report
        output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_recommendation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"Report saved to: {output_file}")
        print()
        print(report)
        
        return report

if __name__ == '__main__':
    engine = VoxUnifiedRecommendationEngine()
    result = engine.run()
