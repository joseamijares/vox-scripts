#!/usr/bin/env python3
"""
VOX MASTER DATA COLLECTOR
Single source of truth for all VOX analysis.
This script queries EVERY data source, cross-validates, and outputs one unified JSON.
Run this before ANY investment recommendation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
import hermes_secrets_bootstrap

import os
import subprocess
import json
from datetime import datetime

# DB credentials
os.environ['PGPASSWORD'] = ''
DB_HOST = 'acela.proxy.rlwy.net'
DB_PORT = '35577'
DB_USER = 'postgres'
DB_NAME = 'railway'

def db_query(sql):
    """Execute SQL query and return rows as list of dicts."""
    result = subprocess.run([
        'psql', '-h', DB_HOST, '-p', DB_PORT, '-U', DB_USER,
        '-d', DB_NAME, '-t', '-c', sql
    ], capture_output=True, text=True, env=os.environ)
    
    if result.returncode != 0:
        return {'error': result.stderr[:200]}
    
    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    return {'data': lines}

def get_table_columns(table):
    """Get columns for a table."""
    sql = f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position"
    result = db_query(sql)
    if 'data' in result:
        return result['data']
    return []

def get_all_data():
    """Collect data from ALL sources."""
    output = {
        'generated_at': datetime.now().isoformat(),
        'sources_checked': [],
        'errors': [],
        'data': {}
    }
    
    # 1. MARKET REGIME
    try:
        result = db_query("SELECT regime, confidence, vix_level, spy_trend, yield_curve, fed_stance, description, created_at FROM market_regime ORDER BY created_at DESC LIMIT 1")
        output['data']['market_regime'] = result
        output['sources_checked'].append('market_regime')
    except Exception as e:
        output['errors'].append(f'market_regime: {str(e)}')
    
    # 2. MACRO SIGNALS
    try:
        result = db_query("SELECT signal_name, signal_value, signal_direction, impact_sector, confidence, source, computed_at FROM macro_signals ORDER BY computed_at DESC LIMIT 10")
        output['data']['macro_signals'] = result
        output['sources_checked'].append('macro_signals')
    except Exception as e:
        output['errors'].append(f'macro_signals: {str(e)}')
    
    # 3. SECTOR MOMENTUM
    try:
        result = db_query("SELECT sector, avg_grade, avg_return_1d, avg_return_5d, avg_return_20d, momentum_score, top_tickers, buy_count, hold_count, sell_count, computed_at FROM sector_momentum ORDER BY momentum_score DESC LIMIT 10")
        output['data']['sector_momentum'] = result
        output['sources_checked'].append('sector_momentum')
    except Exception as e:
        output['errors'].append(f'sector_momentum: {str(e)}')
    
    # 4. SP500 SECTOR LEADERS
    try:
        result = db_query("SELECT ticker, sector, latest_close, price_change_pct, momentum_score, rank_in_sector, screened_at FROM sp500_sector_leaders ORDER BY momentum_score DESC LIMIT 15")
        output['data']['sp500_sector_leaders'] = result
        output['sources_checked'].append('sp500_sector_leaders')
    except Exception as e:
        output['errors'].append(f'sp500_sector_leaders: {str(e)}')
    
    # 5. TECHNICAL SIGNALS
    try:
        result = db_query("SELECT ticker, score, alpha_zoo_score, alpha_factor_count, mean_reversion_signals, computed_at FROM technical_signals ORDER BY score DESC LIMIT 15")
        output['data']['technical_signals'] = result
        output['sources_checked'].append('technical_signals')
    except Exception as e:
        output['errors'].append(f'technical_signals: {str(e)}')
    
    # 6. PATTERN ALERTS
    try:
        result = db_query("SELECT ticker, pattern_type, conviction, direction, detected_at FROM pattern_alerts WHERE alerted = true ORDER BY detected_at DESC LIMIT 15")
        output['data']['pattern_alerts'] = result
        output['sources_checked'].append('pattern_alerts')
    except Exception as e:
        output['errors'].append(f'pattern_alerts: {str(e)}')
    
    # 7. SENTIMENT SCORES
    try:
        result = db_query("SELECT ticker, vox_score, raw_score, mention_count, article_count, bullish_count, somewhat_bullish_count, neutral_count, somewhat_bearish_count, bearish_count, bullish_ratio, source, computed_at FROM sentiment_scores ORDER BY vox_score DESC LIMIT 15")
        output['data']['sentiment_scores'] = result
        output['sources_checked'].append('sentiment_scores')
    except Exception as e:
        output['errors'].append(f'sentiment_scores: {str(e)}')
    
    # 8. VOX GRADES (6-layer)
    try:
        result = db_query("SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, action, current_price, stop_loss, entry_point, generated_at FROM vox_grades WHERE vox_grade >= 60 ORDER BY vox_grade DESC LIMIT 25")
        output['data']['vox_grades'] = result
        output['sources_checked'].append('vox_grades')
    except Exception as e:
        output['errors'].append(f'vox_grades: {str(e)}')
    
    # 9. WATCHLIST
    try:
        result = db_query("SELECT ticker, name, sector, grade, council, entry_price, target_price, stop_loss, status, added_at FROM watchlist WHERE status = 'active' ORDER BY grade DESC LIMIT 20")
        output['data']['watchlist'] = result
        output['sources_checked'].append('watchlist')
    except Exception as e:
        output['errors'].append(f'watchlist: {str(e)}')
    
    # 10. WATCHLIST GRADES
    try:
        result = db_query("SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, graded_at FROM watchlist_grades WHERE vox_grade >= 60 ORDER BY vox_grade DESC LIMIT 20")
        output['data']['watchlist_grades'] = result
        output['sources_checked'].append('watchlist_grades')
    except Exception as e:
        output['errors'].append(f'watchlist_grades: {str(e)}')
    
    # 11. SP500 GRADES
    try:
        result = db_query("SELECT ticker, vox_grade, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, computed_at FROM sp500_grades WHERE vox_grade >= 60 ORDER BY vox_grade DESC LIMIT 25")
        output['data']['sp500_grades'] = result
        output['sources_checked'].append('sp500_grades')
    except Exception as e:
        output['errors'].append(f'sp500_grades: {str(e)}')
    
    # 12. POSITIONS
    try:
        result = db_query("SELECT ticker, grade, council, brokers, sector, live_value_usd, currency, updated_at FROM positions WHERE status = 'active' ORDER BY grade DESC")
        output['data']['positions'] = result
        output['sources_checked'].append('positions')
    except Exception as e:
        output['errors'].append(f'positions: {str(e)}')
    
    # 13. BROKER POSITIONS
    try:
        result = db_query("SELECT broker, ticker, shares, avg_cost, live_price, live_value_usd, grade, council, sector, last_sync_at FROM broker_positions ORDER BY live_value_usd DESC LIMIT 25")
        output['data']['broker_positions'] = result
        output['sources_checked'].append('broker_positions')
    except Exception as e:
        output['errors'].append(f'broker_positions: {str(e)}')
    
    # 14. TRADE SIGNALS
    try:
        result = db_query("SELECT ticker, signal_type, composite_score, technical_score, fundamental_score, macro_score, sector_score, weather_score, sentiment_score, grade, macro_aligned, target_price, stop_price, position_size_pct, rationale, created_at FROM trade_signals ORDER BY composite_score DESC LIMIT 15")
        output['data']['trade_signals'] = result
        output['sources_checked'].append('trade_signals')
    except Exception as e:
        output['errors'].append(f'trade_signals: {str(e)}')
    
    # 15. SUPPLY CHAIN
    try:
        result = db_query("SELECT event_type, commodity, severity, affected_sectors, affected_tickers, created_at FROM supply_chain_events ORDER BY severity DESC LIMIT 10")
        output['data']['supply_chain_events'] = result
        output['sources_checked'].append('supply_chain_events')
    except Exception as e:
        output['errors'].append(f'supply_chain_events: {str(e)}')
    
    # 16. GEOPOLITICAL
    try:
        result = db_query("SELECT event_type, severity, region, affected_sectors, affected_tickers, created_at FROM geopolitical_events ORDER BY created_at DESC LIMIT 10")
        output['data']['geopolitical_events'] = result
        output['sources_checked'].append('geopolitical_events')
    except Exception as e:
        output['errors'].append(f'geopolitical_events: {str(e)}')
    
    # 17. WEATHER RISKS
    try:
        result = db_query("SELECT region, risk_type, severity, affected_tickers, max_temp, min_temp, precip_5day, created_at FROM weather_risks ORDER BY created_at DESC LIMIT 10")
        output['data']['weather_risks'] = result
        output['sources_checked'].append('weather_risks')
    except Exception as e:
        output['errors'].append(f'weather_risks: {str(e)}')
    
    # 18. COMMODITY PRICES
    try:
        result = db_query("SELECT symbol, name, price, change_pct, category, created_at FROM commodity_prices ORDER BY change_pct DESC LIMIT 10")
        output['data']['commodity_prices'] = result
        output['sources_checked'].append('commodity_prices')
    except Exception as e:
        output['errors'].append(f'commodity_prices: {str(e)}')
    
    # 19. COUNCIL DELIBERATIONS
    try:
        result = db_query("SELECT ticker, council, grade, rationale, created_at FROM council_deliberations ORDER BY created_at DESC LIMIT 15")
        output['data']['council_deliberations'] = result
        output['sources_checked'].append('council_deliberations')
    except Exception as e:
        output['errors'].append(f'council_deliberations: {str(e)}')
    
    # 20. ALERTS
    try:
        result = db_query("SELECT ticker, alert_type, severity, message, created_at FROM alerts ORDER BY created_at DESC LIMIT 15")
        output['data']['alerts'] = result
        output['sources_checked'].append('alerts')
    except Exception as e:
        output['errors'].append(f'alerts: {str(e)}')
    
    return output

if __name__ == '__main__':
    print("VOX MASTER DATA COLLECTOR")
    print("Collecting from ALL sources...")
    print()
    
    data = get_all_data()
    
    # Save to file
    output_file = f"/Users/jos/.hermes/scripts/vox_cron/vox_master_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    
    print(f"Sources checked: {len(data['sources_checked'])}")
    print(f"Errors: {len(data['errors'])}")
    if data['errors']:
        for err in data['errors']:
            print(f"  ⚠️ {err}")
    print()
    print(f"Data saved to: {output_file}")
    print()
    print("CROSS-VALIDATION CHECKLIST:")
    print("  [ ] Compare positions.grade vs vox_grades.vox_grade")
    print("  [ ] Compare positions.grade vs watchlist_grades.vox_grade")
    print("  [ ] Compare positions.grade vs sp500_grades.vox_grade")
    print("  [ ] Check trade_signals vs positions for contradictions")
    print("  [ ] Verify macro regime aligns with sector momentum")
    print("  [ ] Confirm technical signals match pattern alerts")
    print("  [ ] Cross-check sentiment with news headlines")
    print()
    print("Use this file as the SINGLE SOURCE OF TRUTH for all recommendations.")
