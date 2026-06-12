#!/usr/bin/env python3
"""
VOX Morning Debrief v9.2
Pre-market intelligence briefing delivered at 8:00 AM daily.

Covers:
1. Yesterday's Reflection — what happened, what we did, what we learned
2. Overnight News — futures, Asia, Europe, key headlines
3. Today's Watchlist — positions to watch, levels, earnings, alerts
4. Pre-Market Checklist — what to do before market open

Usage:
    python3 vox_morning_debrief.py [--date YYYY-MM-DD] [--send-telegram]
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv('/Users/jos/.hermes/.env')

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SNAPSHOT_DIR = SCRIPT_DIR / 'snapshots'
DIGEST_FILE = SCRIPT_DIR / 'vox_daily_digest.json'
PLAN_FILE = SCRIPT_DIR / 'vox_next_day_plan.json'
GRADES_FILE = SCRIPT_DIR / 'vox_grades.json'
BRIEF_FILE = SCRIPT_DIR / 'vox_daily_brief.json'
SOCIAL_FILE = SCRIPT_DIR / 'vox_social_sentiment.json'
NEWS_FILE = SCRIPT_DIR / 'vox_news_digest.json'
HISTORY_FILE = SCRIPT_DIR / 'vox_digest_history.json'
TRADE_LOG = SCRIPT_DIR / 'vox_trade_log.json'

# ─── DATA LOADING ────────────────────────────────────────────────────

def load_json(path, default=None):
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}

def load_yesterday_digest():
    """Load yesterday's digest for reflection."""
    return load_json(DIGEST_FILE, {})

def load_yesterday_plan():
    """Load yesterday's plan to check what we intended to do."""
    return load_json(PLAN_FILE, {})

def load_portfolio():
    snapshots = sorted(SNAPSHOT_DIR.glob('snapshot_*.json'))
    if len(snapshots) >= 2:
        # Compare yesterday vs today
        yesterday = load_json(snapshots[-2])
        today = load_json(snapshots[-1])
        return {'yesterday': yesterday, 'today': today}
    elif snapshots:
        return {'today': load_json(snapshots[-1])}
    return {}

def load_grades():
    return load_json(GRADES_FILE, {})

def load_brief():
    return load_json(BRIEF_FILE, {})

def load_social():
    return load_json(SOCIAL_FILE, {})

def load_news():
    return load_json(NEWS_FILE, {})

def load_trade_log():
    return load_json(TRADE_LOG, [])

# ─── SECTION 1: YESTERDAY'S REFLECTION ───────────────────────────────

def generate_reflection(yesterday_digest, yesterday_plan, portfolio, trade_log):
    """Reflect on what happened yesterday."""
    reflection = {
        'date': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
        'summary': {},
        'planned_vs_actual': [],
        'key_moves': [],
        'lessons': [],
    }
    
    # What did we plan to do?
    planned_trades = yesterday_plan.get('execution_plan', [])
    reflection['summary']['planned_trades'] = len(planned_trades)
    
    # What did we actually do?
    yesterday_trades = [t for t in trade_log if t.get('date') == reflection['date']]
    reflection['summary']['executed_trades'] = len(yesterday_trades)
    
    # Planned vs Actual
    for planned in planned_trades:
        ticker = planned['ticker']
        actual = next((t for t in yesterday_trades if t.get('ticker') == ticker), None)
        
        status = 'EXECUTED' if actual else 'MISSED'
        reflection['planned_vs_actual'].append({
            'ticker': ticker,
            'planned_action': planned['action'],
            'status': status,
            'actual_price': actual.get('price') if actual else None,
            'planned_price': planned.get('current_price'),
            'difference_pct': ((actual.get('price', 0) - planned.get('current_price', 0)) / planned.get('current_price', 1) * 100) if actual else None,
        })
    
    # Portfolio changes
    if portfolio.get('yesterday') and portfolio.get('today'):
        yesterday_value = portfolio['yesterday'].get('total_value', 0)
        today_value = portfolio['today'].get('total_value', 0)
        change = today_value - yesterday_value
        change_pct = (change / yesterday_value * 100) if yesterday_value > 0 else 0
        
        reflection['summary']['portfolio_change'] = change
        reflection['summary']['portfolio_change_pct'] = round(change_pct, 2)
        reflection['summary']['yesterday_value'] = yesterday_value
        reflection['summary']['today_value'] = today_value
        
        # Biggest movers in portfolio
        yesterday_positions = {p['ticker']: p for p in portfolio['yesterday'].get('positions', [])}
        today_positions = {p['ticker']: p for p in portfolio['today'].get('positions', [])}
        
        movers = []
        for ticker, today_pos in today_positions.items():
            yesterday_pos = yesterday_positions.get(ticker)
            if yesterday_pos:
                today_price = today_pos.get('current_price', 0)
                yesterday_price = yesterday_pos.get('current_price', 0)
                if yesterday_price > 0:
                    move_pct = (today_price - yesterday_price) / yesterday_price * 100
                    if abs(move_pct) >= 3:  # Only significant moves
                        movers.append({
                            'ticker': ticker,
                            'move_pct': round(move_pct, 2),
                            'direction': 'UP' if move_pct > 0 else 'DOWN',
                        })
        
        movers.sort(key=lambda x: abs(x['move_pct']), reverse=True)
        reflection['key_moves'] = movers[:10]
    
    # Lessons from missed trades
    missed = [p for p in reflection['planned_vs_actual'] if p['status'] == 'MISSED']
    if missed:
        reflection['lessons'].append(f"Missed {len(missed)} planned trades — review execution discipline")
    
    # Lessons from big movers
    big_down = [m for m in reflection['key_moves'] if m['direction'] == 'DOWN' and abs(m['move_pct']) >= 5]
    if big_down:
        reflection['lessons'].append(f"{len(big_down)} positions dropped >5% — check stops")
    
    return reflection

# ─── SECTION 2: OVERNIGHT NEWS ───────────────────────────────────────

def generate_news_summary(news_data, brief):
    """Summarize overnight news and market moves."""
    summary = {
        'futures': {},
        'asia': {},
        'europe': {},
        'headlines': [],
        'portfolio_impact': [],
    }
    
    # Futures
    futures = brief.get('futures', {})
    summary['futures'] = {
        'sp500': futures.get('sp500', {}),
        'nasdaq': futures.get('nasdaq', {}),
        'dow': futures.get('dow', {}),
        'vix': futures.get('vix', {}),
    }
    
    # Asia/Europe
    summary['asia'] = brief.get('asia_markets', {})
    summary['europe'] = brief.get('europe_markets', {})
    
    # Key headlines
    headlines = news_data.get('headlines', [])
    summary['headlines'] = headlines[:10]  # Top 10
    
    # Portfolio-related news
    portfolio_tickers = set()
    for snapshot in SNAPSHOT_DIR.glob('snapshot_*.json'):
        data = load_json(snapshot)
        for pos in data.get('positions', []):
            portfolio_tickers.add(pos.get('ticker'))
    
    for headline in headlines:
        title = headline.get('title', '')
        for ticker in portfolio_tickers:
            if ticker and ticker in title:
                summary['portfolio_impact'].append({
                    'ticker': ticker,
                    'headline': title,
                    'source': headline.get('source', ''),
                })
                break
    
    return summary

# ─── SECTION 3: TODAY'S WATCHLIST ────────────────────────────────────

def generate_watchlist(portfolio, grades, brief, social):
    """Generate today's watchlist with key levels and alerts."""
    watchlist = {
        'earnings_today': [],
        'earnings_this_week': [],
        'grade_alerts': [],
        'price_alerts': [],
        'social_alerts': [],
        'technical_setups': [],
    }
    
    # Earnings
    earnings = brief.get('earnings_calendar', [])
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    for e in earnings:
        days = e.get('days_to_earnings', 999)
        if days == 0:
            watchlist['earnings_today'].append(e)
        elif days <= 3:
            watchlist['earnings_this_week'].append(e)
    
    # Grade alerts — big changes
    current_grades = grades
    history = load_json(HISTORY_FILE, [])
    
    if history:
        yesterday_grades = history[-1].get('grades', {}) if history else {}
        for ticker, current in current_grades.items():
            prev = yesterday_grades.get(ticker, {})
            if prev:
                change = current.get('grade', 50) - prev.get('grade', 50)
                if abs(change) >= 10:
                    watchlist['grade_alerts'].append({
                        'ticker': ticker,
                        'old_grade': prev.get('grade', 50),
                        'new_grade': current.get('grade', 50),
                        'change': change,
                        'direction': 'UP' if change > 0 else 'DOWN',
                    })
    
    # Price alerts — positions near stops or targets
    today_portfolio = portfolio.get('today', {})
    positions = today_portfolio.get('positions', [])
    
    for pos in positions:
        ticker = pos.get('ticker')
        current = pos.get('current_price', 0)
        avg_cost = pos.get('avg_cost', 0)
        
        if avg_cost > 0:
            unrealized_pct = (current - avg_cost) / avg_cost * 100
            
            # Near stop loss (within 2%)
            if unrealized_pct < -8 and unrealized_pct > -12:
                watchlist['price_alerts'].append({
                    'ticker': ticker,
                    'alert_type': 'STOP_APPROACHING',
                    'current_pct': round(unrealized_pct, 2),
                    'message': f'Down {abs(unrealized_pct):.1f}% — approaching stop zone',
                })
            
            # Big winner — consider trim
            if unrealized_pct > 100:
                watchlist['price_alerts'].append({
                    'ticker': ticker,
                    'alert_type': 'TRIM_CANDIDATE',
                    'current_pct': round(unrealized_pct, 2),
                    'message': f'Up {unrealized_pct:.1f}% — strong trim candidate',
                })
    
    # Social alerts
    for ticker, sentiment in social.items():
        bullish = sentiment.get('bullish', 0)
        bearish = sentiment.get('bearish', 0)
        total = bullish + bearish
        
        if total >= 10:
            ratio = bullish / total
            if ratio >= 0.8 or ratio <= 0.2:
                watchlist['social_alerts'].append({
                    'ticker': ticker,
                    'sentiment': 'BULLISH' if ratio >= 0.8 else 'BEARISH',
                    'mentions': total,
                    'message': f'Extreme {"bullish" if ratio >= 0.8 else "bearish"} sentiment ({total} mentions)',
                })
    
    # Technical setups from brief
    market_data = brief.get('market_data', {})
    for ticker, data in market_data.items():
        rsi = data.get('rsi', 50)
        if rsi >= 75 or rsi <= 25:
            watchlist['technical_setups'].append({
                'ticker': ticker,
                'setup': 'OVERSOLD' if rsi <= 25 else 'OVERBOUGHT',
                'rsi': rsi,
                'message': f'RSI {rsi:.0f} — {"potential bounce" if rsi <= 25 else "potential pullback"}',
            })
    
    return watchlist

# ─── SECTION 4: PRE-MARKET CHECKLIST ─────────────────────────────────

def generate_checklist(reflection, news, watchlist, portfolio):
    """Generate pre-market checklist."""
    checklist = []
    
    # Reflection-based
    missed = [p for p in reflection.get('planned_vs_actual', []) if p['status'] == 'MISSED']
    if missed:
        checklist.append(f"☐ Review {len(missed)} missed trades from yesterday — why did we miss them?")
    
    # News-based
    if news.get('portfolio_impact'):
        checklist.append(f"☐ Read {len(news['portfolio_impact'])} news items affecting your positions")
    
    # Earnings
    if watchlist['earnings_today']:
        checklist.append(f"☐ Earnings today: {', '.join(e['ticker'] for e in watchlist['earnings_today'])} — know your plan BEFORE open")
    
    # Grade alerts
    if watchlist['grade_alerts']:
        down_grades = [g for g in watchlist['grade_alerts'] if g['direction'] == 'DOWN']
        if down_grades:
            checklist.append(f"☐ {len(down_grades)} positions had significant grade drops — review thesis")
    
    # Price alerts
    stop_alerts = [a for a in watchlist['price_alerts'] if a['alert_type'] == 'STOP_APPROACHING']
    if stop_alerts:
        checklist.append(f"☐ {len(stop_alerts)} positions approaching stops — set alerts or execute")
    
    # Cash check
    today = portfolio.get('today', {})
    cash = today.get('cash', 0)
    total = today.get('total_value', 1)
    cash_pct = (cash / total * 100) if total > 0 else 0
    if cash_pct < 5:
        checklist.append(f"☐ LOW CASH: {cash_pct:.1f}% — prioritize sells before buys today")
    
    # Standard items
    checklist.extend([
        "☐ Check futures and pre-market movers",
        "☐ Review today's action plan (from digest)",
        "☐ Set price alerts for key levels",
        "☐ Execute sells FIRST, then buys",
        "☐ Log all trades immediately",
    ])
    
    return checklist

# ─── MAIN DEBRIEF GENERATOR ──────────────────────────────────────────

def generate_debrief(date_str=None):
    """Generate the full morning debrief."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    print(f"🌅 VOX Morning Debrief — {date_str}")
    print("=" * 60)
    
    # Load all data
    yesterday_digest = load_yesterday_digest()
    yesterday_plan = load_yesterday_plan()
    portfolio = load_portfolio()
    grades = load_grades()
    brief = load_brief()
    social = load_social()
    news = load_news()
    trade_log = load_trade_log()
    
    # Generate sections
    reflection = generate_reflection(yesterday_digest, yesterday_plan, portfolio, trade_log)
    news_summary = generate_news_summary(news, brief)
    watchlist = generate_watchlist(portfolio, grades, brief, social)
    checklist = generate_checklist(reflection, news_summary, watchlist, portfolio)
    
    debrief = {
        'date': date_str,
        'generated_at': datetime.now().isoformat(),
        'market_regime': brief.get('market_regime', {}),
        'sections': {
            'reflection': reflection,
            'news': news_summary,
            'watchlist': watchlist,
            'checklist': checklist,
        },
        'portfolio_snapshot': {
            'total_value': portfolio.get('today', {}).get('total_value', 0),
            'total_positions': len(portfolio.get('today', {}).get('positions', [])),
            'cash': portfolio.get('today', {}).get('cash', 0),
        },
    }
    
    return debrief

# ─── OUTPUT GENERATORS ───────────────────────────────────────────────

def save_debrief_json(debrief, output_path):
    with open(output_path, 'w') as f:
        json.dump(debrief, f, indent=2)
    print(f"💾 Debrief saved: {output_path}")

def generate_markdown_debrief(debrief):
    """Generate markdown for Obsidian vault."""
    date = debrief['date']
    reflection = debrief['sections']['reflection']
    news = debrief['sections']['news']
    watchlist = debrief['sections']['watchlist']
    checklist = debrief['sections']['checklist']
    
    md = f"""# 🌅 VOX Morning Debrief — {date}

**Generated:** {debrief['generated_at']}
**Market Regime:** {debrief['market_regime'].get('regime', 'neutral').upper()}

## 💰 Portfolio Snapshot
- **Total Value:** ${debrief['portfolio_snapshot']['total_value']:,.2f}
- **Positions:** {debrief['portfolio_snapshot']['total_positions']}
- **Cash:** ${debrief['portfolio_snapshot']['cash']:,.2f}

---

## 1️⃣ Yesterday's Reflection

**Date:** {reflection['date']}

### Summary
| Metric | Value |
|--------|-------|
| Planned Trades | {reflection['summary'].get('planned_trades', 0)} |
| Executed Trades | {reflection['summary'].get('executed_trades', 0)} |
| Portfolio Change | ${reflection['summary'].get('portfolio_change', 0):,.2f} ({reflection['summary'].get('portfolio_change_pct', 0):+.2f}%) |

### Planned vs Actual
| Ticker | Planned | Status | Price Diff |
|--------|---------|--------|------------|
"""
    
    for p in reflection.get('planned_vs_actual', []):
        diff = f"{p.get('difference_pct', 0):+.1f}%" if p.get('difference_pct') is not None else "N/A"
        md += f"| {p['ticker']} | {p['planned_action']} | {p['status']} | {diff} |\n"
    
    if reflection.get('key_moves'):
        md += "\n### Key Movers\n"
        for m in reflection['key_moves'][:5]:
            emoji = "🟢" if m['direction'] == 'UP' else "🔴"
            md += f"- {emoji} **{m['ticker']}**: {m['move_pct']:+.2f}%\n"
    
    if reflection.get('lessons'):
        md += "\n### Lessons\n"
        for lesson in reflection['lessons']:
            md += f"- 💡 {lesson}\n"
    
    md += "\n---\n\n## 2️⃣ Overnight News\n\n"
    
    # Futures
    futures = news.get('futures', {})
    md += "### Futures\n"
    for name, data in futures.items():
        if data:
            change = data.get('change', 0)
            emoji = "🟢" if change >= 0 else "🔴"
            md += f"- {emoji} **{name.upper()}**: {data.get('value', 'N/A')} ({change:+.2f}%)\n"
    
    # Headlines
    if news.get('headlines'):
        md += "\n### Top Headlines\n"
        for h in news['headlines'][:5]:
            md += f"- 📰 [{h.get('source', '')}] {h.get('title', '')}\n"
    
    # Portfolio impact
    if news.get('portfolio_impact'):
        md += "\n### 🚨 News Affecting Your Positions\n"
        for item in news['portfolio_impact']:
            md += f"- **{item['ticker']}**: {item['headline']} ({item['source']})\n"
    
    md += "\n---\n\n## 3️⃣ Today's Watchlist\n\n"
    
    # Earnings
    if watchlist['earnings_today']:
        md += "### ⚠️ Earnings TODAY\n"
        for e in watchlist['earnings_today']:
            md += f"- **{e['ticker']}** — {e.get('time', 'TBD')}\n"
    
    if watchlist['earnings_this_week']:
        md += f"\n### Earnings This Week ({len(watchlist['earnings_this_week'])} more)\n"
        for e in watchlist['earnings_this_week'][:5]:
            md += f"- **{e['ticker']}** — in {e.get('days_to_earnings', '?')} days\n"
    
    # Grade alerts
    if watchlist['grade_alerts']:
        md += "\n### Grade Alerts\n"
        for g in watchlist['grade_alerts'][:5]:
            emoji = "🟢" if g['direction'] == 'UP' else "🔴"
            md += f"- {emoji} **{g['ticker']}**: {g['old_grade']} → {g['new_grade']} ({g['change']:+.0f})\n"
    
    # Price alerts
    if watchlist['price_alerts']:
        md += "\n### Price Alerts\n"
        for a in watchlist['price_alerts'][:5]:
            emoji = "🚨" if a['alert_type'] == 'STOP_APPROACHING' else "✂️"
            md += f"- {emoji} **{a['ticker']}**: {a['message']}\n"
    
    # Technical setups
    if watchlist['technical_setups']:
        md += "\n### Technical Setups\n"
        for s in watchlist['technical_setups'][:5]:
            emoji = "📈" if s['setup'] == 'OVERSOLD' else "📉"
            md += f"- {emoji} **{s['ticker']}**: {s['message']}\n"
    
    md += "\n---\n\n## 4️⃣ Pre-Market Checklist\n\n"
    for item in checklist:
        md += f"{item}\n"
    
    md += "\n---\n*Generated by VOX Morning Debrief System v9.2*\n"
    
    return md

def save_markdown_debrief(debrief, vault_path):
    md = generate_markdown_debrief(debrief)
    date = debrief['date']
    
    daily_dir = Path(vault_path) / '06-Tracking' / 'Daily'
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = daily_dir / f'Debrief — {date}.md'
    with open(file_path, 'w') as f:
        f.write(md)
    
    print(f"📝 Debrief saved: {file_path}")
    return file_path

def send_telegram_debrief(debrief):
    """Send concise debrief via Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("⚠️  Telegram credentials not found")
        return False
    
    date = debrief['date']
    reflection = debrief['sections']['reflection']
    watchlist = debrief['sections']['watchlist']
    
    message = f"🌅 *VOX Morning Debrief — {date}*\n\n"
    
    # Portfolio change
    change = reflection['summary'].get('portfolio_change_pct', 0)
    emoji = "🟢" if change >= 0 else "🔴"
    message += f"{emoji} Portfolio: {change:+.2f}%\n"
    message += f"📊 Planned: {reflection['summary'].get('planned_trades', 0)} | Executed: {reflection['summary'].get('executed_trades', 0)}\n\n"
    
    # Earnings
    if watchlist['earnings_today']:
        message += "⚠️ *Earnings Today:*\n"
        for e in watchlist['earnings_today']:
            message += f"  • {e['ticker']}\n"
        message += "\n"
    
    # Key alerts
    alerts = (watchlist['grade_alerts'][:2] + 
              watchlist['price_alerts'][:2])
    if alerts:
        message += "🚨 *Key Alerts:*\n"
        for a in alerts:
            message += f"  • {a['ticker']}: {a.get('message', a.get('direction', 'ALERT'))}\n"
        message += "\n"
    
    message += "📋 Checklist in Obsidian vault\n"
    
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
        print("📱 Telegram debrief sent")
        return True
    except Exception as e:
        print(f"❌ Telegram failed: {e}")
        return False

# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='VOX Morning Debrief')
    parser.add_argument('--date', help='Date for debrief (YYYY-MM-DD)')
    parser.add_argument('--output', default='vox_morning_debrief.json', help='Output JSON file')
    parser.add_argument('--vault', default='~/Documents/Obsidian Vault/Portfolio-Finance', help='Obsidian vault path')
    parser.add_argument('--send-telegram', action='store_true', help='Send via Telegram')
    
    args = parser.parse_args()
    
    debrief = generate_debrief(args.date)
    
    if not debrief:
        sys.exit(1)
    
    # Save JSON
    output_path = SCRIPT_DIR / args.output
    save_debrief_json(debrief, output_path)
    
    # Save markdown
    vault_path = os.path.expanduser(args.vault)
    md_path = save_markdown_debrief(debrief, vault_path)
    
    # Send Telegram
    if args.send_telegram:
        send_telegram_debrief(debrief)
    
    # Print summary
    print("\n" + "=" * 60)
    print("🌅 MORNING DEBRIEF COMPLETE")
    print("=" * 60)
    
    reflection = debrief['sections']['reflection']
    print(f"📊 Portfolio: ${reflection['summary'].get('portfolio_change', 0):+.2f} ({reflection['summary'].get('portfolio_change_pct', 0):+.2f}%)")
    print(f"📋 Planned: {reflection['summary'].get('planned_trades', 0)} | Executed: {reflection['summary'].get('executed_trades', 0)}")
    
    watchlist = debrief['sections']['watchlist']
    print(f"⚠️  Earnings today: {len(watchlist['earnings_today'])}")
    print(f"🚨 Alerts: {len(watchlist['grade_alerts'])} grade, {len(watchlist['price_alerts'])} price")
    
    print(f"\n💾 JSON: {output_path}")
    print(f"📝 Markdown: {md_path}")

if __name__ == '__main__':
    main()
