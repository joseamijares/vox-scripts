#!/bin/bash
# Load environment variables from Hermes .env
set -a
source "$HOME/.hermes/.env"
set +a

cd "$HOME/.hermes/scripts" && python3 vox_supply_chain_agent.py
