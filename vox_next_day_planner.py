#!/usr/bin/env python3
"""
VOX Next-Day Planner v9.2
Generates tomorrow's action plan with exact execution details.
Only the best of the best — maximum 5 trades per day.

Usage:
    python3 vox_next_day_planner.py [--digest vox_daily_digest.json] [--output plan.json]
    python3 vox_next_day_planner.py --send-telegram

Outputs:
    - JSON plan with exact broker/shares/price/stop/cash
    - Markdown plan for Obsidian vault
    - Telegram alert with execution checklist
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('/Users/jos/.hermes/.env')

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
DIGEST_FILE = SCRIPT_DIR / 'vox_daily_digest.json'
PORTFOLIO_DIR = SCRIPT_DIR / 'snapshots'
BROKER_FILES = {
    'eToro': SCRIPT_DIR / 'etoro_portfolio.json',
    'GBM Main': SCRIPT_DIR / 'gbm_main_portfolio.json',
    'GBM USA': SCRIPT_DIR / 'gbm_usa_portfolio.json',
    'Schwab': SCRIPT_DIR / 'schwab_portfolio.json',
    'IBKR': SCRIPT_DIR / 'ibkr_portfolio.json',
    'Binance': SCRIPT_DIR / 'binance_portfolio.json',
    'Bitso': SCRIPT_DIR / 'bitso_portfolio.json',
    'Revolut': SCRIPT_DIR / 'revolut_portfolio.json',
}

# Execution rules
MAX_TRADES_PER_DAY = 5
MIN_CASH_RESERVE_PCT = 10  # Keep at least 10% cash
MAX_POSITION_PCT = 15      # No position > 15% of portfolio
CORE_POSITION_PCT = 8      # Target for core positions
SPEC_POSITION_PCT = 3      # Target for speculative positions

# Broker preferences by trade type
BROKER_PREFERENCE = {
    'core': ['Schwab', 'IBKR', 'GBM USA'],
    'speculative': ['eToro', 'GBM Main'],
    'crypto': ['Binance', 'Bitso'],
    'trim': ['any'],
}

# ─── DATA LOADING ────────────────────────────────────────────────────

def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def load_digest():
    return load_json(DIGEST_FILE, {})

def load_portfolio():
    snapshots = sorted(PORTFOLIO_DIR.glob('snapshot_*.json'))
    if not snapshots:
        return {}
    return load_json(snapshots[-1])

def load_broker_data(broker):
    path = BROKER_FILES.get(broker)
    if path and path.exists():
        return load_json(path)
    return {}

def get_broker_cash(broker):
    """Get available cash for a broker."""
    data = load_broker_data(broker)
    return data.get('cash', 0)

def get_position_at_broker(ticker, broker):
    """Check if ticker exists at broker and return position."""
    data = load_broker_data(broker)
    positions = data.get('positions', [])
    for pos in positions:
        if pos.get('ticker') == ticker:
            return pos
    return None

# ─── POSITION SIZER ──────────────────────────────────────────────────

def calculate_position_size(ticker, action_type, portfolio, broker, current_price):
    """Calculate exact shares and cash impact."""
    total_value = portfolio.get('total_value', 0)
    cash = get_broker_cash(broker)
    
    # Determine target size based on action type
    if action_type == 'BUY':
        # New position
        target_pct = SPEC_POSITION_PCT  # Start small
        target_value = total_value * (target_pct / 100)
        
        # Cap at available cash minus reserve
        min_cash = total_value * (MIN_CASH_RESERVE_PCT / 100)
        max_deploy = cash - min_cash
        
        deploy = min(target_value, max_deploy)
        if deploy < 100:  # Minimum trade size
            return None
        
        shares = int(deploy / current_price)
        cash_impact = shares * current_price
        
        return {
            'shares': shares,
            'cash_impact': cash_impact,
            'target_pct': (shares * current_price / total_value * 100) if total_value > 0 else 0,
        }
    
    elif action_type == 'ADD':
        # Add to existing position
        pos = get_position_at_broker(ticker, broker)
        if not pos:
            return None
        
        current_value = pos.get('market_value', 0)
        target_value = total_value * (CORE_POSITION_PCT / 100)
        add_value = target_value - current_value
        
        # Cap at available cash
        min_cash = total_value * (MIN_CASH_RESERVE_PCT / 100)
        max_deploy = cash - min_cash
        
        deploy = min(add_value, max_deploy)
        if deploy < 100:
            return None
        
        shares = int(deploy / current_price)
        cash_impact = shares * current_price
        
        return {
            'shares': shares,
            'cash_impact': cash_impact,
            'target_pct': ((current_value + cash_impact) / total_value * 100) if total_value > 0 else 0,
        }
    
    elif action_type == 'TRIM':
        # Trim position
        pos = get_position_at_broker(ticker, broker)
        if not pos:
            return None
        
        current_shares = pos.get('shares', 0)
        trim_pct = 0.25  # Trim 25% by default
        
        shares = max(1, int(current_shares * trim_pct))
        cash_impact = shares * current_price  # Positive (selling)
        
        return {
            'shares': -shares,  # Negative = selling
            'cash_impact': cash_impact,
            'remaining_shares': current_shares - shares,
        }
    
    elif action_type == 'SELL':
        # Sell all
        pos = get_position_at_broker(ticker, broker)
        if not pos:
            return None
        
        shares = pos.get('shares', 0)
        cash_impact = shares * current_price
        
        return {
            'shares': -shares,
            'cash_impact': cash_impact,
            'remaining_shares': 0,
        }
    
    return None

# ─── STOP CALCULATOR ─────────────────────────────────────────────────

def calculate_stop(ticker, action_type, current_price, grade, portfolio):
    """Calculate exact stop loss price."""
    
    # Base stop percentages by action type
    if action_type in ['BUY', 'ADD']:
        if grade >= 75:
            stop_pct = 0.08  # 8% for high-grade positions
        elif grade >= 60:
            stop_pct = 0.10  # 10% for moderate
        else:
            stop_pct = 0.12  # 12% for lower grade
    elif action_type == 'TRIM':
        # Trailing stop for trims
        stop_pct = 0.15  # 15% trailing
    else:
        stop_pct = 0.10
    
    stop_price = round(current_price * (1 - stop_pct), 2)
    
    return {
        'price': stop_price,
        'pct': stop_pct * 100,
        'risk_amount': current_price - stop_price,
    }

# ─── BROKER SELECTOR ─────────────────────────────────────────────────

def select_broker(ticker, action_type, portfolio):
    """Select best broker for the trade."""
    
    # Check where position already exists
    for broker in BROKER_FILES.keys():
        pos = get_position_at_broker(ticker, broker)
        if pos:
            # Position exists here — prefer same broker
            if action_type in ['ADD', 'TRIM', 'SELL']:
                return broker
    
    # For new buys, select based on type
    if action_type == 'BUY':
        # Check cash availability
        candidates = BROKER_PREFERENCE['core']
        for broker in candidates:
            cash = get_broker_cash(broker)
            if cash > 500:  # Minimum deployable
                return broker
        
        # Fallback to any broker with cash
        for broker in BROKER_FILES.keys():
            cash = get_broker_cash(broker)
            if cash > 500:
                return broker
    
    return 'Schwab'  # Default

# ─── PLAN GENERATOR ──────────────────────────────────────────────────

def generate_plan(date_str=None):
    """Generate tomorrow's action plan."""
    
    if date_str is None:
        tomorrow = datetime.now() + timedelta(days=1)
        date_str = tomorrow.strftime('%Y-%m-%d')
    
    print(f"📋 VOX Next-Day Planner — {date_str}")
    print("=" * 60)
    
    # Load data
    digest = load_digest()
    portfolio = load_portfolio()
    
    if not digest:
        print("❌ No digest found. Run vox_daily_digest.py first.")
        return None
    
    # Get all actions from digest
    all_actions = digest.get('winners', []) + digest.get('losers', []) + digest.get('reviews', [])
    
    # Filter to top N
    all_actions.sort(key=lambda x: x.get('score', 0), reverse=True)
    selected_actions = all_actions[:MAX_TRADES_PER_DAY]
    
    print(f"🎯 Processing {len(selected_actions)} actions...")
    
    # Generate detailed plans
    execution_plans = []
    total_cash_impact = 0
    
    for action in selected_actions:
        ticker = action['ticker']
        action_type = action['action']
        grade = action['grade']
        
        # Get current price (from digest or portfolio)
        current_price = 100.0  # Default fallback
        positions = portfolio.get('positions', [])
        pos = next((p for p in positions if p.get('ticker') == ticker), None)
        if pos:
            current_price = pos.get('current_price', current_price)
        
        # Select broker
        broker = select_broker(ticker, action_type, portfolio)
        
        # Calculate position size
        sizing = calculate_position_size(ticker, action_type, portfolio, broker, current_price)
        if not sizing:
            print(f"⚠️  Could not size {ticker} — skipping")
            continue
        
        # Calculate stop
        stop = calculate_stop(ticker, action_type, current_price, grade, portfolio)
        
        # Calculate timeline
        if action_type in ['BUY', 'ADD']:
            timeline = 'Execute at market open or on pullback to entry zone'
        elif action_type == 'SELL':
            timeline = 'Execute immediately — do not delay'
        elif action_type == 'TRIM':
            timeline = 'Trim within 2 trading days'
        else:
            timeline = 'Review within 48 hours'
        
        plan = {
            'rank': len(execution_plans) + 1,
            'ticker': ticker,
            'action': action_type,
            'score': action['score'],
            'grade': grade,
            'urgency': action['urgency'],
            'broker': broker,
            'current_price': current_price,
            'shares': abs(sizing['shares']),
            'direction': 'BUY' if sizing['shares'] > 0 else 'SELL',
            'estimated_value': sizing['cash_impact'],
            'cash_impact': sizing['cash_impact'] if sizing['shares'] > 0 else -sizing['cash_impact'],
            'stop_price': stop['price'],
            'stop_pct': stop['pct'],
            'timeline': timeline,
            'thesis': action.get('thesis', f"Grade {grade} — {action_type} signal"),
            'risk_amount': stop['risk_amount'] * abs(sizing['shares']),
        }
        
        execution_plans.append(plan)
        total_cash_impact += plan['cash_impact']
    
    # Build final plan
    plan = {
        'date': date_str,
        'generated_at': datetime.now().isoformat(),
        'based_on_digest': digest.get('date'),
        'market_regime': digest.get('market_regime', {}),
        'summary': {
            'total_actions': len(execution_plans),
            'buys': len([p for p in execution_plans if p['action'] in ['BUY', 'ADD']]),
            'sells': len([p for p in execution_plans if p['action'] in ['SELL', 'TRIM']]),
            'total_cash_needed': sum(p['cash_impact'] for p in execution_plans if p['cash_impact'] > 0),
            'total_cash_generated': abs(sum(p['cash_impact'] for p in execution_plans if p['cash_impact'] < 0)),
            'net_cash_impact': total_cash_impact,
        },
        'execution_plan': execution_plans,
        'pre_trade_checklist': [
            '☐ Review all positions one more time before market open',
            '☐ Check pre-market futures and news',
            '☐ Verify cash balances at each broker',
            '☐ Confirm stop prices are set before entry',
            '☐ Execute SELLs first, then BUYs',
            '☐ Never chase — if price gaps above entry, skip',
            '☐ Log all trades immediately after execution',
        ],
        'post_trade_checklist': [
            '☐ Update position notes in Obsidian',
            '☐ Set price alerts for stops',
            '☐ Review P&L at market close',
            '☐ Update grade if significant move',
        ],
    }
    
    return plan

# ─── OUTPUT GENERATORS ───────────────────────────────────────────────

def save_plan_json(plan, output_path):
    with open(output_path, 'w') as f:
        json.dump(plan, f, indent=2)
    print(f"💾 Plan saved: {output_path}")

def generate_markdown_plan(plan):
    """Generate markdown plan for Obsidian."""
    date = plan['date']
    summary = plan['summary']
    
    md = f"""# 📋 VOX Action Plan — {date}

**Generated:** {plan['generated_at']}
**Based on Digest:** {plan['based_on_digest']}
**Market Regime:** {plan['market_regime'].get('regime', 'neutral').upper()}

## 💰 Cash Flow Summary
| Metric | Amount |
|--------|--------|
| Cash Needed (Buys) | ${summary['total_cash_needed']:,.2f} |
| Cash Generated (Sells) | ${summary['total_cash_generated']:,.2f} |
| **Net Cash Impact** | **${summary['net_cash_impact']:,.2f}** |

## 🎯 Execution Plan ({summary['total_actions']} Trades)

"""
    
    for p in plan['execution_plan']:
        emoji = "🟢" if p['action'] in ['BUY', 'ADD'] else "🔴"
        md += f"### {p['rank']}. {emoji} {p['ticker']} — {p['action']}\n\n"
        md += f"| Field | Value |\n"
        md += f"|-------|-------|\n"
        md += f"| **Broker** | {p['broker']} |\n"
        md += f"| **Action** | {p['direction']} {p['shares']} shares |\n"
        md += f"| **Current Price** | ${p['current_price']:.2f} |\n"
        md += f"| **Estimated Value** | ${p['estimated_value']:,.2f} |\n"
        md += f"| **Stop Price** | ${p['stop_price']:.2f} ({p['stop_pct']:.1f}%) |\n"
        md += f"| **Cash Impact** | ${p['cash_impact']:,.2f} |\n"
        md += f"| **Risk Amount** | ${p['risk_amount']:,.2f} |\n"
        md += f"| **Timeline** | {p['timeline']} |\n"
        md += f"| **Score** | {p['score']} |\n"
        md += f"| **Grade** | {p['grade']}/100 |\n"
        md += f"| **Urgency** | {p['urgency']} |\n"
        md += f"\n**Thesis:** {p['thesis']}\n\n"
        md += "---\n\n"
    
    md += "## ✅ Pre-Trade Checklist\n\n"
    for item in plan['pre_trade_checklist']:
        md += f"{item}\n"
    
    md += "\n## ✅ Post-Trade Checklist\n\n"
    for item in plan['post_trade_checklist']:
        md += f"{item}\n"
    
    md += "\n---\n*Generated by VOX Next-Day Planner v9.2*\n"
    
    return md

def save_markdown_plan(plan, vault_path):
    md = generate_markdown_plan(plan)
    date = plan['date']
    
    actions_dir = Path(vault_path) / '09-Actions' / date
    actions_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = actions_dir / f'VOX Action Plan — {date}.md'
    with open(file_path, 'w') as f:
        f.write(md)
    
    print(f"📝 Plan saved: {file_path}")
    return file_path

def send_telegram_plan(plan):
    """Send execution plan via Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("⚠️  Telegram credentials not found")
        return False
    
    date = plan['date']
    summary = plan['summary']
    
    message = f"📋 *VOX Action Plan — {date}*\n\n"
    message += f"🎯 *{summary['total_actions']} Trades Planned*\n"
    message += f"🟢 Buys: {summary['buys']} | 🔴 Sells: {summary['sells']}\n"
    message += f"💰 Net Cash: ${summary['net_cash_impact']:,.2f}\n\n"
    
    for p in plan['execution_plan'][:3]:
        emoji = "🟢" if p['action'] in ['BUY', 'ADD'] else "🔴"
        message += f"{emoji} *{p['ticker']}* — {p['action']}\n"
        message += f"   {p['direction']} {p['shares']} @ ${p['current_price']:.2f}\n"
        message += f"   Stop: ${p['stop_price']:.2f} | Broker: {p['broker']}\n\n"
    
    if len(plan['execution_plan']) > 3:
        message += f"_+{len(plan['execution_plan']) - 3} more trades in full plan_\n"
    
    import urllib.request
    import urllib.parse
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = urllib.parse.urlencode({
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'Markdown'
    }).encode()
    
    try:
        req = urllib.request.Request(url, data=data, method='POST')
        urllib.request.urlopen(req)
        print("📱 Telegram plan sent")
        return True
    except Exception as e:
        print(f"❌ Telegram failed: {e}")
        return False

# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='VOX Next-Day Planner')
    parser.add_argument('--date', help='Date for plan (YYYY-MM-DD)')
    parser.add_argument('--output', default='vox_next_day_plan.json', help='Output JSON file')
    parser.add_argument('--vault', default='~/Documents/Obsidian Vault/Portfolio-Finance', help='Obsidian vault path')
    parser.add_argument('--send-telegram', action='store_true', help='Send plan via Telegram')
    
    args = parser.parse_args()
    
    # Generate plan
    plan = generate_plan(args.date)
    
    if not plan:
        sys.exit(1)
    
    # Save JSON
    output_path = SCRIPT_DIR / args.output
    save_plan_json(plan, output_path)
    
    # Save markdown
    vault_path = os.path.expanduser(args.vault)
    md_path = save_markdown_plan(plan, vault_path)
    
    # Send Telegram
    if args.send_telegram:
        send_telegram_plan(plan)
    
    # Print summary
    print("\n" + "=" * 60)
    print("📋 NEXT-DAY PLAN COMPLETE")
    print("=" * 60)
    print(f"🎯 Trades: {plan['summary']['total_actions']}")
    print(f"🟢 Buys: {plan['summary']['buys']} | 🔴 Sells: {plan['summary']['sells']}")
    print(f"💰 Net Cash: ${plan['summary']['net_cash_impact']:,.2f}")
    print(f"\n💾 JSON: {output_path}")
    print(f"📝 Markdown: {md_path}")
    
    print("\n🏆 TOMORROW'S TRADES:")
    for p in plan['execution_plan']:
        emoji = "🟢" if p['action'] in ['BUY', 'ADD'] else "🔴"
        print(f"   {p['rank']}. {emoji} {p['ticker']}: {p['direction']} {p['shares']} @ ${p['current_price']:.2f}")
        print(f"      Stop: ${p['stop_price']:.2f} | Broker: {p['broker']} | Score: {p['score']}")

if __name__ == '__main__':
    main()
