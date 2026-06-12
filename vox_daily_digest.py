#!/usr/bin/env python3
"""
VOX Daily Digest & Reflection System v9.2
End-of-day intelligence processor that digests ALL data sources
and outputs only the highest-conviction actions for tomorrow.

Usage:
    python3 vox_daily_digest.py [--date YYYY-MM-DD] [--output digest.json]
    python3 vox_daily_digest.py --send-telegram  # Send digest via Telegram

Outputs:
    - JSON digest with ranked actions
    - Markdown summary for Obsidian vault
    - Telegram alert with top 3 actions only
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
import statistics

# Load .env for API keys
from dotenv import load_dotenv
load_dotenv('/Users/jos/.hermes/.env')

# ─── CONFIG ──────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
SNAPSHOT_DIR = SCRIPT_DIR / 'snapshots'
GRADES_FILE = SCRIPT_DIR / 'vox_grades.json'
PLAYS_FILE = SCRIPT_DIR / 'vox_generated_plays.json'
BRIEF_FILE = SCRIPT_DIR / 'vox_daily_brief.json'
SOCIAL_FILE = SCRIPT_DIR / 'vox_social_sentiment.json'
SIGNALS_FILE = SCRIPT_DIR / 'vox_signals.json'
HISTORY_FILE = SCRIPT_DIR / 'vox_digest_history.json'

# Scoring thresholds
MIN_ACTION_SCORE = 75       # Only actions scoring 75+ make the cut
MAX_DAILY_ACTIONS = 5       # Never more than 5 trades per day
MIN_CONFIDENCE = 70         # Minimum AI confidence for plays

# Weight system for ranking
WEIGHTS = {
    'grade_change': 0.20,      # Grade moved significantly today
    'price_move': 0.15,        # Large price move vs position
    'signal_fusion': 0.20,     # AI harness composite score
    'social_sentiment': 0.10,  # Reddit/X sentiment alignment
    'earnings_proximity': 0.10,# Earnings within 7 days
    'technical': 0.10,         # RSI, EMA breakouts
    'portfolio_risk': 0.10,    # Concentration, correlation
    'macro_alignment': 0.05,   # Market regime fit
}

# ─── DATA LOADING ────────────────────────────────────────────────────

def load_json(path, default=None):
    """Safely load JSON file."""
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Could not load {path}: {e}")
        return default if default is not None else {}

def load_portfolio():
    """Load latest portfolio snapshot."""
    snapshots = sorted(SNAPSHOT_DIR.glob('snapshot_*.json'))
    if not snapshots:
        return {}
    latest = snapshots[-1]
    return load_json(latest)

def load_grades():
    """Load current grades."""
    return load_json(GRADES_FILE, {})

def load_plays():
    """Load AI-generated plays."""
    return load_json(PLAYS_FILE, {}).get('plays', [])

def load_brief():
    """Load daily brief."""
    return load_json(BRIEF_FILE, {})

def load_social():
    """Load social sentiment data."""
    return load_json(SOCIAL_FILE, {})

def load_signals():
    """Load signal data."""
    return load_json(SIGNALS_FILE, {})

def load_history():
    """Load digest history for trend analysis."""
    return load_json(HISTORY_FILE, [])

# ─── SCORING ENGINE ──────────────────────────────────────────────────

def calculate_grade_change_score(ticker, current_grades, history):
    """Score based on grade movement."""
    if not history:
        return 50  # Neutral if no history
    
    current = current_grades.get(ticker, {}).get('grade', 50)
    
    # Find previous grade
    prev_grade = None
    for entry in reversed(history[-7:]):  # Last 7 days
        if ticker in entry.get('grades', {}):
            prev_grade = entry['grades'][ticker].get('grade')
            break
    
    if prev_grade is None:
        return 50
    
    change = current - prev_grade
    
    # Big grade drops are urgent (SELL signals)
    if change <= -15:
        return 95  # Urgent review needed
    elif change <= -10:
        return 85
    elif change <= -5:
        return 70
    # Big grade jumps are opportunities (BUY/ADD signals)
    elif change >= 15:
        return 90
    elif change >= 10:
        return 80
    elif change >= 5:
        return 65
    
    return 50 + (change * 2)  # Small changes

def calculate_price_move_score(ticker, portfolio, brief):
    """Score based on today's price action vs position."""
    # Get position data
    positions = portfolio.get('positions', [])
    pos = next((p for p in positions if p.get('ticker') == ticker), None)
    
    if not pos:
        return 50
    
    avg_cost = pos.get('avg_cost', 0)
    current = pos.get('current_price', avg_cost)
    
    # Get daily change from brief
    market_data = brief.get('market_data', {})
    ticker_data = market_data.get(ticker, {})
    daily_change = ticker_data.get('change_percent', 0)
    
    # If position is losing and dropping further → high score (SELL)
    unrealized_pct = ((current - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
    
    if unrealized_pct < -20 and daily_change < -3:
        return 95  # Stop loss violation
    elif unrealized_pct < -10 and daily_change < -2:
        return 85
    elif unrealized_pct > 50 and daily_change > 5:
        return 80  # Trim winner
    elif unrealized_pct > 100 and daily_change > 3:
        return 90  # Strong trim signal
    
    return 50 + (daily_change * 3)  # Moderate moves

def calculate_signal_fusion_score(ticker, plays, signals):
    """Score based on AI harness signals."""
    # Check plays
    for play in plays:
        if play.get('ticker') == ticker:
            confidence = play.get('confidence', 50)
            return min(100, confidence)
    
    # Check signals
    ticker_signals = signals.get(ticker, {})
    composite = ticker_signals.get('composite_score', 50)
    return composite

def calculate_social_sentiment_score(ticker, social):
    """Score based on social sentiment alignment."""
    sentiment = social.get(ticker, {})
    bullish = sentiment.get('bullish', 0)
    bearish = sentiment.get('bearish', 0)
    total = bullish + bearish
    
    if total < 5:
        return 50  # Not enough data
    
    ratio = bullish / total if total > 0 else 0.5
    
    # Extreme sentiment is actionable
    if ratio >= 0.8:
        return 85  # Very bullish
    elif ratio <= 0.2:
        return 85  # Very bearish (contrarian or confirm)
    elif ratio >= 0.7:
        return 70
    elif ratio <= 0.3:
        return 70
    
    return 50

def calculate_earnings_proximity_score(ticker, brief):
    """Score based on earnings proximity."""
    earnings = brief.get('earnings_calendar', [])
    for e in earnings:
        if e.get('ticker') == ticker:
            days = e.get('days_to_earnings', 999)
            if days <= 2:
                return 95  # Very close
            elif days <= 5:
                return 80
            elif days <= 7:
                return 65
            return 50
    return 50

def calculate_technical_score(ticker, brief):
    """Score based on technical indicators."""
    market_data = brief.get('market_data', {})
    data = market_data.get(ticker, {})
    
    rsi = data.get('rsi', 50)
    
    # RSI extremes
    if rsi >= 75:
        return 85  # Overbought → trim
    elif rsi <= 25:
        return 85  # Oversold → potential buy
    elif rsi >= 70:
        return 70
    elif rsi <= 30:
        return 70
    
    return 50

def calculate_portfolio_risk_score(ticker, portfolio):
    """Score based on portfolio risk factors."""
    positions = portfolio.get('positions', [])
    total_value = portfolio.get('total_value', 1)
    
    pos = next((p for p in positions if p.get('ticker') == ticker), None)
    if not pos:
        return 50
    
    value = pos.get('market_value', 0)
    pct = (value / total_value * 100) if total_value > 0 else 0
    
    # Concentration risk
    if pct > 15:
        return 90  # Too concentrated
    elif pct > 10:
        return 75
    elif pct > 8:
        return 60
    
    return 50

def calculate_macro_alignment_score(ticker, brief):
    """Score based on macro regime fit."""
    regime = brief.get('market_regime', {})
    regime_type = regime.get('regime', 'neutral')
    
    # Simple scoring based on regime
    if regime_type == 'bullish':
        return 60  # Slightly favor action in bull markets
    elif regime_type == 'bearish':
        return 70  # More action needed in bear markets (defensive)
    
    return 50

# ─── ACTION GENERATOR ────────────────────────────────────────────────

def generate_action(ticker, scores, portfolio, plays, grades):
    """Generate a specific action recommendation."""
    positions = portfolio.get('positions', [])
    pos = next((p for p in positions if p.get('ticker') == ticker), None)
    
    grade = grades.get(ticker, {}).get('grade', 50)
    
    # Find matching play
    play = next((p for p in plays if p.get('ticker') == ticker), None)
    
    # Determine action type
    action_type = 'HOLD'
    urgency = 'LOW'
    
    # Grade-based rules
    if grade < 40:
        action_type = 'SELL'
        urgency = 'HIGH'
    elif grade < 50:
        action_type = 'SELL'
        urgency = 'MEDIUM'
    elif grade < 55:
        action_type = 'REVIEW'
        urgency = 'MEDIUM'
    elif grade >= 75 and pos:
        action_type = 'ADD'
        urgency = 'LOW'
    elif grade >= 70 and not pos:
        action_type = 'BUY'
        urgency = 'LOW'
    
    # Price move overrides
    price_score = scores.get('price_move', 50)
    if price_score >= 90:
        if pos and pos.get('unrealized_pnl_pct', 0) < -20:
            action_type = 'SELL'
            urgency = 'HIGH'
        elif pos and pos.get('unrealized_pnl_pct', 0) > 100:
            action_type = 'TRIM'
            urgency = 'MEDIUM'
    
    # Portfolio risk overrides
    risk_score = scores.get('portfolio_risk', 50)
    if risk_score >= 90:
        action_type = 'TRIM'
        urgency = 'HIGH'
    
    # Earnings proximity
    earnings_score = scores.get('earnings_proximity', 50)
    if earnings_score >= 90 and pos:
        action_type = 'REVIEW'
        urgency = 'HIGH'
    
    # Override with AI play if high confidence
    if play and play.get('confidence', 0) >= 80:
        play_action = play.get('action', 'HOLD')
        if play_action in ['BUY', 'SELL', 'TRIM', 'ADD']:
            action_type = play_action
            urgency = 'HIGH' if play.get('confidence', 0) >= 90 else 'MEDIUM'
    
    return {
        'type': action_type,
        'urgency': urgency,
        'grade': grade,
    }

def calculate_total_score(scores):
    """Calculate weighted total score."""
    total = 0
    for key, weight in WEIGHTS.items():
        total += scores.get(key, 50) * weight
    return round(total, 1)

# ─── MAIN DIGEST GENERATOR ───────────────────────────────────────────

def generate_digest(date_str=None):
    """Generate the daily digest."""
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    print(f"🧠 VOX Daily Digest — {date_str}")
    print("=" * 60)
    
    # Load all data
    portfolio = load_portfolio()
    grades = load_grades()
    plays = load_plays()
    brief = load_brief()
    social = load_social()
    signals = load_signals()
    history = load_history()
    
    if not portfolio:
        print("❌ No portfolio data found")
        return None
    
    # Get all tickers from portfolio + plays + watchlist
    all_tickers = set()
    for pos in portfolio.get('positions', []):
        all_tickers.add(pos.get('ticker'))
    for play in plays:
        all_tickers.add(play.get('ticker'))
    
    all_tickers = [t for t in all_tickers if t]
    
    print(f"📊 Processing {len(all_tickers)} tickers...")
    
    # Score each ticker
    scored_actions = []
    
    for ticker in all_tickers:
        if not ticker:
            continue
        
        scores = {
            'grade_change': calculate_grade_change_score(ticker, grades, history),
            'price_move': calculate_price_move_score(ticker, portfolio, brief),
            'signal_fusion': calculate_signal_fusion_score(ticker, plays, signals),
            'social_sentiment': calculate_social_sentiment_score(ticker, social),
            'earnings_proximity': calculate_earnings_proximity_score(ticker, brief),
            'technical': calculate_technical_score(ticker, brief),
            'portfolio_risk': calculate_portfolio_risk_score(ticker, portfolio),
            'macro_alignment': calculate_macro_alignment_score(ticker, brief),
        }
        
        total_score = calculate_total_score(scores)
        action = generate_action(ticker, scores, portfolio, plays, grades)
        
        # Only include actionable items
        if action['type'] != 'HOLD' and total_score >= MIN_ACTION_SCORE:
            scored_actions.append({
                'ticker': ticker,
                'score': total_score,
                'action': action['type'],
                'urgency': action['urgency'],
                'grade': action['grade'],
                'scores': scores,
            })
    
    # Sort by score descending
    scored_actions.sort(key=lambda x: x['score'], reverse=True)
    
    # Take top N
    top_actions = scored_actions[:MAX_DAILY_ACTIONS]
    
    # Categorize
    winners = [a for a in top_actions if a['action'] in ['ADD', 'BUY']]
    losers = [a for a in top_actions if a['action'] in ['SELL', 'TRIM']]
    reviews = [a for a in top_actions if a['action'] == 'REVIEW']
    
    # Generate digest
    digest = {
        'date': date_str,
        'generated_at': datetime.now().isoformat(),
        'market_regime': brief.get('market_regime', {}),
        'summary': {
            'total_tickers_scanned': len(all_tickers),
            'actions_generated': len(scored_actions),
            'actions_selected': len(top_actions),
            'winners': len(winners),
            'losers': len(losers),
            'reviews': len(reviews),
        },
        'winners': winners,
        'losers': losers,
        'reviews': reviews,
        'all_scored': scored_actions[:20],  # Top 20 for reference
        'portfolio_snapshot': {
            'total_value': portfolio.get('total_value', 0),
            'total_positions': len(portfolio.get('positions', [])),
        },
        'key_insights': generate_insights(scored_actions, portfolio, brief),
    }
    
    return digest

def generate_insights(scored_actions, portfolio, brief):
    """Generate key insights from the digest."""
    insights = []
    
    # Portfolio health
    total_value = portfolio.get('total_value', 0)
    positions = portfolio.get('positions', [])
    
    if total_value > 0:
        # Check concentration
        values = [p.get('market_value', 0) for p in positions]
        if values:
            max_pos = max(values)
            max_pct = (max_pos / total_value) * 100
            if max_pct > 15:
                insights.append(f"⚠️  Concentration risk: largest position is {max_pct:.1f}% of portfolio")
            
            # Check cash
            cash = portfolio.get('cash', 0)
            cash_pct = (cash / total_value) * 100
            if cash_pct < 5:
                insights.append(f"💰 Low cash: {cash_pct:.1f}% — consider raising cash before new buys")
            elif cash_pct > 30:
                insights.append(f"💰 High cash: {cash_pct:.1f}% — opportunity to deploy capital")
    
    # Market regime insight
    regime = brief.get('market_regime', {})
    regime_type = regime.get('regime', 'neutral')
    if regime_type == 'bearish':
        insights.append("🐻 Bear market regime — prioritize defense, raise cash, cut losers")
    elif regime_type == 'bullish':
        insights.append("🐂 Bull market regime — favor growth, add to winners")
    
    # Action urgency
    high_urgency = [a for a in scored_actions if a.get('urgency') == 'HIGH']
    if high_urgency:
        insights.append(f"🚨 {len(high_urgency)} HIGH urgency actions requiring immediate attention")
    
    # Grade distribution
    grades = [a.get('grade', 50) for a in scored_actions]
    if grades:
        avg_grade = statistics.mean(grades)
        if avg_grade < 55:
            insights.append(f"📉 Portfolio grade average {avg_grade:.1f} — broad review needed")
        elif avg_grade > 70:
            insights.append(f"📈 Portfolio grade average {avg_grade:.1f} — strong positioning")
    
    return insights

# ─── OUTPUT GENERATORS ───────────────────────────────────────────────

def save_digest_json(digest, output_path):
    """Save digest as JSON."""
    with open(output_path, 'w') as f:
        json.dump(digest, f, indent=2)
    print(f"💾 Digest saved: {output_path}")

def generate_markdown_summary(digest):
    """Generate markdown summary for Obsidian vault."""
    date = digest['date']
    summary = digest['summary']
    
    md = f"""# 🧠 VOX Daily Digest — {date}

**Generated:** {digest['generated_at']}
**Market Regime:** {digest['market_regime'].get('regime', 'neutral').upper()}

## 📊 Portfolio Snapshot
- **Total Value:** ${digest['portfolio_snapshot']['total_value']:,.2f}
- **Positions:** {digest['portfolio_snapshot']['total_positions']}
- **Tickers Scanned:** {summary['total_tickers_scanned']}

## 🎯 Today's Verdict
| Metric | Count |
|--------|-------|
| Actions Generated | {summary['actions_generated']} |
| **Actions Selected** | **{summary['actions_selected']}** |
| Winners (BUY/ADD) | {summary['winners']} |
| Losers (SELL/TRIM) | {summary['losers']} |
| Reviews Needed | {summary['reviews']} |

## 🔑 Key Insights
"""
    
    for insight in digest['key_insights']:
        md += f"- {inspect}\n"
    
    # Winners section
    if digest['winners']:
        md += "\n## 🟢 WINNERS — Add/Buy\n\n"
        for i, w in enumerate(digest['winners'], 1):
            md += f"### {i}. **{w['ticker']}** — Score: {w['score']}\n"
            md += f"- **Action:** {w['action']} | **Urgency:** {w['urgency']}\n"
            md += f"- **Grade:** {w['grade']}/100\n"
            md += f"- **Signal Breakdown:**\n"
            for sig, val in w['scores'].items():
                md += f"  - {sig}: {val}\n"
            md += "\n"
    
    # Losers section
    if digest['losers']:
        md += "\n## 🔴 LOSERS — Sell/Trim\n\n"
        for i, l in enumerate(digest['losers'], 1):
            md += f"### {i}. **{l['ticker']}** — Score: {l['score']}\n"
            md += f"- **Action:** {l['action']} | **Urgency:** {l['urgency']}\n"
            md += f"- **Grade:** {l['grade']}/100\n"
            md += f"- **Signal Breakdown:**\n"
            for sig, val in l['scores'].items():
                md += f"  - {sig}: {val}\n"
            md += "\n"
    
    # Reviews section
    if digest['reviews']:
        md += "\n## 🟡 REVIEWS — Check Thesis\n\n"
        for i, r in enumerate(digest['reviews'], 1):
            md += f"### {i}. **{r['ticker']}** — Score: {r['score']}\n"
            md += f"- **Grade:** {r['grade']}/100 | **Urgency:** {r['urgency']}\n\n"
    
    # All scored reference
    md += "\n## 📋 All Scored Actions (Top 20)\n\n"
    md += "| Rank | Ticker | Action | Score | Urgency | Grade |\n"
    md += "|------|--------|--------|-------|---------|-------|\n"
    for i, a in enumerate(digest['all_scored'][:20], 1):
        md += f"| {i} | {a['ticker']} | {a['action']} | {a['score']} | {a['urgency']} | {a['grade']} |\n"
    
    md += "\n---\n*Generated by VOX Daily Digest System v9.2*\n"
    
    return md

def save_markdown(digest, vault_path):
    """Save markdown to Obsidian vault."""
    md = generate_markdown_summary(digest)
    date = digest['date']
    
    # Ensure directory exists
    daily_dir = Path(vault_path) / '06-Tracking' / 'Daily'
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = daily_dir / f'Digest — {date}.md'
    with open(file_path, 'w') as f:
        f.write(md)
    
    print(f"📝 Markdown saved: {file_path}")
    return file_path

def send_telegram_digest(digest):
    """Send top 3 actions via Telegram."""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    if not bot_token or not chat_id:
        print("⚠️  Telegram credentials not found")
        return False
    
    # Build message
    date = digest['date']
    all_actions = digest['winners'] + digest['losers'] + digest['reviews']
    top3 = all_actions[:3]
    
    message = f"🧠 *VOX Daily Digest — {date}*\n"
    message += f"Regime: {digest['market_regime'].get('regime', 'neutral').upper()}\n"
    message += f"Actions: {digest['summary']['actions_selected']}\n\n"
    
    for i, action in enumerate(top3, 1):
        emoji = "🟢" if action['action'] in ['BUY', 'ADD'] else "🔴" if action['action'] in ['SELL', 'TRIM'] else "🟡"
        message += f"{emoji} *{action['ticker']}* — {action['action']}\n"
        message += f"   Score: {action['score']} | Grade: {action['grade']}\n"
        message += f"   Urgency: {action['urgency']}\n\n"
    
    if len(all_actions) > 3:
        message += f"_+{len(all_actions) - 3} more actions in full digest_\n"
    
    # Send
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
        print("📱 Telegram digest sent")
        return True
    except Exception as e:
        print(f"❌ Telegram failed: {e}")
        return False

# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='VOX Daily Digest System')
    parser.add_argument('--date', help='Date for digest (YYYY-MM-DD)')
    parser.add_argument('--output', default='vox_daily_digest.json', help='Output JSON file')
    parser.add_argument('--vault', default='~/Documents/Obsidian Vault/Portfolio-Finance', help='Obsidian vault path')
    parser.add_argument('--send-telegram', action='store_true', help='Send top 3 actions via Telegram')
    parser.add_argument('--markdown-only', action='store_true', help='Only generate markdown')
    
    args = parser.parse_args()
    
    # Generate digest
    digest = generate_digest(args.date)
    
    if not digest:
        sys.exit(1)
    
    # Save JSON
    output_path = SCRIPT_DIR / args.output
    save_digest_json(digest, output_path)
    
    # Save markdown to vault
    vault_path = os.path.expanduser(args.vault)
    md_path = save_markdown(digest, vault_path)
    
    # Send Telegram if requested
    if args.send_telegram:
        send_telegram_digest(digest)
    
    # Print summary
    print("\n" + "=" * 60)
    print("🎯 DAILY DIGEST COMPLETE")
    print("=" * 60)
    print(f"📊 Scanned: {digest['summary']['total_tickers_scanned']} tickers")
    print(f"✅ Actions: {digest['summary']['actions_selected']} (from {digest['summary']['actions_generated']} generated)")
    print(f"🟢 Winners: {digest['summary']['winners']}")
    print(f"🔴 Losers: {digest['summary']['losers']}")
    print(f"🟡 Reviews: {digest['summary']['reviews']}")
    print(f"\n💾 JSON: {output_path}")
    print(f"📝 Markdown: {md_path}")
    
    # Print top actions
    all_actions = digest['winners'] + digest['losers'] + digest['reviews']
    if all_actions:
        print("\n🏆 TOP ACTIONS:")
        for i, a in enumerate(all_actions[:5], 1):
            emoji = "🟢" if a['action'] in ['BUY', 'ADD'] else "🔴" if a['action'] in ['SELL', 'TRIM'] else "🟡"
            print(f"   {i}. {emoji} {a['ticker']}: {a['action']} (Score: {a['score']}, Grade: {a['grade']})")

if __name__ == '__main__':
    main()
