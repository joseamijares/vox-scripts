#!/bin/bash
# One-shot: reload launchd Hermes service so new config is picked up.
# Invoked by a short-lived no_agent cron, not from inside the gateway child tree.
set -euo pipefail
LOG="${HOME}/.hermes/logs/config-reload-bounce.log"
mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "=== START $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
UID_NUM=$(id -u)
LABEL="gui/${UID_NUM}/ai.hermes.gateway"
# Prefer hermes CLI when PATH is complete; fall back to launchctl
export PATH="${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:${PATH}"
if command -v hermes >/dev/null 2>&1; then
  # Use launchctl kickstart so the supervised job recycles cleanly
  launchctl kickstart -k "$LABEL" || hermes gateway start || true
else
  launchctl kickstart -k "$LABEL" || true
fi
sleep 4
if command -v hermes >/dev/null 2>&1; then
  hermes gateway status || true
fi
launchctl print "$LABEL" 2>&1 | head -40 || true
# mark done for Linear/update consumers
echo ok > "${HOME}/.hermes/cache/config-reload-bounce.ok"
echo "=== DONE $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
