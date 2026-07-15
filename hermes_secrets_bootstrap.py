#!/usr/bin/env python3
"""Bootstrap secrets: 1Password FIRST, local .env only as emergency fallback.

Usage (top of every VOX/cron script):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
    import hermes_secrets_bootstrap

Env flags:
  HERMES_SECRETS_SOURCE=1password|env|auto   (default auto = 1P then env)
  HERMES_SECRETS_NO_ENV=1                   refuse .env fallback entirely
  OP_SERVICE_ACCOUNT_TOKEN                  or file ~/.hermes/secrets/1password_service_account
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

VAULT = os.environ.get("HERMES_OP_VAULT", "Vox Hermes")
TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "1password_service_account"
ENV_PATH = Path.home() / ".hermes" / ".env"
OP_TIMEOUT = float(os.environ.get("HERMES_OP_TIMEOUT", "6"))

# Prefer service-account token (non-interactive) over desktop biometric unlock
if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") and TOKEN_PATH.exists():
    try:
        for line in TOKEN_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip()
                break
    except Exception:
        pass

# Avoid desktop biometric hangs when service account is present
if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
    os.environ.setdefault("OP_BIOMETRIC_UNLOCK_TIMEOUT", "1")

KNOWN_SECRETS = [
    "OPENROUTER_API_KEY",
    "DB_PASSWORD",
    "PGPASSWORD",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "FMP_API_KEY",
    "POLYGON_API_KEY",
    "FINNHUB_API_KEY",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
    "PERPLEXITY_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "BINANCE_API_KEY",
    "BINANCE_API_SECRET",
    "BITSO_API_KEY",
    "BITSO_API_SECRET",
    "LINEAR_API_KEY",
    "X_BEARER_TOKEN",
    "ETORO_API_KEY",
    "ETORO_USER_KEY",
    "KIMI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "FIRECRAWL_API_KEY",
    "GROQ_API_KEY",
    "NOVITA_API_KEY",
    "HF_TOKEN",
    "SLACK_BOT_TOKEN",
    "SLACK_APP_TOKEN",
    "EMAIL_PASSWORD",
    "GITHUB_TOKEN",
    "XAI_API_KEY",
    "RAILWAY_TOKEN",
    "RAILWAY_API_TOKEN",
]


def _field_name(key: str) -> str:
    kl = key.upper()
    if "PASSWORD" in kl:
        return "password"
    if "SECRET" in kl and "KEY" in kl:
        return "secret"
    if "SECRET" in kl:
        return "secret"
    if "TOKEN" in kl:
        return "token"
    if "API_KEY" in kl or kl.endswith("_KEY"):
        return "credential"
    if kl in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"):
        return "credential"
    return "credential"


def _op_env() -> dict:
    env = os.environ.copy()
    if env.get("OP_SERVICE_ACCOUNT_TOKEN"):
        # Isolate from desktop integration hangs where possible
        env.setdefault("OP_BIOMETRIC_UNLOCK_TIMEOUT", "1")
    return env


_1PASSWORD_AVAILABLE = False
_1PASSWORD_ERR = ""
if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") or os.environ.get("OP_CONNECT_HOST"):
    try:
        r = subprocess.run(
            ["op", "whoami"],
            capture_output=True,
            text=True,
            timeout=OP_TIMEOUT,
            env=_op_env(),
        )
        _1PASSWORD_AVAILABLE = r.returncode == 0
        if not _1PASSWORD_AVAILABLE:
            _1PASSWORD_ERR = (r.stderr or r.stdout or "op whoami failed")[:200]
    except Exception as e:
        _1PASSWORD_AVAILABLE = False
        _1PASSWORD_ERR = str(e)[:200]


def _load_from_1password(key: str):
    if not _1PASSWORD_AVAILABLE:
        return None
    try:
        result = subprocess.run(
            [
                "op",
                "item",
                "get",
                key,
                "--vault",
                VAULT,
                "--field",
                _field_name(key),
                "--reveal",
            ],
            capture_output=True,
            text=True,
            timeout=OP_TIMEOUT,
            env=_op_env(),
        )
        if result.returncode == 0:
            val = result.stdout.strip()
            return val or None
        # fallback: try credential field names commonly used
        for field in ("password", "credential", "api_key", "token", "secret", "notesPlain"):
            if field == _field_name(key):
                continue
            result = subprocess.run(
                [
                    "op",
                    "item",
                    "get",
                    key,
                    "--vault",
                    VAULT,
                    "--field",
                    field,
                    "--reveal",
                ],
                capture_output=True,
                text=True,
                timeout=OP_TIMEOUT,
                env=_op_env(),
            )
            if result.returncode == 0 and result.stdout.strip():
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
                if k.strip() != key:
                    continue
                val = v.strip().strip('"').strip("'")
                if " #" in val:
                    val = val.split(" #", 1)[0].strip()
                return val
    except Exception:
        pass
    return None


def load_all(keys=None):
    keys = keys or KNOWN_SECRETS
    source_mode = (os.environ.get("HERMES_SECRETS_SOURCE") or "auto").lower()
    no_env = os.environ.get("HERMES_SECRETS_NO_ENV", "").lower() in ("1", "true", "yes")
    stats = {"1password": 0, "env": 0, "already": 0, "missing": 0}

    for key in keys:
        if os.environ.get(key):
            stats["already"] += 1
            continue

        val = None
        if source_mode in ("auto", "1password", "op"):
            val = _load_from_1password(key)
            if val:
                os.environ[key] = val
                stats["1password"] += 1
                # alias common pairs
                if key == "DB_PASSWORD" and not os.environ.get("PGPASSWORD"):
                    os.environ["PGPASSWORD"] = val
                continue

        if source_mode in ("auto", "env") and not no_env:
            val = _load_from_env_file(key)
            if val:
                os.environ[key] = val
                stats["env"] += 1
                if key == "DB_PASSWORD" and not os.environ.get("PGPASSWORD"):
                    os.environ["PGPASSWORD"] = val
                continue

        stats["missing"] += 1
    return stats


# Run on import
_STATS = load_all()

if __name__ == "__main__":
    print(f"vault={VAULT}")
    print(f"1password_available={_1PASSWORD_AVAILABLE} err={_1PASSWORD_ERR!r}")
    print(f"load_stats={_STATS}")
    for k in KNOWN_SECRETS:
        print(f"{k}: {'set' if os.environ.get(k) else 'NOT SET'}")
