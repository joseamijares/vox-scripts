#!/bin/bash
# VOX Smart Alerts v5 — Event-driven, not schedule-driven
# Only alerts when something CHANGED or REQUIRES ACTION

cd /Users/jos/.hermes/scripts

# Update live prices first (needed for stop-loss and price-hit alerts)
python3 vox_live_prices.py --update 2>/dev/null

# Run smart alert system v8 (LLM-enhanced)
python3 vox_smart_alerts_v8.py
