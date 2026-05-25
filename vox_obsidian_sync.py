#!/usr/bin/env python3
"""
VOX Obsidian Sync v1.0
Two-way sync between dashboard data and Obsidian vault

Features:
- Export portfolio positions to vault notes
- Export grades to position notes
- Export plays to vault plays folder
- Import vault theses into dashboard
- Sync daily

Usage:
    python3 vox_obsidian_sync.py --export-all
    python3 vox_obsidian_sync.py --export-positions
    python3 vox_obsidian_sync.py --export-plays
    python3 vox_obsidian_sync.py --import-theses
"""

import os
import sys
import json
import argparse
from datetime import datetime

VAULT_PATH = os.path.expanduser("~/Documents/Obsidian Vault/Portfolio-Finance")
SCRIPTS_DIR = os.path.expanduser("~/.hermes/scripts")


def load_json(filename):
    filepath = os.path.join(SCRIPTS_DIR, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def export_positions():
    """Export portfolio positions to Obsidian vault notes"""
    positions = load_json("dashboard_positions.json")
    if not positions:
        print("No positions found")
        return
    
    if isinstance(positions, dict):
        positions = positions.get("positions", [])
    
    # Group by ticker
    by_ticker = {}
    for p in positions:
        ticker = p.get("ticker", "UNKNOWN")
        if ticker not in by_ticker:
            by_ticker[ticker] = []
        by_ticker[ticker].append(p)
    
    # Export each position to vault
    positions_dir = os.path.join(VAULT_PATH, "02-Portfolio/Stocks/Positions")
    crypto_dir = os.path.join(VAULT_PATH, "02-Portfolio/Crypto/Positions")
    ensure_dir(positions_dir)
    ensure_dir(crypto_dir)
    
    count = 0
    for ticker, pos_list in by_ticker.items():
        # Determine if crypto
        is_crypto = any(p.get("asset_type") == "crypto" or p.get("broker") == "Binance" for p in pos_list)
        target_dir = crypto_dir if is_crypto else positions_dir
        
        # Calculate totals
        total_shares = sum(p.get("shares", 0) for p in pos_list)
        total_value = sum(p.get("value", 0) for p in pos_list)
        avg_price = total_value / total_shares if total_shares > 0 else 0
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in pos_list)
        
        # Build note content
        content = f"""---
ticker: {ticker}
updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
type: position
brokers: {', '.join(set(p.get('broker', 'Unknown') for p in pos_list))}
---

# {ticker} Position

## Holdings
| Broker | Shares | Price | Value | P&L |
|--------|--------|-------|-------|-----|
"""
        for p in pos_list:
            content += f"| {p.get('broker', 'N/A')} | {p.get('shares', 0):,.0f} | ${p.get('price', 0):,.2f} | ${p.get('value', 0):,.2f} | ${p.get('unrealized_pnl', 0):,.2f} |\n"
        
        content += f"""
## Summary
- **Total Shares:** {total_shares:,.0f}
- **Avg Price:** ${avg_price:,.2f}
- **Total Value:** ${total_value:,.2f}
- **Unrealized P&L:** ${total_pnl:,.2f}

## Dashboard
[Open in VOX](https://vox-dashboard-five.vercel.app)
"""
        
        filepath = os.path.join(target_dir, f"{ticker}.md")
        with open(filepath, 'w') as f:
            f.write(content)
        count += 1
    
    print(f"Exported {count} position notes to vault")


def export_grades():
    """Export grades to position notes (append to existing)"""
    grades = load_json("portfolio_grades.json")
    if not grades:
        print("No grades found")
        return
    
    if isinstance(grades, list):
        grades = {g.get("ticker", "UNKNOWN"): g for g in grades}
    
    positions_dir = os.path.join(VAULT_PATH, "02-Portfolio/Stocks/Positions")
    crypto_dir = os.path.join(VAULT_PATH, "02-Portfolio/Crypto/Positions")
    
    count = 0
    for ticker, grade_data in grades.items():
        # Find the note
        for dir_path in [positions_dir, crypto_dir]:
            filepath = os.path.join(dir_path, f"{ticker}.md")
            if os.path.exists(filepath):
                with open(filepath) as f:
                    content = f.read()
                
                # Remove old grade section if exists
                if "## Grade" in content:
                    content = content.split("## Grade")[0].rstrip() + "\n"
                
                # Append grade
                grade = grade_data.get("grade", 0)
                action = "BUY" if grade >= 70 else "HOLD" if grade >= 45 else "SELL"
                content += f"""
## Grade
- **Score:** {grade}/100
- **Action:** {action}
- **Updated:** {datetime.now().strftime('%Y-%m-%d')}

{grade_data.get('rationale', 'No rationale provided.')}
"""
                with open(filepath, 'w') as f:
                    f.write(content)
                count += 1
                break
    
    print(f"Updated {count} position notes with grades")


def export_plays():
    """Export generated plays to vault plays folder"""
    plays = load_json("vox_generated_plays.json")
    if not plays:
        print("No plays found")
        return
    
    if not isinstance(plays, list):
        print("Invalid plays format")
        return
    
    plays_dir = os.path.join(VAULT_PATH, "05-Plays")
    ensure_dir(plays_dir)
    
    # Create daily plays note
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"{date_str}-AI-Plays.md"
    filepath = os.path.join(plays_dir, filename)
    
    content = f"""---
date: {date_str}
type: ai-plays
source: vox-autonomous-agent
---

# AI Generated Plays — {date_str}

"""
    
    for play in plays[:20]:  # Top 20
        emoji = {"BUY": "🟢", "SELL": "🔴", "TRIM": "🟡", "HOLD": "⚪"}.get(play.get("type"), "⚪")
        content += f"""## {emoji} {play.get('ticker', '?')} — {play.get('type', '?')}

- **Confidence:** {play.get('confidence', 0):.0f}%
- **Conviction:** {play.get('conviction', 'SPEC')}
- **Thesis:** {play.get('thesis', 'No thesis')}

"""
        if play.get("entry_price"):
            content += f"- **Entry:** ${play['entry_price']:.2f}\n"
        if play.get("stop_loss"):
            content += f"- **Stop:** ${play['stop_loss']:.2f}\n"
        if play.get("target_price"):
            content += f"- **Target:** ${play['target_price']:.2f}\n"
        
        content += f"- **Signals:** {', '.join(play.get('source_signals', []))}\n\n"
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"Exported {len(plays)} plays to {filepath}")


def import_theses():
    """Import theses from vault into dashboard data"""
    thesis_dir = os.path.join(VAULT_PATH, "07-Analysis/Thesis")
    if not os.path.exists(thesis_dir):
        print("No thesis directory found")
        return
    
    theses = []
    for filename in os.listdir(thesis_dir):
        if filename.endswith(".md"):
            filepath = os.path.join(thesis_dir, filename)
            with open(filepath) as f:
                content = f.read()
            
            # Extract ticker from filename or content
            ticker = filename.replace(" Thesis.md", "").replace(".md", "")
            
            theses.append({
                "ticker": ticker,
                "title": filename.replace(".md", ""),
                "content": content[:2000],  # First 2000 chars
                "source": "obsidian",
                "updated": datetime.now().isoformat()
            })
    
    # Save to dashboard data
    output_file = os.path.join(SCRIPTS_DIR, "vox_vault_theses.json")
    with open(output_file, 'w') as f:
        json.dump(theses, f, indent=2)
    
    print(f"Imported {len(theses)} theses from vault")


def sync_all():
    """Run full sync"""
    print("=== VOX Obsidian Sync ===\n")
    export_positions()
    export_grades()
    export_plays()
    import_theses()
    print("\n=== Sync Complete ===")


def main():
    parser = argparse.ArgumentParser(description="VOX Obsidian Sync")
    parser.add_argument("--export-all", action="store_true", help="Export everything")
    parser.add_argument("--export-positions", action="store_true", help="Export positions")
    parser.add_argument("--export-grades", action="store_true", help="Export grades")
    parser.add_argument("--export-plays", action="store_true", help="Export plays")
    parser.add_argument("--import-theses", action="store_true", help="Import theses")
    
    args = parser.parse_args()
    
    if args.export_positions:
        export_positions()
    elif args.export_grades:
        export_grades()
    elif args.export_plays:
        export_plays()
    elif args.import_theses:
        import_theses()
    else:
        sync_all()


if __name__ == "__main__":
    main()
