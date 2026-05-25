#!/bin/bash
# Vox Alert System — runs every 30 min during market hours

cd /Users/jos/.hermes/scripts

# Load env
if [ -f /Users/jos/.hermes/.env ]; then
    set -a
    source /Users/jos/.hermes/.env
    set +a
fi

python3 vox_alert_system.py
