#!/bin/bash
# Run Trump Tracker every 30 minutes during market hours (9:30-16:00 ET)
# Also runs at 8:00 ET for pre-market intel

cd /Users/jos/.hermes/scripts
export X_BEARER_TOKEN="AAAAAAAAAAAAAAAAAAAAAPoP9wEAAAAAQs5zVwSKSZjyrA4fKlYGeHCYu2E%3Dmi6CkKomg33cR2xn2gjW3ftDuKTb6D964if5Apw1taQJdWhbdA"

# Load other env vars
if [ -f /Users/jos/.hermes/.env ]; then
    set -a
    source /Users/jos/.hermes/.env
    set +a
fi

python3 trump_tracker.py
