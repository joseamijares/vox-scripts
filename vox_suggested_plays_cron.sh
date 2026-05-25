#!/bin/bash
# Vox Suggested Plays — Runs M-F 6:00 PM ET
# Run screener → grade top setups → LLM Council → push to Suggested Plays

cd ~/.hermes/scripts

echo "⚡ Vox Suggested Plays — $(date)"
echo "================================"

python3 vox_suggested_plays.py 2>/dev/null || echo "  ⚠️ Pipeline failed"

echo "✅ Suggested plays done — $(date)"
