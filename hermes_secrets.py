#!/usr/bin/env python3
"""Lightweight secrets helper: reads from 1Password Vox Hermes vault first,
falls back to environment variables, then to ~/.hermes/.env.
Import from any VOX script with:
    sys.path.insert(0, str(Path.home() / '.hermes' / 'scripts'))
    from hermes_secrets import get_env
"""
import os
import re
import subprocess
from pathlib import Path

HERMES_HOME = Path.home() / ".hermes"
ENV_PATH = HERMES_HOME / ".env"
TOKEN_PATH = HERMES_HOME / "secrets" / "1password_service_account"
VAULT = "Vox Hermes"


# Load service account token once at import time
if TOKEN_PATH.exists() and "OP_SERVICE_ACCOUNT_TOKEN" not in os.environ:
    try:
        with open(TOKEN_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                    os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1]
                    break
    except Exception:
        pass


# Parse .env once
_ENV_CACHE = None

def _load_env():
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    _ENV_CACHE = {}
    if ENV_PATH.exists():
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'")
                # Strip inline comments
                if " #" in v:
                    v = v.split(" #", 1)[0].strip()
                _ENV_CACHE[k.strip()] = v
    return _ENV_CACHE


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


def _looks_secret(key: str, value: str) -> bool:
    if not value:
        return False
    if value.lower() in {"true", "false"}:
        return False
    if re.match(r"^[0-9]+$", value):
        return False
    if value.startswith("http://") or value.startswith("https://"):
        return False
    if len(value) < 8:
        return False
    return any(kw in key.upper() for kw in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "BEARER"))


def get_env(key: str, default=None):
    """Get a secret/config value, trying 1Password, then env, then .env."""
    # 1. Environment variable already loaded
    if key in os.environ:
        return os.environ[key]

    # 2. 1Password
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") and _looks_secret(key, "x"):
        try:
            result = subprocess.run(
                ["op", "item", "get", key, "--vault", VAULT, "--field", _field_name(key), "--reveal"],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    # 3. .env fallback
    env = _load_env()
    if key in env:
        return env[key]

    return default


if __name__ == "__main__":
    # Simple test
    print("OpenRouter present:", bool(get_env("OPENROUTER_API_KEY")))
    print("DB password present:", bool(get_env("DB_PASSWORD")))
