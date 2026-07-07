#!/usr/bin/env python3
"""Wrapper for vox-market-news-brief cron (no arguments allowed in Hermes script field)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from vox_market_news_brief import main as brief_main

if __name__ == "__main__":
    sys.argv = ["vox_market_news_brief.py", "--run", "--model", "deepseek/deepseek-v4-flash"]
    sys.exit(brief_main())
