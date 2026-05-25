#!/usr/bin/env python3
"""
VOX DASHBOARD GENERATOR v3
Generates a professional HTML trading dashboard from Google Sheets data.
Handles decorative headers, multi-section layouts, and emoji dividers.

Usage:
    python3 vox_dashboard.py
    python3 vox_dashboard.py --serve  # opens in browser

Output: ~/.hermes/scripts/vox_dashboard/index.html
"""

import os, sys, json, subprocess, re
from datetime import datetime
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────
DASHBOARD_SHEET_ID = "1Ft6dRv7AtO-s5KLFi2pF-JYxrE0Tj9_hII8rT0qk0bw"
ARCHIVE_SHEET_ID   = "1ViLAYMGzHnR60T8TnuoOyiUYx7NDZEHj2op_ZeYqwpA"
OUTPUT_DIR = Path.home() / ".hermes" / "scripts" / "vox_dashboard"
COMPOSIO_PATH = os.path.expanduser("~/.composio")
API_KEY = os.environ.get("COMPOSIO_API_KEY", "uak_zwBd4-GiasWKW7yedRYW")

# ── Colors ──────────────────────────────────────────────────────────
BG = "#0a0e1a"
CARD = "#111827"
CARD_BORDER = "#1f2937"
TEXT = "#e5e7eb"
TEXT_MUTED = "#9ca3af"
ACCENT = "#3b82f6"
GREEN = "#10b981"
RED = "#ef4444"
YELLOW = "#f59e0b"
PURPLE = "#8b5cf6"
PINK = "#ec4899"
CYAN = "#06b6d4"

# ── Composio Helpers ────────────────────────────────────────────────
def run_composio_cmd(args):
    env = os.environ.copy()
    env["PATH"] = f"{COMPOSIO_PATH}:{env.get('PATH', '')}"
    env["COMPOSIO_API_KEY"] = API_KEY
    cmd = ["composio"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    stderr_clean = re.sub(r'\x1b\[[0-9;]*m', '', stderr)
    if result.returncode == 0:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"output": stdout}
    else:
        try:
            return json.loads(stdout) if stdout else {"error": stderr_clean, "returncode": result.returncode}
        except json.JSONDecodeError:
            return {"error": stderr_clean, "returncode": result.returncode}

def get_sheet_batch(sheet_id, ranges):
    result = run_composio_cmd([
        "execute", "GOOGLESHEETS_BATCH_GET",
        "-d", json.dumps({"spreadsheet_id": sheet_id, "ranges": ranges})
    ])
    if isinstance(result, dict) and result.get("successful"):
        data = result.get("data", {})
        if "valueRanges" in data:
            return data["valueRanges"]
    if isinstance(result, dict) and "valueRanges" in result:
        return result["valueRanges"]
    return []

def extract_values(value_range):
    if isinstance(value_range, dict):
        return value_range.get("values", [])
    return []

# ── Smart Table Parser ──────────────────────────────────────────────
def is_header_row(row):
    """Detect if a row is a table header — must have ALL typical header traits."""
    if not row or len(row) < 2:
        return False
    # Headers typically have short, clean text in every cell
    # and don't have numeric values as first cell
    first = str(row[0]).strip()
    # Skip if first cell looks like data (ticker symbol, number, emoji header)
    if not first or first.startswith('📊') or first.startswith('🎯') or first.startswith('🧠') or first.startswith('🇺🇸') or first.startswith('⚖️'):
        return False
    if first.isupper() and len(first) <= 4 and first.isalpha():  # Looks like a ticker
        return False
    try:
        float(first.replace('$', '').replace(',', ''))  # Looks like a number
        return False
    except:
        pass
    
    header_keywords = ['ticker', 'grade', 'action', 'price', 'rsi', 'broker', 'value', 'size', 'symbol', 'name', 'date', 'return', 'change', 'entry', 'stop', 'target', 'fundamental', 'technical', 'sentiment', 'risk', 'contrarian', 'consensus', 'text', 'impact', 'sectors', 'asset_class']
    row_text = ' '.join([str(c).lower() for c in row if c])
    score = sum(1 for kw in header_keywords if kw in row_text)
    # Need at least 2 header keywords to be a real header row
    return score >= 2

def is_data_row(row):
    if not row or not row[0]:
        return False
    first = str(row[0]).strip()
    if first.startswith('━') or first.startswith('─') or first.startswith('═'):
        return False
    if first.startswith('🔴') or first.startswith('🟡') or first.startswith('🟠') or first.startswith('🟢'):
        return False
    if first.startswith('THRESHOLD') or first.startswith('NOTE:'):
        return False
    if 'PLAY #' in first or 'STATUS:' in first:
        return False
    return True

def parse_smart_table(values):
    if not values or len(values) < 2:
        return []
    headers_list = []
    for i, row in enumerate(values):
        if is_header_row(row):
            headers_list.append((i, [str(c).strip().lower().replace(" ", "_").replace("#", "num") for c in row]))
    if not headers_list:
        return []
    all_rows = []
    for idx, (header_idx, headers) in enumerate(headers_list):
        end_idx = headers_list[idx + 1][0] if idx + 1 < len(headers_list) else len(values)
        for row in values[header_idx + 1:end_idx]:
            if is_data_row(row):
                item = {}
                for i, h in enumerate(headers):
                    item[h] = row[i] if i < len(row) else ""
                all_rows.append(item)
    return all_rows

def parse_portfolio_snapshot(values):
    result = {}
    for row in values:
        if len(row) >= 2 and row[0] and not str(row[0]).startswith('━'):
            key = str(row[0]).strip().lower().replace(":", "").replace(" ", "_").replace("🎯", "").replace("📊", "").replace("━", "").replace("🔮", "")
            if key and not key.startswith('last_updated') and not key.startswith('portfolio:'):
                result[key] = row[1]
    return result

def parse_broker_rows(values):
    if not values:
        return []
    header_idx = None
    for i, row in enumerate(values):
        if row and len(row) >= 2:
            first = str(row[0]).strip().lower()
            if "broker" in first or "date" in first:
                header_idx = i
                break
    if header_idx is None:
        return []
    headers = [str(h).strip().lower().replace(" ", "_") for h in values[header_idx]]
    rows = []
    for row in values[header_idx + 1:]:
        if not row or not row[0] or str(row[0]).startswith('━') or str(row[0]).startswith('TOTAL') or str(row[0]).startswith('TARGET'):
            continue
        item = {}
        for i, h in enumerate(headers):
            item[h] = row[i] if i < len(row) else ""
        rows.append(item)
    return rows

# ── SVG Chart Generation ────────────────────────────────────────────
def sparkline(data, width=220, height=45, color=GREEN):
    if not data or len(data) < 2:
        return ""
    try:
        nums = [float(x) for x in data]
    except:
        return ""
    if not nums:
        return ""
    min_val, max_val = min(nums), max(nums)
    if max_val == min_val:
        max_val = min_val + 1
    points = []
    for i, val in enumerate(nums):
        x = (i / max(len(nums) - 1, 1)) * width
        y = height - ((val - min_val) / (max_val - min_val)) * (height - 4) - 2
        points.append("{:.1f},{:.1f}".format(x, y))
    path_d = "M" + points[0] + "".join([" L" + p for p in points[1:]])
    return '<svg width="{}" height="{}" viewBox="0 0 {} {}"><path d="{}" fill="none" stroke="{}" stroke-width="2" stroke-linecap="round"/></svg>'.format(width, height, width, height, path_d, color)

def donut_chart(values, colors, size=140):
    if not values or sum(values) == 0:
        return ""
    total = sum(values)
    gradient_stops = []
    current_pct = 0
    for val, color in zip(values, colors):
        pct = (val / total) * 100
        gradient_stops.append("{} {:.1f}% {:.1f}%".format(color, current_pct, current_pct + pct))
        current_pct += pct
    gradient = ", ".join(gradient_stops)
    inner_size = int(size * 0.6)
    return '<div style="width:{}px;height:{}px;border-radius:50%;background:conic-gradient({});position:relative;"><div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:{}px;height:{}px;border-radius:50%;background:{};"></div></div>'.format(size, size, gradient, inner_size, inner_size, CARD)

def bar_chart(bars, labels, colors, height=120):
    if not bars:
        return ""
    max_val = max(bars) if bars else 1
    html = '<div style="display:flex;flex-direction:column;gap:8px;">'
    for val, label, color in zip(bars, labels, colors):
        pct = (val / max_val) * 100 if max_val > 0 else 0
        html += '<div style="display:flex;align-items:center;gap:10px;"><span style="width:80px;font-size:11px;color:{};text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{}</span><div style="flex:1;background:{};border-radius:4px;height:20px;overflow:hidden;"><div style="width:{:.1f}%;height:100%;background:{};border-radius:4px;"></div></div><span style="width:60px;font-size:11px;font-weight:500;text-align:right;">${:,.0f}</span></div>'.format(TEXT_MUTED, label, CARD_BORDER, pct, color, val)
    html += '</div>'
    return html

# ── HTML Generation ─────────────────────────────────────────────────
def generate_dashboard(data):
    portfolio_raw = parse_portfolio_snapshot(data.get("portfolio", []))
    active_plays = parse_smart_table(data.get("active_plays", []))
    grades = parse_smart_table(data.get("grades", []))
    council = parse_smart_table(data.get("council", []))
    trump = parse_smart_table(data.get("trump", []))
    snapshots = parse_smart_table(data.get("snapshots", []))
    brokers = parse_broker_rows(data.get("brokers", []))
    allocations = parse_smart_table(data.get("allocations", []))
    
    total_aum = portfolio_raw.get("total_aum", "$196,072")
    health_score = portfolio_raw.get("portfolio_health_score", "38/100")
    ytd_return = portfolio_raw.get("ytd_return", "N/A")
    usd_mxn = portfolio_raw.get("usd/mxn", "17.31")
    
    aum_history = []
    for snap in snapshots:
        val = snap.get("total_aum", snap.get("portfolio_value", "")).replace("$", "").replace(",", "")
        try:
            aum_history.append(float(val))
        except:
            pass
    aum_sparkline = sparkline(aum_history, width=220, height=45, color=GREEN)
    
    broker_names, broker_values = [], []
    broker_colors = [ACCENT, GREEN, PURPLE, YELLOW, PINK, CYAN, RED]
    for b in brokers:
        name = b.get("broker", b.get("name", "")).strip()
        val_str = b.get("value_usd", b.get("balance", b.get("value", "0"))).replace("$", "").replace(",", "")
        try:
            val = float(val_str)
            if val > 100 and name and not name.lower().startswith("total"):
                broker_names.append(name)
                broker_values.append(val)
        except:
            pass
    
    broker_donut = donut_chart(broker_values, broker_colors[:len(broker_values)], size=140) if broker_values else ""
    broker_bars = bar_chart(broker_values, broker_names, broker_colors[:len(broker_values)], height=120) if broker_values else ""
    
    alloc_names, alloc_values = [], []
    for a in allocations:
        name = a.get("asset_class", a.get("category", a.get("asset", ""))).strip()
        if not name:
            name = a.get("date", "").strip()  # Fallback
        pct_str = a.get("%_total", a.get("allocation", a.get("percentage", "0"))).replace("%", "")
        try:
            pct = float(pct_str)
            if pct > 0 and name:
                alloc_names.append(name)
                alloc_values.append(pct)
        except:
            pass
    alloc_donut = donut_chart(alloc_values, broker_colors[:len(alloc_values)], size=120) if alloc_values else ""
    
    # Active plays
    plays_html = ""
    for play in active_plays[:12]:
        ticker = play.get("ticker", play.get("symbol", "?"))
        action = play.get("action", play.get("trade", "HOLD"))
        size = play.get("position_size", play.get("size", play.get("shares", "?")))
        entry = play.get("entry", play.get("entry_price", play.get("price", "?")))
        stop = play.get("stop_loss", play.get("stop", "?"))
        target = play.get("target", play.get("target_price", "?"))
        
        action_class = "badge-hold"
        if "BUY" in action.upper():
            action_class = "badge-buy"
        elif "SELL" in action.upper():
            action_class = "badge-sell"
        elif "TRIM" in action.upper():
            action_class = "badge-hold"
        
        plays_html += '<tr><td class="ticker">{}</td><td><span class="badge {}">{}</span></td><td class="num">{}</td><td class="num">{}</td><td class="num" style="color:{}">{}</td><td class="num">{}</td></tr>'.format(ticker, action_class, action, size, entry, RED, stop, target)
    
    # Grades
    grades_html = ""
    for g in grades[:12]:
        ticker = g.get("ticker", g.get("symbol", "?"))
        grade_val = g.get("grade", g.get("score", "?"))
        signal = g.get("signal", g.get("recommendation", g.get("rec", "HOLD")))
        rsi = g.get("rsi", "?")
        trend = g.get("trend", g.get("trend_direction", "?"))
        
        signal_class = "badge-hold"
        if "BUY" in signal.upper():
            signal_class = "badge-buy"
        elif "SELL" in signal.upper() or "AVOID" in signal.upper():
            signal_class = "badge-sell"
        
        try:
            grade_num = float(str(grade_val).replace("/100", ""))
            grade_color = GREEN if grade_num >= 70 else YELLOW if grade_num >= 55 else RED
        except:
            grade_color = TEXT
        
        grades_html += '<tr><td class="ticker">{}</td><td class="num" style="color:{};font-weight:700">{}</td><td><span class="badge {}">{}</span></td><td class="num">{}</td><td class="num">{}</td></tr>'.format(ticker, grade_color, grade_val, signal_class, signal, rsi, trend)
    
    # Council
    council_html = ""
    for c in council[:6]:
        ticker = c.get("ticker", c.get("symbol", "?"))
        vote = c.get("vote", c.get("consensus", "NEUTRAL"))
        confidence = c.get("confidence", "?")
        vote_color = GREEN if "BULL" in vote.upper() else RED if "BEAR" in vote.upper() else TEXT_MUTED
        council_html += '<tr><td class="ticker">{}</td><td style="color:{};font-weight:600">{}</td><td class="num">{}</td></tr>'.format(ticker, vote_color, vote, confidence)
    
    # Trump
    trump_html = ""
    for t in trump[:5]:
        event = t.get("event", t.get("tweet", t.get("headline", "")))
        impact = t.get("impact", t.get("severity", "?"))
        sector = t.get("sector", t.get("tickers", "?"))
        impact_color = RED if "HIGH" in impact.upper() else YELLOW if "MED" in impact.upper() else TEXT_MUTED
        trump_html += '<tr><td style="font-size:12px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{}</td><td style="color:{};font-weight:600">{}</td><td>{}</td></tr>'.format(event, impact_color, impact, sector)
    
    # Position sizer
    position_html = ""
    for p in parse_smart_table(data.get("position_sizer", []))[:6]:
        ticker = p.get("ticker", p.get("symbol", "?"))
        size = p.get("size", p.get("position_size", "?"))
        risk = p.get("risk", p.get("risk_pct", "?"))
        position_html += '<tr><td class="ticker">{}</td><td class="num">{}</td><td class="num">{}</td></tr>'.format(ticker, size, risk)
    
    # Broker rows
    broker_rows = ""
    for b in brokers[:8]:
        name = b.get("broker", b.get("name", "?")).strip()
        balance = b.get("value_usd", b.get("balance", b.get("value", "?")))
        if name and not name.lower().startswith("total"):
            broker_rows += '<div class="broker-row"><span style="color:{}">{}</span><span style="font-weight:500">{}</span></div>'.format(TEXT_MUTED, name, balance)
    
    health_num = health_score.split('/')[0] if '/' in health_score else '38'
    
    # Allocation rows
    alloc_rows = ""
    for n, v in zip(alloc_names, alloc_values):
        alloc_rows += '<div class="broker-row"><span style="color:{}">{}</span><span style="font-weight:700">{:.1f}%</span></div>'.format(TEXT_MUTED, n, v)
    
    now_str = datetime.now().strftime("%b %d, %Y at %H:%M")
    year_str = datetime.now().strftime("%Y")
    
    html = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VOX Dashboard — ''' + datetime.now().strftime("%b %d, %Y") + '''</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: ''' + BG + ''';
            color: ''' + TEXT + ''';
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            font-size: 13px;
            line-height: 1.5;
            min-height: 100vh;
        }
        .header {
            background: ''' + CARD + ''';
            border-bottom: 1px solid ''' + CARD_BORDER + ''';
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .header h1 {
            font-size: 20px;
            font-weight: 800;
            background: linear-gradient(90deg, ''' + ACCENT + ''', ''' + PURPLE + ''');
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .header .timestamp {
            color: ''' + TEXT_MUTED + ''';
            font-size: 12px;
        }
        .container {
            max-width: 1440px;
            margin: 0 auto;
            padding: 20px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 16px;
            margin-bottom: 16px;
        }
        .grid-2 { grid-template-columns: repeat(2, 1fr); }
        .grid-4 { grid-template-columns: repeat(4, 1fr); }
        @media (max-width: 1200px) { .grid-4 { grid-template-columns: repeat(2, 1fr); } }
        @media (max-width: 768px) {
            .grid, .grid-2, .grid-4 { grid-template-columns: 1fr; }
            .header { flex-direction: column; gap: 8px; align-items: flex-start; }
        }
        .card {
            background: ''' + CARD + ''';
            border: 1px solid ''' + CARD_BORDER + ''';
            border-radius: 12px;
            padding: 20px;
            overflow: hidden;
        }
        .card h2 {
            font-size: 12px;
            font-weight: 700;
            color: ''' + TEXT_MUTED + ''';
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .metric {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .metric .value {
            font-size: 32px;
            font-weight: 800;
            color: ''' + TEXT + ''';
            letter-spacing: -0.5px;
        }
        .metric .label {
            font-size: 12px;
            color: ''' + TEXT_MUTED + ''';
            font-weight: 500;
        }
        .metric .change {
            font-size: 13px;
            font-weight: 600;
            margin-top: 4px;
        }
        .positive { color: ''' + GREEN + '''; }
        .negative { color: ''' + RED + '''; }
        .neutral { color: ''' + YELLOW + '''; }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }
        th {
            text-align: left;
            padding: 8px 10px;
            color: ''' + TEXT_MUTED + ''';
            font-weight: 600;
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            border-bottom: 1px solid ''' + CARD_BORDER + ''';
            white-space: nowrap;
        }
        td {
            padding: 8px 10px;
            border-bottom: 1px solid ''' + CARD_BORDER + ''';
            vertical-align: middle;
        }
        tr:hover td { background: rgba(59, 130, 246, 0.05); }
        .ticker {
            font-weight: 700;
            font-size: 13px;
            color: ''' + TEXT + ''';
        }
        .num {
            text-align: right;
            font-variant-numeric: tabular-nums;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 12px;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.3px;
        }
        .badge-buy { background: rgba(16, 185, 129, 0.15); color: ''' + GREEN + '''; }
        .badge-sell { background: rgba(239, 68, 68, 0.15); color: ''' + RED + '''; }
        .badge-hold { background: rgba(245, 158, 11, 0.15); color: ''' + YELLOW + '''; }
        .sparkline-wrap {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-top: 8px;
        }
        .broker-row {
            display: flex;
            justify-content: space-between;
            padding: 7px 0;
            border-bottom: 1px solid ''' + CARD_BORDER + ''';
            font-size: 13px;
        }
        .broker-row:last-child { border-bottom: none; }
        .empty-state {
            padding: 30px;
            text-align: center;
            color: ''' + TEXT_MUTED + ''';
            font-size: 13px;
        }
        .health-bar {
            width: 100%;
            height: 6px;
            background: ''' + CARD_BORDER + ''';
            border-radius: 3px;
            margin-top: 8px;
            overflow: hidden;
        }
        .health-fill {
            height: 100%;
            border-radius: 3px;
            background: linear-gradient(90deg, ''' + RED + ''', ''' + YELLOW + ''', ''' + GREEN + ''');
        }
        .footer {
            text-align: center;
            padding: 24px;
            color: ''' + TEXT_MUTED + ''';
            font-size: 11px;
            letter-spacing: 0.3px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔮 VOX Dashboard</h1>
        <span class="timestamp">Last updated: ''' + now_str + ''' · USD/MXN: ''' + usd_mxn + '''</span>
    </div>
    
    <div class="container">
        <!-- KPI Row -->
        <div class="grid grid-4">
            <div class="card">
                <div class="metric">
                    <span class="label">Total AUM</span>
                    <span class="value">''' + total_aum + '''</span>
                    <div class="sparkline-wrap">''' + aum_sparkline + '''</div>
                </div>
            </div>
            <div class="card">
                <div class="metric">
                    <span class="label">Portfolio Health</span>
                    <span class="value" style="color: ''' + YELLOW + '''">''' + health_score + '''</span>
                    <div class="health-bar"><div class="health-fill" style="width: ''' + health_num + '''%"></div></div>
                    <span class="change neutral">Needs attention</span>
                </div>
            </div>
            <div class="card">
                <div class="metric">
                    <span class="label">YTD Return</span>
                    <span class="value">''' + ytd_return + '''</span>
                    <span class="change neutral">Target: 20%</span>
                </div>
            </div>
            <div class="card">
                <div class="metric">
                    <span class="label">Active Positions</span>
                    <span class="value">''' + str(len(active_plays)) + '''</span>
                    <span class="change">Across ''' + str(len(brokers)) + ''' brokers</span>
                </div>
            </div>
        </div>
        
        <!-- Charts Row -->
        <div class="grid grid-2">
            <div class="card">
                <h2>🏦 Broker Breakdown</h2>
                <div style="display:flex;align-items:center;gap:24px;">
                    ''' + broker_donut + '''
                    <div style="flex:1;min-width:200px;">''' + broker_bars + '''</div>
                </div>
            </div>
            <div class="card">
                <h2>📊 Asset Allocation</h2>
                <div style="display:flex;align-items:center;gap:24px;">
                    ''' + alloc_donut + '''
                    <div style="flex:1;">''' + alloc_rows + '''</div>
                </div>
            </div>
        </div>
        
        <!-- Active Plays -->
        <div class="grid">
            <div class="card" style="grid-column: 1 / -1;">
                <h2>🎯 Active Plays</h2>
                <table>
                    <thead>
                        <tr><th>Ticker</th><th>Action</th><th style="text-align:right">Size</th><th style="text-align:right">Entry</th><th style="text-align:right">Stop</th><th style="text-align:right">Target</th></tr>
                    </thead>
                    <tbody>
                        ''' + (plays_html if plays_html else '<tr><td colspan="6" class="empty-state">No active plays</td></tr>') + '''
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Grades + Council -->
        <div class="grid grid-2">
            <div class="card">
                <h2>📈 Fresh Grades</h2>
                <table>
                    <thead>
                        <tr><th>Ticker</th><th style="text-align:center">Grade</th><th style="text-align:center">Signal</th><th style="text-align:center">RSI</th><th style="text-align:center">Trend</th></tr>
                    </thead>
                    <tbody>
                        ''' + (grades_html if grades_html else '<tr><td colspan="5" class="empty-state">No grades available</td></tr>') + '''
                    </tbody>
                </table>
            </div>
            <div class="card">
                <h2>🧠 LLM Council</h2>
                <table>
                    <thead>
                        <tr><th>Ticker</th><th style="text-align:center">Consensus</th><th style="text-align:center">Confidence</th></tr>
                    </thead>
                    <tbody>
                        ''' + (council_html if council_html else '<tr><td colspan="3" class="empty-state">No council votes</td></tr>') + '''
                    </tbody>
                </table>
                <h2 style="margin-top:20px">⚖️ Position Sizer</h2>
                <table>
                    <thead>
                        <tr><th>Ticker</th><th style="text-align:right">Size</th><th style="text-align:right">Risk %</th></tr>
                    </thead>
                    <tbody>
                        ''' + (position_html if position_html else '<tr><td colspan="3" class="empty-state">No positions sized</td></tr>') + '''
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Trump Tracker -->
        <div class="grid">
            <div class="card" style="grid-column: 1 / -1;">
                <h2>🇺🇸 Trump Tracker</h2>
                <table>
                    <thead>
                        <tr><th>Event</th><th style="text-align:center">Impact</th><th>Sector/Tickers</th></tr>
                    </thead>
                    <tbody>
                        ''' + (trump_html if trump_html else '<tr><td colspan="3" class="empty-state">No high-impact events</td></tr>') + '''
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            🔮 VOX Dashboard · Generated ''' + year_str + ''' · Data from Google Sheets · <a href="https://docs.google.com/spreadsheets/d/''' + DASHBOARD_SHEET_ID + '''" style="color:''' + ACCENT + ''';text-decoration:none;">Open Dashboard Sheet</a>
        </div>
    </div>
</body>
</html>'''
    
    return html

# ── Main ────────────────────────────────────────────────────────────
def main():
    print("🔮 VOX Dashboard Generator v3")
    print("=" * 50)
    
    dashboard_ranges = [
        "'📊 Portfolio Snapshot'!A1:Z30",
        "'🎯 Active Plays'!A1:Z50",
        "'📈 Fresh Grades'!A1:Z30",
        "'🧠 LLM Council'!A1:Z30",
        "'🇺🇸 Trump Tracker'!A1:Z30",
        "'⚖️ Position Sizer'!A1:Z30",
    ]
    archive_ranges = [
        "'📅 Weekly Snapshots'!A1:Z50",
        "'🏦 Broker Breakdown'!A1:Z30",
        "'📊 Asset Allocation'!A1:Z30",
    ]
    
    print("📊 Fetching Dashboard data...")
    dashboard_vr = get_sheet_batch(DASHBOARD_SHEET_ID, dashboard_ranges)
    print("📈 Fetching Archive data...")
    archive_vr = get_sheet_batch(ARCHIVE_SHEET_ID, archive_ranges)
    
    data = {
        "portfolio": extract_values(dashboard_vr[0]) if len(dashboard_vr) > 0 else [],
        "active_plays": extract_values(dashboard_vr[1]) if len(dashboard_vr) > 1 else [],
        "grades": extract_values(dashboard_vr[2]) if len(dashboard_vr) > 2 else [],
        "council": extract_values(dashboard_vr[3]) if len(dashboard_vr) > 3 else [],
        "trump": extract_values(dashboard_vr[4]) if len(dashboard_vr) > 4 else [],
        "position_sizer": extract_values(dashboard_vr[5]) if len(dashboard_vr) > 5 else [],
        "snapshots": extract_values(archive_vr[0]) if len(archive_vr) > 0 else [],
        "brokers": extract_values(archive_vr[1]) if len(archive_vr) > 1 else [],
        "allocations": extract_values(archive_vr[2]) if len(archive_vr) > 2 else [],
    }
    
    print("🎨 Generating dashboard HTML...")
    html = generate_dashboard(data)
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "index.html"
    with open(output_path, "w") as f:
        f.write(html)
    
    print("✅ Dashboard saved: {}".format(output_path))
    print("📊 Data loaded: {} rows".format(sum(len(v) for v in data.values())))
    
    if "--serve" in sys.argv or "--open" in sys.argv:
        import webbrowser
        webbrowser.open("file://{}".format(output_path))
        print("🌐 Opened in browser")
    
    return output_path

if __name__ == "__main__":
    main()
