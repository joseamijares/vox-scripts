#!/usr/bin/env python3
"""Bootstrap secrets: local env files first, optional live vault.

Vault name: "Vox Hermes Vault" (HERMES_OP_VAULT override)
Token: ~/.hermes/secrets/1password_service_account  OR  OP_SERVICE_ACCOUNT_TOKEN

CRITICAL (2026-07-22): Live `op` calls hang in gateway/cron even with a service
account. Prefer ~/.hermes/.env.generated and ~/.hermes/.env. Only hit the vault
when critical keys are missing, or HERMES_SECRETS_FORCE_VAULT=1.

Disable live vault entirely:
  HERMES_SECRETS_NO_VAULT=1

Usage:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.home() / ".hermes" / "scripts"))
    import hermes_secrets_bootstrap
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

VAULT = os.environ.get("HERMES_OP_VAULT", "Vox Hermes Vault")
TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "1password_service_account"
ENV_PATH = Path.home() / ".hermes" / ".env"
GENERATED_PATH = Path.home() / ".hermes" / ".env.generated"
SCRIPTS = Path.home() / ".hermes" / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Load service account token into env for op (only used if vault path runs)
if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN") and TOKEN_PATH.exists():
    try:
        for line in TOKEN_PATH.read_text().splitlines():
            if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip()
                break
    except Exception:
        pass
if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
    os.environ.setdefault("OP_BIOMETRIC_UNLOCK_TIMEOUT", "0")
os.environ.setdefault("HERMES_OP_VAULT", VAULT)

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
    "TELEGRAM_BROADCAST_CHAT_ID",
    "TELEGRAM_BROADCAST_BOT_TOKEN",
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
    "ALPHA_VANTAGE_API_KEY",
    "BROWSERBASE_ADVANCED_STEALTH",
]

# Minimum set for VOX cron scripts to proceed without live vault.
CRITICAL_SECRETS = (
    "DB_PASSWORD",
    "PGPASSWORD",
    "DB_HOST",
)


def _load_dotenv_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text().splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if " #" in v:
                v = v.split(" #", 1)[0].strip()
            if k and v:
                out[k] = v
    except Exception:
        pass
    return out


def _apply_db_aliases() -> None:
    if os.environ.get("DB_PASSWORD") and not os.environ.get("PGPASSWORD"):
        os.environ["PGPASSWORD"] = os.environ["DB_PASSWORD"]
    if os.environ.get("PGPASSWORD") and not os.environ.get("DB_PASSWORD"):
        os.environ["DB_PASSWORD"] = os.environ["PGPASSWORD"]


def _critical_ok() -> bool:
    _apply_db_aliases()
    # Need a DB password and host at minimum.
    pw = os.environ.get("DB_PASSWORD") or os.environ.get("PGPASSWORD")
    host = os.environ.get("DB_HOST") or os.environ.get("PGHOST")
    return bool(pw and host)


def _load_from_vault() -> dict[str, str]:
    """Vault → dict via vault_to_env (hang-tolerant op). Only when forced/needed."""
    no_vault = os.environ.get("HERMES_SECRETS_NO_VAULT", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if no_vault:
        return {}
    if not os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return {}
    try:
        from vault_to_env import pull_from_vault

        return pull_from_vault(use_cache=True) or {}
    except Exception as e:
        os.environ["_HERMES_VAULT_ERR"] = str(e)[:200]
        return {}


def load_all() -> dict:
    """
    Priority (fixed 2026-07-22 after mass cron 3600s hangs on `op`):
      1) already in os.environ
      2) .env.generated (last vault sync) — FAST path for crons
      3) .env (emergency) unless HERMES_SECRETS_NO_ENV=1
      4) live 1Password vault ONLY if critical keys still missing
         OR HERMES_SECRETS_FORCE_VAULT=1
    """
    stats = {
        "vault": 0,
        "generated": 0,
        "env": 0,
        "already": 0,
        "missing": 0,
        "vault_skipped": 0,
    }
    no_env = os.environ.get("HERMES_SECRETS_NO_ENV", "").lower() in (
        "1",
        "true",
        "yes",
    )
    force_vault = os.environ.get("HERMES_SECRETS_FORCE_VAULT", "").lower() in (
        "1",
        "true",
        "yes",
    )

    # 1 already set
    for k in KNOWN_SECRETS:
        if os.environ.get(k):
            stats["already"] += 1

    # 2 generated file (preferred durable cache)
    if any(not os.environ.get(k) for k in KNOWN_SECRETS):
        gen = _load_dotenv_file(GENERATED_PATH)
        for k, v in gen.items():
            if not os.environ.get(k) and v:
                os.environ[k] = v
                stats["generated"] += 1
        _apply_db_aliases()

    # 3 emergency .env
    if not no_env and any(not os.environ.get(k) for k in KNOWN_SECRETS):
        envf = _load_dotenv_file(ENV_PATH)
        for k, v in envf.items():
            if not os.environ.get(k) and v:
                os.environ[k] = v
                stats["env"] += 1
        _apply_db_aliases()

    # 4 live vault — only if still missing critical DB secrets or forced
    need_vault = force_vault or not _critical_ok()
    if need_vault:
        vault_secrets = _load_from_vault()
        for k, v in vault_secrets.items():
            if not os.environ.get(k) and v:
                os.environ[k] = v
                stats["vault"] += 1
        _apply_db_aliases()
    else:
        stats["vault_skipped"] = 1
        os.environ.setdefault("_HERMES_VAULT_SKIP", "local_env_sufficient")

    for k in KNOWN_SECRETS:
        if not os.environ.get(k):
            stats["missing"] += 1

    return stats


_STATS = load_all()

if __name__ == "__main__":
    print(f"vault={VAULT}")
    print(f"stats={_STATS}")
    print(f"vault_err={os.environ.get('_HERMES_VAULT_ERR', '')}")
    print(f"vault_skip={os.environ.get('_HERMES_VAULT_SKIP', '')}")
    for k in KNOWN_SECRETS:
        v = os.environ.get(k)
        print(f"{k}: {'set('+str(len(v))+')' if v else 'NOT SET'}")
