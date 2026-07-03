#!/usr/bin/env python3
"""Bootstrap module: loads missing secrets into os.environ from 1Password first,
local .env second. Import once at the top of any script/cron that expects
traditional os.environ.get(...) calls to work.

Usage:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
    import hermes_secrets_bootstrap
"""
import os
import subprocess
from pathlib import Path

VAULT = "Vox Hermes"
TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "1password_service_account"
ENV_PATH = Path.home() / ".hermes" / ".env"

# Set OP_SERVICE_ACCOUNT_TOKEN from the restricted local file if not already set
if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") and TOKEN_PATH.exists():
    try:
        with open(TOKEN_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                    os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1]
                    break
    except Exception:
        pass

# Secrets that were migrated to 1Password and/or .env
KNOWN_SECRETS = [
    "OPENROUTER_API_KEY", "DB_PASSWORD", "PGPASSWORD",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_WEBHOOK_SECRET",
    "FMP_API_KEY", "POLYGON_API_KEY", "FINNHUB_API_KEY",
    "EXA_API_KEY", "TAVILY_API_KEY", "PERPLEXITY_API_KEY",
    "ALPACA_API_KEY", "ALPACA_SECRET_KEY",
    "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "BITSO_API_KEY", "BITSO_API_SECRET",
    "LINEAR_API_KEY", "X_BEARER_TOKEN",
    "ETORO_API_KEY", "ETORO_USER_KEY",
    "KIMI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY",
    "FIRECRAWL_API_KEY", "GROQ_API_KEY", "NOVITA_API_KEY",
    "HF_TOKEN", "SLACK_BOT_TOKEN", "SLACK_APP_TOKEN",
    "EMAIL_PASSWORD", "GITHUB_TOKEN",
]


def _field_name(key: str) -> str:
    kl = key.upper()
    if "API_KEY" in kl:
        return "api_key"
    if "SECRET" in kl:
        return "secret"
    if "TOKEN" in kl:
        return "token"
    if "PASSWORD" in kl:
        return "password"
    return "credential"


# Quick 1Password health check: if `op` cannot respond within 3 seconds, disable
# 1Password lookups entirely to avoid 30+ second hangs per key.
_1PASSWORD_AVAILABLE = False
if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
    try:
        _op_check = subprocess.run(
            ["op", "whoami"], capture_output=True, text=True, timeout=3
        )
        _1PASSWORD_AVAILABLE = _op_check.returncode == 0
    except Exception:
        _1PASSWORD_AVAILABLE = False


def _load_from_1password(key: str):
    if not _1PASSWORD_AVAILABLE:
        return None
    try:
        result = subprocess.run(
            ["op", "item", "get", key, "--vault", VAULT, "--field", _field_name(key), "--reveal"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _load_from_env_file(key: str):
    if not ENV_PATH.exists():
        return None
    try:
        with open(ENV_PATH) as f:
            for line in f:
                raw = line.strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                k, v = raw.split("=", 1)
                k = k.strip()
                if k == key:
                    val = v.strip().strip('"').strip("'")
                    # Strip inline comments
                    if " #" in val:
                        val = val.split(" #", 1)[0].strip()
                    return val
    except Exception:
        pass
    return None


# Populate os.environ with missing secrets.
# Local .env is tried first because 1Password CLI has been hanging/failing
# in this environment; this keeps VOX cron jobs alive without 30s timeouts.
for _key in KNOWN_SECRETS:
    if os.environ.get(_key):
        continue
    _val = _load_from_env_file(_key)
    if _val:
        os.environ[_key] = _val
        continue
    _val = _load_from_1password(_key)
    if _val:
        os.environ[_key] = _val


if __name__ == "__main__":
    for k in KNOWN_SECRETS:
        print(f"{k}: {'set' if os.environ.get(k) else 'NOT SET'}")
