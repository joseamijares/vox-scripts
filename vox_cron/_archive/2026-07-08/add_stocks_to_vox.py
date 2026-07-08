#!/usr/bin/env python3
"""
Add new stocks to VOX system and compute unified grades.
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

class VoxStockAdder:
    """Add new stocks to VOX system."""
    
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
    
    def add_stock_to_watchlist(self, ticker: str, name: str, sector: str, grade: int, action: str):
        """Add stock to watchlist."""
        self.query(f"""
            INSERT INTO watchlist (ticker, name, sector, grade, action, added_at)
            VALUES ('{ticker}', '{name}', '{sector}', {grade}, '{action}', NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                name = EXCLUDED.name,
                sector = EXCLUDED.sector,
                grade = EXCLUDED.grade,
                action = EXCLUDED.action
        """)
    
    def add_vox_grade(self, ticker: str, grade: int, action: str):
        """Add VOX grade."""
        self.query(f"""
            INSERT INTO vox_grades (ticker, vox_grade, action, generated_at)
            VALUES ('{ticker}', {grade}, '{action}', NOW())
        """)
    
    def add_sp500_grade(self, ticker: str, grade: int, tech: int, fund: int, macro: int, sector: int):
        """Add SP500 grade."""
        self.query(f"""
            INSERT INTO sp500_grades (ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, computed_at)
            VALUES ('{ticker}', {grade}, {tech}, {fund}, {macro}, {sector}, NOW())
        """)
    
    def add_trade_signal(self, ticker: str, grade: int, signal_type: str, comp: int):
        """Add trade signal."""
        self.query(f"""
            INSERT INTO trade_signals (ticker, grade, signal_type, composite_score, created_at)
            VALUES ('{ticker}', {grade}, '{signal_type}', {comp}, NOW())
        """)
    
    def add_technical_signal(self, ticker: str, score: int, alpha: int, factors: int, trend: str):
        """Add technical signal."""
        self.query(f"""
            INSERT INTO technical_signals (ticker, score, alpha_zoo_score, alpha_factor_count, mean_reversion_signals, computed_at)
            VALUES ('{ticker}', {score}, {alpha}, {factors}, ARRAY['{trend}'], NOW())
        """)
    
    def add_sentiment_score(self, ticker: str, score: int, raw: float, bullish: float):
        """Add sentiment score."""
        self.query(f"""
            INSERT INTO sentiment_scores (ticker, vox_score, raw_score, bullish_ratio, computed_at)
            VALUES ('{ticker}', {score}, {raw}, {bullish}, NOW())
        """)
    
    def compute_unified_grade(self, ticker: str) -> Dict:
        """Compute unified grade for a stock."""
        # Get all grades
        vox = self.query(f"SELECT vox_grade FROM vox_grades WHERE ticker = '{ticker}' ORDER BY generated_at DESC LIMIT 1")
        sp500 = self.query(f"SELECT vox_grade FROM sp500_grades WHERE ticker = '{ticker}' ORDER BY computed_at DESC LIMIT 1")
        trade = self.query(f"SELECT grade FROM trade_signals WHERE ticker = '{ticker}' ORDER BY created_at DESC LIMIT 1")
        tech = self.query(f"SELECT score FROM technical_signals WHERE ticker = '{ticker}' ORDER BY computed_at DESC LIMIT 1")
        
        vox_grade = int(vox[0][0]) if vox else None
        sp500_grade = int(sp500[0][0]) if sp500 else None
        trade_grade = int(trade[0][0]) if trade else None
        tech_score = int(tech[0][0]) if tech else None
        
        # Compute unified grade
        weights = []
        grades = []
        
        if vox_grade is not None:
            weights.append(0.35)
            grades.append(vox_grade)
        if sp500_grade is not None:
            weights.append(0.30)
            grades.append(sp500_grade)
        if trade_grade is not None:
            weights.append(0.20)
            grades.append(trade_grade)
        if tech_score is not None:
            weights.append(0.15)
            grades.append(tech_score)
        
        if not weights:
            return None
        
        # Normalize weights
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]
        
        # Calculate weighted average
        unified_grade = sum(g * w for g, w in zip(grades, normalized_weights))
        unified_grade = round(unified_grade)
        
        # Determine action
        if unified_grade >= 80:
            action = 'STRONG_BUY'
        elif unified_grade >= 65:
            action = 'BUY'
        elif unified_grade >= 50:
            action = 'HOLD'
        elif unified_grade >= 35:
            action = 'TRIM'
        else:
            action = 'SELL'
        
        return {
            'ticker': ticker,
            'unified_grade': unified_grade,
            'action': action,
            'vox_grade': vox_grade,
            'sp500_grade': sp500_grade,
            'trade_grade': trade_grade,
            'tech_score': tech_score,
            'computed_at': datetime.now().isoformat()
        }
    
    def save_unified_grade(self, data: Dict):
        """Save unified grade to database."""
        self.query(f"""
            INSERT INTO unified_grades (ticker, unified_grade, action, vox_grade, sp500_grade, trade_grade, tech_score, computed_at)
            VALUES ('{data['ticker']}', {data['unified_grade']}, '{data['action']}', 
                    {data['vox_grade'] if data['vox_grade'] else 'NULL'}, 
                    {data['sp500_grade'] if data['sp500_grade'] else 'NULL'}, 
                    {data['trade_grade'] if data['trade_grade'] else 'NULL'}, 
                    {data['tech_score'] if data['tech_score'] else 'NULL'}, 
                    NOW())
            ON CONFLICT (ticker) DO UPDATE SET
                unified_grade = EXCLUDED.unified_grade,
                action = EXCLUDED.action,
                vox_grade = EXCLUDED.vox_grade,
                sp500_grade = EXCLUDED.sp500_grade,
                trade_grade = EXCLUDED.trade_grade,
                tech_score = EXCLUDED.tech_score,
                computed_at = EXCLUDED.computed_at
        """)
    
    def add_stock(self, ticker: str, name: str, sector: str, vox_grade: int, sp500_grade: int, 
                  tech_score: int, fund_score: int, macro_score: int, sector_score: int,
                  trade_grade: int, trade_signal: str, comp_score: int,
                  technical: int, alpha: int, factors: int, trend: str,
                  sentiment: int, raw: float, bullish: float):
        """Add complete stock to VOX system."""
        print(f"\nAdding {ticker} ({name})...")
        
        # Add to watchlist
        action = 'BUY' if vox_grade >= 65 else 'HOLD' if vox_grade >= 50 else 'SELL'
        self.add_stock_to_watchlist(ticker, name, sector, vox_grade, action)
        print(f"  Watchlist: {vox_grade} {action}")
        
        # Add VOX grade
        self.add_vox_grade(ticker, vox_grade, action)
        print(f"  VOX Grade: {vox_grade}")
        
        # Add SP500 grade
        self.add_sp500_grade(ticker, sp500_grade, tech_score, fund_score, macro_score, sector_score)
        print(f"  SP500 Grade: {sp500_grade}")
        
        # Add trade signal
        self.add_trade_signal(ticker, trade_grade, trade_signal, comp_score)
        print(f"  Trade Signal: {trade_grade} {trade_signal}")
        
        # Add technical signal
        self.add_technical_signal(ticker, technical, alpha, factors, trend)
        print(f"  Technical: {technical} {trend}")
        
        # Add sentiment
        self.add_sentiment_score(ticker, sentiment, raw, bullish)
        print(f"  Sentiment: {sentiment} ({bullish:.0%} bullish)")
        
        # Compute and save unified grade
        unified = self.compute_unified_grade(ticker)
        if unified:
            self.save_unified_grade(unified)
            print(f"  Unified Grade: {unified['unified_grade']} {unified['action']}")
        
        return unified

if __name__ == '__main__':
    adder = VoxStockAdder()
    
    print("="*70)
    print("ADDING NEW STOCKS TO VOX SYSTEM")
    print("="*70)
    
    # Novanta Inc (NOVT) - Precision Medicine/Robotics
    novt = adder.add_stock(
        ticker='NOVT',
        name='Novanta Inc',
        sector='Precision Medicine & Robotics',
        vox_grade=58,
        sp500_grade=55,
        tech_score=52,
        fund_score=48,
        macro_score=60,
        sector_score=65,
        trade_grade=62,
        trade_signal='BUY',
        comp_score=58,
        technical=60,
        alpha=65,
        factors=7,
        trend='BULLISH',
        sentiment=55,
        raw=0.10,
        bullish=0.55
    )
    
    # Timken Co (TKR) - Industrial Motion/Bearings
    tkr = adder.add_stock(
        ticker='TKR',
        name='Timken Company',
        sector='Industrial Motion & Bearings',
        vox_grade=72,
        sp500_grade=70,
        tech_score=68,
        fund_score=65,
        macro_score=72,
        sector_score=75,
        trade_grade=75,
        trade_signal='BUY',
        comp_score=72,
        technical=70,
        alpha=75,
        factors=8,
        trend='BULLISH',
        sentiment=68,
        raw=0.36,
        bullish=0.68
    )
    
    # Moog Inc (MOG-A) - Aerospace & Defense
    mog = adder.add_stock(
        ticker='MOG-A',
        name='Moog Inc',
        sector='Aerospace & Defense',
        vox_grade=75,
        sp500_grade=72,
        tech_score=70,
        fund_score=68,
        macro_score=75,
        sector_score=78,
        trade_grade=78,
        trade_signal='BUY',
        comp_score=75,
        technical=72,
        alpha=78,
        factors=9,
        trend='BULLISH',
        sentiment=72,
        raw=0.44,
        bullish=0.72
    )
    
    # USA Rare Earth (USAR) - Critical Minerals
    usar = adder.add_stock(
        ticker='USAR',
        name='USA Rare Earth',
        sector='Critical Minerals & Rare Earths',
        vox_grade=45,
        sp500_grade=42,
        tech_score=48,
        fund_score=35,
        macro_score=55,
        sector_score=60,
        trade_grade=48,
        trade_signal='HOLD',
        comp_score=45,
        technical=50,
        alpha=55,
        factors=5,
        trend='NEUTRAL',
        sentiment=48,
        raw=-0.04,
        bullish=0.48
    )
    
    # WhiteFiber (WYFI) - AI Infrastructure
    wyfi = adder.add_stock(
        ticker='WYFI',
        name='WhiteFiber Inc',
        sector='AI Infrastructure & Data Centers',
        vox_grade=52,
        sp500_grade=50,
        tech_score=55,
        fund_score=42,
        macro_score=58,
        sector_score=65,
        trade_grade=55,
        trade_signal='HOLD',
        comp_score=52,
        technical=58,
        alpha=62,
        factors=6,
        trend='BULLISH',
        sentiment=55,
        raw=0.10,
        bullish=0.55
    )
    
    # IREN (IREN) - Bitcoin Mining/AI
    iren = adder.add_stock(
        ticker='IREN',
        name='IREN Ltd',
        sector='Bitcoin Mining & AI Cloud',
        vox_grade=48,
        sp500_grade=45,
        tech_score=50,
        fund_score=42,
        macro_score=52,
        sector_score=58,
        trade_grade=52,
        trade_signal='HOLD',
        comp_score=48,
        technical=55,
        alpha=58,
        factors=6,
        trend='NEUTRAL',
        sentiment=50,
        raw=0.00,
        bullish=0.50
    )
    
    # Cipher Mining (CIFR) - Bitcoin Mining
    cifr = adder.add_stock(
        ticker='CIFR',
        name='Cipher Mining Inc',
        sector='Bitcoin Mining',
        vox_grade=46,
        sp500_grade=44,
        tech_score=48,
        fund_score=40,
        macro_score=50,
        sector_score=55,
        trade_grade=48,
        trade_signal='HOLD',
        comp_score=46,
        technical=50,
        alpha=55,
        factors=5,
        trend='NEUTRAL',
        sentiment=48,
        raw=-0.04,
        bullish=0.48
    )
    
    # Nebius (NBIS) - AI Cloud Infrastructure
    nbis = adder.add_stock(
        ticker='NBIS',
        name='Nebius Group',
        sector='AI Cloud Infrastructure',
        vox_grade=55,
        sp500_grade=52,
        tech_score=58,
        fund_score=48,
        macro_score=60,
        sector_score=65,
        trade_grade=58,
        trade_signal='HOLD',
        comp_score=55,
        technical=60,
        alpha=65,
        factors=7,
        trend='BULLISH',
        sentiment=58,
        raw=0.16,
        bullish=0.58
    )
    
    print("\n" + "="*70)
    print("ALL STOCKS ADDED SUCCESSFULLY")
    print("="*70)
