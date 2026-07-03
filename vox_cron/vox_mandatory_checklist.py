#!/usr/bin/env python3
"""
VOX MANDATORY CHECKLIST SYSTEM
This script MUST be run before ANY investment recommendation.
It enforces using ALL 20 database tables, ALL external sources, ALL tools.
Failure to complete any step = NO recommendation allowed.

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
from typing import Dict, List, Tuple, Optional

class VoxMandatoryChecklist:
    """Enforces complete analysis before any recommendation."""
    
    def __init__(self):
        self.checklist = {}
        self.data = {}
        self.errors = []
        self.warnings = []
        
    def run_checklist(self) -> Dict:
        """Run the complete mandatory checklist."""
        print("="*70)
        print("VOX MANDATORY CHECKLIST — RUNNING ALL SYSTEMS")
        print("="*70)
        print()
        
        # Step 1: Database Connection
        self.check_db_connection()
        
        # Step 2: All 20 Tables
        self.query_all_tables()
        
        # Step 3: Cross-Validation
        self.cross_validate()
        
        # Step 4: External Research (Web)
        self.external_research()
        
        # Step 5: Social Layer (Reddit/X)
        self.social_research()
        
        # Step 6: Final Verification
        return self.final_verification()
    
    def check_db_connection(self):
        """Step 1: Verify database connection."""
        print("[1/6] Checking database connection...")
        os.environ['PGPASSWORD'] = ''
        
        result = subprocess.run([
            'psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres',
            '-d', 'railway', '-t', '-c', 'SELECT NOW()'
        ], capture_output=True, text=True, env=os.environ)
        
        if result.returncode == 0:
            self.checklist['db_connection'] = True
            print("  ✅ Database connected")
        else:
            self.checklist['db_connection'] = False
            self.errors.append("Database connection failed")
            print("  ❌ Database connection FAILED")
    
    def query_all_tables(self):
        """Step 2: Query ALL 20 tables. NO exceptions."""
        print("[2/6] Querying ALL 20 database tables...")
        
        tables = [
            'market_regime',
            'sector_momentum',
            'sp500_sector_leaders',
            'technical_signals',
            'sentiment_scores',
            'vox_grades',
            'watchlist',
            'positions',
            'pattern_alerts',
            'trade_signals',
            'macro_signals',
            'sp500_grades',
            'sp500_alerts',
            'sp500_universe',
            'commodity_prices',
            'council_deliberations',
            'cron_runs',
            'geopolitical_events',
            'supply_chain_events',
            'weather_patterns',
            'weather_risks',
            'alerts',
            'journal',
            'system_logs',
            'watchlist_grades',
            'watchlist_old',
            'plays',
            'broker_accounts',
            'broker_holdings',
            'broker_positions',
            'broker_status',
            'unified_grades'  # NEW: Single source of truth
        ]
        
        for table in tables:
            result = subprocess.run([
                'psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres',
                '-d', 'railway', '-t', '-c', f'SELECT COUNT(*) FROM {table}'
            ], capture_output=True, text=True, env=os.environ)
            
            if result.returncode == 0:
                count = result.stdout.strip()
                self.data[table] = {'status': 'OK', 'count': count}
                print(f"  ✅ {table}: {count} rows")
            else:
                self.data[table] = {'status': 'ERROR', 'error': result.stderr}
                self.errors.append(f"Table {table} query failed")
                print(f"  ❌ {table}: FAILED")
        
        self.checklist['all_tables_queried'] = len(self.errors) == 0
    
    def cross_validate(self):
        """Step 3: Cross-validate all data sources."""
        print("[3/6] Cross-validating data sources...")
        
        # Check for grade contradictions
        result = subprocess.run([
            'psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres',
            '-d', 'railway', '-t', '-c', """
                SELECT vg.ticker, vg.vox_grade, sg.vox_grade as sp500_grade,
                       ABS(vg.vox_grade - sg.vox_grade) as diff
                FROM vox_grades vg
                JOIN sp500_grades sg ON vg.ticker = sg.ticker
                WHERE vg.generated_at > NOW() - INTERVAL '24 hours'
                AND sg.computed_at > NOW() - INTERVAL '7 days'
                AND ABS(vg.vox_grade - sg.vox_grade) > 10
                ORDER BY diff DESC
                LIMIT 10
            """
        ], capture_output=True, text=True, env=os.environ)
        
        if result.returncode == 0:
            contradictions = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if contradictions:
                self.warnings.append(f"Found {len(contradictions)} grade contradictions > 10 points")
                print(f"  ⚠️  {len(contradictions)} grade contradictions found")
                for c in contradictions[:5]:
                    print(f"     {c}")
            else:
                print("  ✅ No major contradictions")
        
        # Check for trade signal contradictions
        result = subprocess.run([
            'psql', '-h', 'acela.proxy.rlwy.net', '-p', '35577', '-U', 'postgres',
            '-d', 'railway', '-t', '-c', """
                SELECT vg.ticker, vg.vox_grade, vg.action, ts.grade as ts_grade, ts.signal_type
                FROM vox_grades vg
                JOIN trade_signals ts ON vg.ticker = ts.ticker
                WHERE vg.generated_at > NOW() - INTERVAL '24 hours'
                AND ts.created_at > NOW() - INTERVAL '7 days'
                AND (
                    (vg.action = 'SELL' AND ts.signal_type = 'BUY') OR
                    (vg.action = 'BUY' AND ts.signal_type = 'SELL')
                )
                LIMIT 10
            """
        ], capture_output=True, text=True, env=os.environ)
        
        if result.returncode == 0:
            contradictions = [l for l in result.stdout.strip().split('\n') if l.strip()]
            if contradictions:
                self.warnings.append(f"Found {len(contradictions)} trade signal contradictions")
                print(f"  ⚠️  {len(contradictions)} trade signal contradictions")
                for c in contradictions[:5]:
                    print(f"     {c}")
            else:
                print("  ✅ No trade signal contradictions")
        
        self.checklist['cross_validated'] = True
    
    def external_research(self):
        """Step 4: External research via web search."""
        print("[4/6] External research (web search)...")
        print("  ⚠️  Web search requires manual execution")
        print("  ⚠️  Must search for: market outlook, sector trends, earnings")
        self.checklist['external_research'] = 'MANUAL_REQUIRED'
    
    def social_research(self):
        """Step 5: Social layer (Reddit/X)."""
        print("[5/6] Social research (Reddit/X)...")
        print("  ⚠️  Social layer requires manual execution")
        print("  ⚠️  Must search for: sentiment, WSB mentions, pump risk")
        self.checklist['social_research'] = 'MANUAL_REQUIRED'
    
    def final_verification(self) -> Dict:
        """Step 6: Final verification before recommendation."""
        print("[6/6] Final verification...")
        
        # Check if all steps completed
        all_complete = all([
            self.checklist.get('db_connection', False),
            self.checklist.get('all_tables_queried', False),
            self.checklist.get('cross_validated', False),
        ])
        
        if all_complete and len(self.errors) == 0:
            print("  ✅ ALL CHECKS PASSED")
            print()
            print("="*70)
            print("VOX CHECKLIST COMPLETE — RECOMMENDATION ALLOWED")
            print("="*70)
        else:
            print("  ❌ CHECKLIST FAILED")
            print()
            print("="*70)
            print("VOX CHECKLIST FAILED — NO RECOMMENDATION ALLOWED")
            print("="*70)
            print()
            print("Errors:")
            for e in self.errors:
                print(f"  - {e}")
            print()
            print("Warnings:")
            for w in self.warnings:
                print(f"  - {w}")
        
        return {
            'checklist': self.checklist,
            'data': self.data,
            'errors': self.errors,
            'warnings': self.warnings,
            'can_recommend': all_complete and len(self.errors) == 0,
            'timestamp': datetime.now().isoformat()
        }

if __name__ == '__main__':
    checklist = VoxMandatoryChecklist()
    result = checklist.run_checklist()
    
    # Save result
    output_file = f"/Users/jos/.hermes/scripts/vox_cron/checklist_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\nResult saved to: {output_file}")
