#!/bin/bash
# Generic wrapper to run VOX scripts with 1Password secrets injected.
# Usage: op_run_vox.sh <python-script-relative-to-scripts-dir> [args...]
set -euo pipefail

SCRIPT_DIR="/Users/jos/.hermes/scripts"
ENV_FILE="/Users/jos/.hermes/.env.op-refs"
SA_FILE="$HOME/.hermes/secrets/1password_service_account"

# Extract token without sourcing the whole file in bash (avoid $ interpolation)
_extract_token() {
  python3 -c "
import pathlib
p = pathlib.Path.home() / '.hermes' / 'secrets' / '1password_service_account'
if p.exists():
    for line in p.read_text().splitlines():
        line = line.strip()
        if line.startswith('OP_SERVICE_ACCOUNT_TOKEN='):
            print(line.split('=', 1)[1])
"
}

# If a service account token exists, validate it before exporting. If invalid,
# fall back to desktop app integration (Touch ID / password).
if [[ -f "$SA_FILE" ]]; then
  TOKEN="$(_extract_token)"
  if [[ -n "$TOKEN" ]]; then
    if OP_SERVICE_ACCOUNT_TOKEN="$TOKEN" op whoami >/dev/null 2>&1; then
      export OP_SERVICE_ACCOUNT_TOKEN="$TOKEN"
    else
      echo "[WARN] 1Password service account token invalid; falling back to desktop app integration" >&2
    fi
  fi
fi

cd "$SCRIPT_DIR"

if [[ $# -lt 1 ]]; then
  echo "Usage: op_run_vox.sh <python-script> [args...]"
  exit 1
fi

PY_SCRIPT="$1"
shift

exec op run --env-file "$ENV_FILE" -- python3 "$PY_SCRIPT" "$@"
