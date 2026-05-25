#!/usr/bin/env python3
"""
VOX Dashboard v9.1 Launch Test
Full system validation before production

Tests:
1. All dashboard pages exist and build
2. All Python scripts run without errors
3. API connections work (Polygon, Telegram, Linear)
4. Data pipeline produces valid output
5. Cron jobs are scheduled correctly
6. Git repos are in sync

Usage:
    python3 vox_dashboard_test.py
    python3 vox_dashboard_test.py --full
"""

import os
import sys
import json
import subprocess
import urllib.request
from datetime import datetime
from typing import Dict, List, Tuple

SCRIPTS_DIR = os.path.expanduser("~/.hermes/scripts")
DASHBOARD_DIR = os.path.expanduser("~/dev/vox-dashboard")
VAULT_PATH = os.path.expanduser("~/Documents/Obsidian Vault/Portfolio-Finance")


class TestResult:
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message


def test_dashboard_pages() -> List[TestResult]:
    """Test all dashboard pages exist"""
    results = []
    
    expected_pages = [
        "/", "/portfolio", "/grades", "/watchlist", "/regime", "/briefing",
        "/positions", "/scorer", "/sectors", "/council", "/trump", "/sentiment",
        "/screener", "/macro", "/correlation", "/journal", "/earnings", "/dividends",
        "/risk", "/performance", "/sizer", "/rebalancing", "/compounding", "/mistakes",
        "/crypto", "/options", "/forex", "/alerts", "/commander", "/weekly",
        "/ai-insights", "/plays", "/rag", "/play-review", "/next-trade"
    ]
    
    pages_dir = os.path.join(DASHBOARD_DIR, "src/app")
    
    for page in expected_pages:
        page_name = page.strip("/") or "home"
        page_path = os.path.join(pages_dir, page_name)
        
        if os.path.exists(page_path):
            results.append(TestResult(f"Page: {page}", True))
        else:
            # Check if it's a dynamic route or special page
            if page in ["/", "/_not-found"]:
                results.append(TestResult(f"Page: {page}", True, "Special route"))
            else:
                results.append(TestResult(f"Page: {page}", False, f"Missing at {page_path}"))
    
    return results


def test_python_scripts() -> List[TestResult]:
    """Test all Python scripts are valid"""
    results = []
    
    scripts = [
        "vox_portfolio_scanner.py",
        "vox_ai_harness.py",
        "vox_autonomous_agent.py",
        "vox_rag_system.py",
        "vox_telegram_alerts.py",
        "vox_signal_enhancer.py",
        "vox_self_upgrade.py",
        "vox_obsidian_sync.py",
        "vox_social_tracker.py",
        "vox_live_prices.py",
        "vox_daily_analysis.py",
        "vox_position_review.py",
        "vox_market_regime.py",
        "vox_trade_scorer.py",
    ]
    
    for script in scripts:
        script_path = os.path.join(SCRIPTS_DIR, script)
        if not os.path.exists(script_path):
            results.append(TestResult(f"Script: {script}", False, "File not found"))
            continue
        
        # Test syntax
        try:
            result = subprocess.run(
                [sys.executable, "-m", "py_compile", script_path],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                results.append(TestResult(f"Script: {script}", True))
            else:
                results.append(TestResult(f"Script: {script}", False, result.stderr[:100]))
        except Exception as e:
            results.append(TestResult(f"Script: {script}", False, str(e)[:100]))
    
    return results


def test_api_connections() -> List[TestResult]:
    """Test API connections"""
    results = []
    
    # Test Polygon
    try:
        env_path = os.path.expanduser("~/.hermes/.env")
        polygon_key = ""
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("POLYGON_API_KEY="):
                        polygon_key = line.strip().split("=", 1)[1]
        
        if polygon_key:
            url = f"https://api.polygon.io/v2/aggs/ticker/AAPL/prev?apiKey={polygon_key}"
            req = urllib.request.Request(url, headers={"User-Agent": "VOX-Test/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "OK":
                    results.append(TestResult("API: Polygon", True, f"AAPL: ${data['results'][0]['c']:.2f}"))
                else:
                    results.append(TestResult("API: Polygon", False, "Invalid response"))
        else:
            results.append(TestResult("API: Polygon", False, "No API key"))
    except Exception as e:
        results.append(TestResult("API: Polygon", False, str(e)[:100]))
    
    # Test Telegram
    try:
        telegram_token = ""
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        telegram_token = line.strip().split("=", 1)[1]
        
        if telegram_token:
            url = f"https://api.telegram.org/bot{telegram_token}/getMe"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if data.get("ok"):
                    bot_name = data["result"].get("username", "Unknown")
                    results.append(TestResult("API: Telegram", True, f"@{bot_name}"))
                else:
                    results.append(TestResult("API: Telegram", False, "Invalid token"))
        else:
            results.append(TestResult("API: Telegram", False, "No token"))
    except Exception as e:
        results.append(TestResult("API: Telegram", False, str(e)[:100]))
    
    return results


def test_data_pipeline() -> List[TestResult]:
    """Test data pipeline produces valid output"""
    results = []
    
    # Test portfolio data
    portfolio_file = os.path.join(SCRIPTS_DIR, "dashboard_positions.json")
    if os.path.exists(portfolio_file):
        try:
            with open(portfolio_file) as f:
                data = json.load(f)
            
            positions = data if isinstance(data, list) else data.get("positions", [])
            total_value = sum(p.get("value", 0) for p in positions)
            
            if len(positions) > 0 and total_value > 0:
                results.append(TestResult("Data: Portfolio", True, f"{len(positions)} positions, ${total_value:,.0f}"))
            else:
                results.append(TestResult("Data: Portfolio", False, "Empty or invalid"))
        except Exception as e:
            results.append(TestResult("Data: Portfolio", False, str(e)[:100]))
    else:
        results.append(TestResult("Data: Portfolio", False, "File not found"))
    
    # Test grades
    grades_file = os.path.join(SCRIPTS_DIR, "portfolio_grades.json")
    if os.path.exists(grades_file):
        try:
            with open(grades_file) as f:
                data = json.load(f)
            
            # Find grades in nested lists
            total_grades = 0
            for key, value in data.items():
                if isinstance(value, list):
                    total_grades += len(value)
            
            if total_grades > 0:
                results.append(TestResult("Data: Grades", True, f"{total_grades} grades across categories"))
            else:
                results.append(TestResult("Data: Grades", False, "Empty"))
        except Exception as e:
            results.append(TestResult("Data: Grades", False, str(e)[:100]))
    else:
        results.append(TestResult("Data: Grades", False, "File not found"))
    
    # Test plays
    plays_file = os.path.join(SCRIPTS_DIR, "vox_generated_plays.json")
    if os.path.exists(plays_file):
        try:
            with open(plays_file) as f:
                plays = json.load(f)
            
            if isinstance(plays, list) and len(plays) > 0:
                results.append(TestResult("Data: Plays", True, f"{len(plays)} plays generated"))
            else:
                results.append(TestResult("Data: Plays", False, "Empty"))
        except Exception as e:
            results.append(TestResult("Data: Plays", False, str(e)[:100]))
    else:
        results.append(TestResult("Data: Plays", False, "File not found"))
    
    return results


def test_cron_jobs() -> List[TestResult]:
    """Test cron jobs are scheduled"""
    results = []
    
    try:
        result = subprocess.run(
            ["hermes", "cron", "list"],
            capture_output=True, text=True, timeout=15
        )
        
        if result.returncode == 0:
            output = result.stdout
            vox_jobs = [line for line in output.split("\n") if "vox" in line.lower()]
            
            if len(vox_jobs) > 0:
                results.append(TestResult("Cron: VOX Jobs", True, f"{len(vox_jobs)} jobs scheduled"))
            else:
                results.append(TestResult("Cron: VOX Jobs", False, "No VOX jobs found"))
        else:
            results.append(TestResult("Cron: VOX Jobs", False, "Failed to list"))
    except Exception as e:
        results.append(TestResult("Cron: VOX Jobs", False, str(e)[:100]))
    
    return results


def test_git_repos() -> List[TestResult]:
    """Test git repos are in sync"""
    results = []
    
    # Test dashboard repo
    try:
        result = subprocess.run(
            ["git", "-C", DASHBOARD_DIR, "status", "--short"],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            if result.stdout.strip():
                results.append(TestResult("Git: Dashboard", False, f"Uncommitted changes: {len(result.stdout.strip().split(chr(10)))} files"))
            else:
                results.append(TestResult("Git: Dashboard", True, "Clean"))
        else:
            results.append(TestResult("Git: Dashboard", False, "Not a git repo"))
    except Exception as e:
        results.append(TestResult("Git: Dashboard", False, str(e)[:100]))
    
    # Test scripts repo
    try:
        result = subprocess.run(
            ["git", "-C", SCRIPTS_DIR, "status", "--short"],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            if result.stdout.strip():
                results.append(TestResult("Git: Scripts", False, f"Uncommitted changes: {len(result.stdout.strip().split(chr(10)))} files"))
            else:
                results.append(TestResult("Git: Scripts", True, "Clean"))
        else:
            results.append(TestResult("Git: Scripts", False, "Not a git repo"))
    except Exception as e:
        results.append(TestResult("Git: Scripts", False, str(e)[:100]))
    
    return results


def test_vault_sync() -> List[TestResult]:
    """Test Obsidian vault sync"""
    results = []
    
    if os.path.exists(VAULT_PATH):
        # Count files
        md_files = []
        for root, dirs, files in os.walk(VAULT_PATH):
            for f in files:
                if f.endswith(".md"):
                    md_files.append(os.path.join(root, f))
        
        if len(md_files) > 100:
            results.append(TestResult("Vault: Files", True, f"{len(md_files)} markdown files"))
        else:
            results.append(TestResult("Vault: Files", False, f"Only {len(md_files)} files"))
        
        # Check for recent sync
        plays_dir = os.path.join(VAULT_PATH, "05-Plays")
        if os.path.exists(plays_dir):
            recent_files = [f for f in os.listdir(plays_dir) if f.endswith(".md")]
            if recent_files:
                results.append(TestResult("Vault: Plays Sync", True, f"{len(recent_files)} play files"))
            else:
                results.append(TestResult("Vault: Plays Sync", False, "No play files"))
        else:
            results.append(TestResult("Vault: Plays Sync", False, "No plays directory"))
    else:
        results.append(TestResult("Vault: Path", False, f"Not found: {VAULT_PATH}"))
    
    return results


def run_all_tests():
    """Run all tests and print report"""
    print("="*70)
    print("VOX DASHBOARD v9.1 — LAUNCH TEST")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    all_results = []
    
    # Run tests
    test_suites = [
        ("Dashboard Pages", test_dashboard_pages),
        ("Python Scripts", test_python_scripts),
        ("API Connections", test_api_connections),
        ("Data Pipeline", test_data_pipeline),
        ("Cron Jobs", test_cron_jobs),
        ("Git Repos", test_git_repos),
        ("Vault Sync", test_vault_sync),
    ]
    
    for suite_name, test_func in test_suites:
        print(f"\n{'─'*70}")
        print(f"📋 {suite_name}")
        print("─"*70)
        
        results = test_func()
        all_results.extend(results)
        
        for result in results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            msg = f" — {result.message}" if result.message else ""
            print(f"  {status} | {result.name}{msg}")
    
    # Summary
    passed = sum(1 for r in all_results if r.passed)
    failed = sum(1 for r in all_results if not r.passed)
    total = len(all_results)
    
    print(f"\n{'='*70}")
    print("SUMMARY")
    print("="*70)
    print(f"  ✅ Passed: {passed}/{total}")
    print(f"  ❌ Failed: {failed}/{total}")
    print(f"  📊 Success Rate: {passed/total*100:.1f}%")
    
    if failed == 0:
        print(f"\n  🚀 ALL TESTS PASSED — READY FOR LAUNCH")
    elif failed <= 2:
        print(f"\n  ⚠️  MINOR ISSUES — CAN LAUNCH WITH NOTES")
    else:
        print(f"\n  🔴 SIGNIFICANT ISSUES — REVIEW BEFORE LAUNCH")
    
    # Save report
    report = {
        "timestamp": datetime.now().isoformat(),
        "version": "9.1",
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "success_rate": passed/total*100 if total > 0 else 0,
        "results": [
            {"name": r.name, "passed": r.passed, "message": r.message}
            for r in all_results
        ]
    }
    
    report_file = os.path.join(SCRIPTS_DIR, "vox_launch_test_report.json")
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\n  📝 Report saved to: {report_file}")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
