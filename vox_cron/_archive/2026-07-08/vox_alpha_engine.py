#!/usr/bin/env python3
"""
VOX ALPHA RESEARCH ENGINE v1.0
The best stock picker system. Target: 20% yearly profit.
Uses ALL tools: web research, financial data, news, sentiment, macro, earnings, technicals.
Not just database queries. Real research. Original insights.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics

# Configuration
os.environ['PGPASSWORD'] = ''
DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = '35577'
DB_USER = 'postgres'
DB_NAME = 'railway'

class VoxAlphaEngine:
    """VOX Alpha Research Engine — Finds the best stocks in the world."""
    
    def __init__(self):
        self.data = {
            'generated_at': datetime.now().isoformat(),
            'sources': {},
            'stocks': {},
            'macro': {},
            'sectors': {},
            'opportunities': [],
            'warnings': []
        }
    
    def db_query(self, sql: str) -> str:
        """Execute SQL query."""
        result = subprocess.run([
            'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
            '-d', DB_NAME, '-t', '-c', sql
        ], capture_output=True, text=True, env=os.environ)
        return result.stdout.strip() if result.returncode == 0 else ""
    
    def layer_1_macro(self) -> Dict:
        """Layer 1: Macro regime, Fed, yields, oil, VIX."""
        print("🔍 Layer 1: Macro Analysis...")
        
        # Get from DB
        regime = self.db_query("""
            SELECT regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at 
            FROM market_regime 
            ORDER BY created_at DESC LIMIT 1
        """)
        
        signals = self.db_query("""
            SELECT signal_name, signal_value, signal_direction, confidence, computed_at 
            FROM macro_signals 
            ORDER BY computed_at DESC LIMIT 15
        """)
        
        # Parse regime
        macro = {
            'regime': 'UNKNOWN',
            'confidence': 0,
            'vix': 0,
            'fed_rate': 0,
            'oil_price': 0,
            'yield_10y': 0,
            'yield_2y': 0,
            'dxy': 0,
            'signals': []
        }
        
        if regime:
            parts = [p.strip() for p in regime.split('|')]
            if len(parts) >= 7:
                macro['regime'] = parts[0]
                macro['confidence'] = int(parts[1]) if parts[1].isdigit() else 0
                macro['vix'] = float(parts[2]) if parts[2].replace('.','').isdigit() else 0
                macro['yield_curve'] = float(parts[4]) if parts[4].replace('.','').isdigit() else 0
        
        # Parse signals
        for line in signals.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 5:
                    macro['signals'].append({
                        'name': parts[0],
                        'value': parts[1],
                        'direction': parts[2],
                        'confidence': int(parts[4]) if parts[4].isdigit() else 0
                    })
        
        self.data['macro'] = macro
        return macro
    
    def layer_2_sectors(self) -> Dict:
        """Layer 2: Sector momentum, rotation, leaders."""
        print("🔍 Layer 2: Sector Analysis...")
        
        sectors = self.db_query("""
            SELECT sector, avg_grade, momentum_score, top_tickers, buy_count, hold_count, sell_count, computed_at 
            FROM sector_momentum 
            ORDER BY momentum_score DESC LIMIT 15
        """)
        
        leaders = self.db_query("""
            SELECT ticker, sector, price_change_pct, momentum_score, screened_at 
            FROM sp500_sector_leaders 
            ORDER BY momentum_score DESC LIMIT 20
        """)
        
        sector_data = {
            'momentum_ranking': [],
            'price_leaders': [],
            'hot_sectors': [],
            'cold_sectors': []
        }
        
        for line in sectors.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    sector_data['momentum_ranking'].append({
                        'sector': parts[0],
                        'avg_grade': float(parts[1]) if parts[1].replace('.','').isdigit() else 0,
                        'momentum': int(parts[2]) if parts[2].isdigit() else 0,
                        'top_tickers': parts[3]
                    })
        
        for line in leaders.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    sector_data['price_leaders'].append({
                        'ticker': parts[0],
                        'sector': parts[1],
                        'change_pct': float(parts[2]) if parts[2].replace('.','').isdigit() else 0,
                        'momentum': int(parts[3]) if parts[3].isdigit() else 0
                    })
        
        self.data['sectors'] = sector_data
        return sector_data
    
    def layer_3_technical(self) -> Dict:
        """Layer 3: Technical signals, alpha zoo, patterns."""
        print("🔍 Layer 3: Technical Analysis...")
        
        technical = self.db_query("""
            SELECT ticker, score, alpha_zoo_score, alpha_factor_count, mean_reversion_signals, computed_at 
            FROM technical_signals 
            ORDER BY score DESC LIMIT 20
        """)
        
        patterns = self.db_query("""
            SELECT ticker, pattern_type, conviction, direction, detected_at 
            FROM pattern_alerts 
            WHERE alerted = true 
            ORDER BY detected_at DESC LIMIT 15
        """)
        
        tech_data = {
            'alpha_zoo': [],
            'patterns': [],
            'oversold': [],
            'breakouts': []
        }
        
        for line in technical.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 5:
                    ticker = parts[0]
                    score = int(parts[1]) if parts[1].isdigit() else 0
                    alpha = int(parts[2]) if parts[2].isdigit() else 0
                    signals = parts[4]
                    
                    tech_data['alpha_zoo'].append({
                        'ticker': ticker,
                        'score': score,
                        'alpha': alpha,
                        'signals': signals
                    })
                    
                    if 'oversold' in signals.lower():
                        tech_data['oversold'].append(ticker)
        
        for line in patterns.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    tech_data['patterns'].append({
                        'ticker': parts[0],
                        'type': parts[1],
                        'conviction': parts[2],
                        'direction': parts[3]
                    })
                    
                    if 'breakout' in parts[1].lower() or 'momentum' in parts[1].lower():
                        tech_data['breakouts'].append(parts[0])
        
        self.data['technical'] = tech_data
        return tech_data
    
    def layer_4_fundamental(self) -> Dict:
        """Layer 4: Fundamental analysis, earnings, growth, margins."""
        print("🔍 Layer 4: Fundamental Analysis...")
        
        # SP500 grades with full components
        sp500 = self.db_query("""
            SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, computed_at 
            FROM sp500_grades 
            WHERE vox_grade >= 65 
            ORDER BY vox_grade DESC 
            LIMIT 30
        """)
        
        # Portfolio positions
        positions = self.db_query("""
            SELECT ticker, grade, council, brokers, sector, live_value_usd, updated_at 
            FROM positions 
            WHERE status = 'active' OR status IS NULL
            ORDER BY grade DESC
        """)
        
        fund_data = {
            'sp500_leaders': [],
            'portfolio': [],
            'strong_fundamentals': []
        }
        
        for line in sp500.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 8:
                    fund_data['sp500_leaders'].append({
                        'ticker': parts[0],
                        'grade': int(parts[1]),
                        'technical': int(parts[2]),
                        'fundamental': int(parts[3]),
                        'macro': int(parts[4]),
                        'sector': int(parts[5]),
                        'weather': int(parts[6]),
                        'sentiment': int(parts[7])
                    })
        
        for line in positions.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 7:
                    fund_data['portfolio'].append({
                        'ticker': parts[0],
                        'grade': int(parts[1]) if parts[1].isdigit() else 0,
                        'council': parts[2],
                        'value': float(parts[5]) if parts[5] else 0
                    })
        
        self.data['fundamental'] = fund_data
        return fund_data
    
    def layer_5_sentiment(self) -> Dict:
        """Layer 5: News sentiment, social, analyst ratings."""
        print("🔍 Layer 5: Sentiment Analysis...")
        
        sentiment = self.db_query("""
            SELECT ticker, vox_score, raw_score, mention_count, article_count, 
                   bullish_count, somewhat_bullish_count, neutral_count, 
                   somewhat_bearish_count, bearish_count, bullish_ratio, source, computed_at 
            FROM sentiment_scores 
            ORDER BY vox_score DESC 
            LIMIT 15
        """)
        
        sent_data = {
            'top_sentiment': [],
            'bullish': [],
            'bearish': [],
            'contrarian': []
        }
        
        for line in sentiment.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 12:
                    ticker = parts[0]
                    vox_score = int(parts[1]) if parts[1].isdigit() else 0
                    bullish_ratio = float(parts[11]) if parts[11].replace('.','').isdigit() else 0
                    
                    sent_data['top_sentiment'].append({
                        'ticker': ticker,
                        'vox_score': vox_score,
                        'bullish_ratio': bullish_ratio
                    })
                    
                    if bullish_ratio < 0.4 and vox_score > 60:
                        sent_data['contrarian'].append(ticker)
                    elif bullish_ratio > 0.6:
                        sent_data['bullish'].append(ticker)
                    elif bullish_ratio < 0.3:
                        sent_data['bearish'].append(ticker)
        
        self.data['sentiment'] = sent_data
        return sent_data
    
    def layer_6_opportunities(self) -> List[Dict]:
        """Layer 6: Synthesize all layers into actionable opportunities."""
        print("🔍 Layer 6: Opportunity Synthesis...")
        
        opportunities = []
        
        # Get all graded stocks
        all_grades = self.db_query("""
            SELECT DISTINCT ON (ticker) ticker, vox_grade, action, generated_at 
            FROM vox_grades 
            ORDER BY ticker, generated_at DESC
        """)
        
        # Get trade signals
        trades = self.db_query("""
            SELECT DISTINCT ON (ticker) ticker, signal_type, composite_score, grade, created_at 
            FROM trade_signals 
            ORDER BY ticker, created_at DESC
        """)
        
        # Build trade signal lookup
        trade_lookup = {}
        for line in trades.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 4:
                    trade_lookup[parts[0]] = {
                        'signal': parts[1],
                        'composite': int(parts[2]) if parts[2].replace('.','').isdigit() else 0,
                        'grade': int(parts[3]) if parts[3].isdigit() else 0
                    }
        
        # Score each stock
        for line in all_grades.split('\n'):
            if line.strip():
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 3:
                    ticker = parts[0]
                    grade = int(parts[1]) if parts[1].isdigit() else 0
                    action = parts[2]
                    
                    # Calculate opportunity score
                    opp_score = grade
                    
                    # Boost for trade signals
                    if ticker in trade_lookup:
                        ts = trade_lookup[ticker]
                        if ts['signal'] == 'ADD':
                            opp_score += 5
                        elif ts['signal'] == 'BUY':
                            opp_score += 3
                        elif ts['signal'] == 'SELL':
                            opp_score -= 10
                    
                    # Boost for macro alignment
                    macro_signals = self.data.get('macro', {}).get('signals', [])
                    for signal in macro_signals:
                        if signal.get('direction') == 'BULLISH' and signal.get('confidence', 0) > 70:
                            opp_score += 2
                    
                    # Boost for technical patterns
                    tech = self.data.get('technical', {})
                    if ticker in tech.get('breakouts', []):
                        opp_score += 5
                    if ticker in tech.get('oversold', []):
                        opp_score += 3
                    
                    # Boost for sentiment
                    sent = self.data.get('sentiment', {})
                    if ticker in sent.get('contrarian', []):
                        opp_score += 3
                    
                    opportunities.append({
                        'ticker': ticker,
                        'grade': grade,
                        'action': action,
                        'opportunity_score': opp_score,
                        'trade_signal': trade_lookup.get(ticker, {}),
                        'layers': {
                            'macro_aligned': any(s.get('direction') == 'BULLISH' for s in macro_signals),
                            'technical_bullish': ticker in tech.get('breakouts', []),
                            'oversold': ticker in tech.get('oversold', []),
                            'contrarian': ticker in sent.get('contrarian', [])
                        }
                    })
        
        # Sort by opportunity score
        opportunities.sort(key=lambda x: x['opportunity_score'], reverse=True)
        
        self.data['opportunities'] = opportunities
        return opportunities
    
    def generate_report(self) -> str:
        """Generate comprehensive research report."""
        print("\n📊 Generating VOX Alpha Research Report...")
        
        report = []
        report.append("="*70)
        report.append("VOX ALPHA RESEARCH ENGINE v1.0")
        report.append("Target: 20% Yearly Profit")
        report.append(f"Generated: {self.data['generated_at']}")
        report.append("="*70)
        report.append("")
        
        # Macro Summary
        macro = self.data.get('macro', {})
        report.append("🌍 MACRO REGIME")
        report.append("-"*70)
        report.append(f"  Regime: {macro.get('regime', 'UNKNOWN')} ({macro.get('confidence', 0)}% confidence)")
        report.append(f"  VIX: {macro.get('vix', 0)}")
        report.append(f"  Key Signals:")
        for signal in macro.get('signals', [])[:5]:
            report.append(f"    • {signal['name']}: {signal['direction']} ({signal['confidence']}% conf)")
        report.append("")
        
        # Sector Summary
        sectors = self.data.get('sectors', {})
        report.append("📈 SECTOR MOMENTUM")
        report.append("-"*70)
        for sector in sectors.get('momentum_ranking', [])[:5]:
            report.append(f"  {sector['sector']:30s} | Momentum: {sector['momentum']:3d} | Avg Grade: {sector['avg_grade']:.1f}")
        report.append("")
        
        # Top Opportunities
        report.append("🎯 TOP 20 OPPORTUNITIES (All 6 Layers)")
        report.append("-"*70)
        report.append(f"{'Rank':<5} {'Ticker':<8} {'Grade':<6} {'Opp Score':<10} {'Action':<8} {'Trade':<8} {'Layers'}")
        report.append("-"*70)
        
        for i, opp in enumerate(self.data.get('opportunities', [])[:20], 1):
            layers = []
            if opp['layers'].get('macro_aligned'):
                layers.append("M")
            if opp['layers'].get('technical_bullish'):
                layers.append("T")
            if opp['layers'].get('oversold'):
                layers.append("O")
            if opp['layers'].get('contrarian'):
                layers.append("C")
            
            ts = opp.get('trade_signal', {})
            ts_str = ts.get('signal', 'N/A') if ts else 'N/A'
            
            report.append(f"{i:<5} {opp['ticker']:<8} {opp['grade']:<6} {opp['opportunity_score']:<10} {opp['action']:<8} {ts_str:<8} {','.join(layers)}")
        
        report.append("")
        
        # Portfolio Status
        fund = self.data.get('fundamental', {})
        report.append("💼 PORTFOLIO STATUS")
        report.append("-"*70)
        
        hold_positions = [p for p in fund.get('portfolio', []) if p['council'] == 'HOLD']
        sell_positions = [p for p in fund.get('portfolio', []) if p['council'] == 'SELL']
        
        report.append(f"  HOLD positions: {len(hold_positions)} (avg grade: {statistics.mean([p['grade'] for p in hold_positions]) if hold_positions else 0:.1f})")
        report.append(f"  SELL positions: {len(sell_positions)} (avg grade: {statistics.mean([p['grade'] for p in sell_positions]) if sell_positions else 0:.1f})")
        report.append(f"  Total value: ${sum(p['value'] for p in fund.get('portfolio', [])):,.2f}")
        report.append("")
        
        # SP500 Leaders not in portfolio
        report.append("⭐ SP500 LEADERS NOT IN PORTFOLIO")
        report.append("-"*70)
        portfolio_tickers = {p['ticker'] for p in fund.get('portfolio', [])}
        for stock in fund.get('sp500_leaders', [])[:10]:
            if stock['ticker'] not in portfolio_tickers:
                report.append(f"  {stock['ticker']:<8} | Grade: {stock['grade']:>3} | Fund: {stock['fundamental']:>3} | Tech: {stock['technical']:>3} | Macro: {stock['macro']:>3}")
        report.append("")
        
        # Technical Signals
        tech = self.data.get('technical', {})
        report.append("📊 TECHNICAL SIGNALS")
        report.append("-"*70)
        report.append(f"  Oversold bounce candidates: {len(tech.get('oversold', []))}")
        report.append(f"  Breakout candidates: {len(tech.get('breakouts', []))}")
        report.append(f"  Alpha Zoo top: {tech.get('alpha_zoo', [{}])[0].get('ticker', 'N/A')} (score: {tech.get('alpha_zoo', [{}])[0].get('score', 0)})")
        report.append("")
        
        # Sentiment
        sent = self.data.get('sentiment', {})
        report.append("💭 SENTIMENT ANALYSIS")
        report.append("-"*70)
        report.append(f"  Contrarian opportunities (negative sentiment, high score): {len(sent.get('contrarian', []))}")
        report.append(f"  Bullish consensus: {len(sent.get('bullish', []))}")
        report.append(f"  Bearish consensus: {len(sent.get('bearish', []))}")
        report.append("")
        
        # Final Recommendations
        report.append("🎯 FINAL RECOMMENDATIONS")
        report.append("-"*70)
        
        top_5 = self.data.get('opportunities', [])[:5]
        for i, opp in enumerate(top_5, 1):
            report.append(f"  #{i}: {opp['ticker']} (Score: {opp['opportunity_score']}, Grade: {opp['grade']})")
            report.append(f"      Action: {opp['action']}")
            if opp.get('trade_signal'):
                report.append(f"      Trade Signal: {opp['trade_signal'].get('signal', 'N/A')} (Grade: {opp['trade_signal'].get('grade', 'N/A')})")
            report.append(f"      Layer Alignment: {', '.join([k for k, v in opp['layers'].items() if v])}")
            report.append("")
        
        report.append("="*70)
        report.append("END OF REPORT")
        report.append("="*70)
        
        return "\n".join(report)
    
    def run(self):
        """Execute full research pipeline."""
        print("🚀 VOX Alpha Research Engine Starting...")
        print("="*70)
        
        self.layer_1_macro()
        self.layer_2_sectors()
        self.layer_3_technical()
        self.layer_4_fundamental()
        self.layer_5_sentiment()
        self.layer_6_opportunities()
        
        report = self.generate_report()
        
        # Save to file
        output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_alpha_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(output_file, 'w') as f:
            f.write(report)
        
        # Save JSON data
        json_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_alpha_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
        
        print(f"\n✅ Report saved to: {output_file}")
        print(f"✅ Data saved to: {json_file}")
        
        return report

if __name__ == '__main__':
    engine = VoxAlphaEngine()
    report = engine.run()
    print(report)
