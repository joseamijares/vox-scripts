#!/usr/bin/env python3
"""
Pull 1Password vault secrets into process environment (and optional .env.generated).

Source of truth: vault (default "Vox Hermes Vault")
Direction: vault → environment  (not the other way)

Usage:
  # print status only (no secret values)
  python3 vault_to_env.py --status

  # load into current process + write ~/.hermes/.env.generated
  python3 vault_to_env.py --write

  # also replace ~/.hermes/.env with generated file (keeps backup)
  python3 vault_to_env.py --write --replace-env

Cron/scripts should:
  import hermes_secrets_bootstrap  # which calls vault inject first
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
from op_wrap import op, load_token, vault_name  # noqa: E402

HERMES = Path.home() / ".hermes"
GENERATED = HERMES / ".env.generated"
ENV_PATH = HERMES / ".env"
CACHE_JSON = HERMES / "secrets" / "vault_env_cache.json"
CACHE_TTL_SEC = int(os.environ.get("HERMES_VAULT_CACHE_TTL", "3600"))

# Map vault item titles that are not exact env keys
TITLE_ALIASES = {
    "OpenRouter": "OPENROUTER_API_KEY",
    "Railway DB": "DB_PASSWORD",
    "Railway DB Password": "DB_PASSWORD",
    "PGPASSWORD": "PGPASSWORD",
}

# Fields to try when reading an item
FIELD_CANDIDATES = (
    "credential",
    "password",
    "token",
    "secret",
    "api_key",
    "notesPlain",
    "username",  # last resort never for secrets ideally
)


def _is_env_key(title: str) -> bool:
    if title in TITLE_ALIASES:
        return True
    # ENV_VAR style
    return bool(re.match(r"^[A-Z][A-Z0-9_]{1,64}$", title))


def _env_key_for_title(title: str) -> str:
    return TITLE_ALIASES.get(title, title)


def list_vault_titles(vault: str) -> list[str]:
    rc, out, err = op(
        ["item", "list", "--vault", vault, "--format=json"],
        timeout=45,
        settle=1.5,
    )
    if not out.strip().startswith("["):
        raise RuntimeError(f"item list failed rc={rc} err={err[:200]} out={out[:200]}")
    items = json.loads(out)
    return [it.get("title") or "" for it in items if it.get("title")]


def read_item_secret(title: str, vault: str) -> str | None:
    for field in FIELD_CANDIDATES:
        rc, out, err = op(
            ["item", "get", title, "--vault", vault, "--field", field, "--reveal"],
            timeout=25,
            settle=0.9,
        )
        val = (out or "").strip()
        # skip junk / error messages
        if not val:
            continue
        if val.lower().startswith("error") or "using configuration" in val.lower():
            continue
        # field might return "[use 'op item get ... --reveal']" without --reveal; we use --reveal
        if len(val) < 1:
            continue
        return val
    return None


def load_cache() -> dict | None:
    if not CACHE_JSON.exists():
        return None
    try:
        data = json.loads(CACHE_JSON.read_text())
        ts = data.get("ts", 0)
        if time.time() - ts > CACHE_TTL_SEC:
            return None
        if data.get("vault") != vault_name():
            return None
        return data.get("secrets") or None
    except Exception:
        return None


def save_cache(secrets: dict):
    CACHE_JSON.parent.mkdir(parents=True, exist_ok=True)
    # cache is sensitive
    CACHE_JSON.write_text(
        json.dumps(
            {
                "ts": time.time(),
                "vault": vault_name(),
                "secrets": secrets,
            }
        )
    )
    CACHE_JSON.chmod(0o600)


def pull_from_vault(use_cache: bool = True) -> dict[str, str]:
    """Return {ENV_KEY: value} from vault (or short TTL cache)."""
    if use_cache:
        cached = load_cache()
        if cached:
            return cached

    vault = vault_name()
    load_token()  # fail early
    titles = list_vault_titles(vault)
    secrets: dict[str, str] = {}
    for title in titles:
        if not _is_env_key(title):
            continue
        key = _env_key_for_title(title)
        # prefer exact OPENROUTER_API_KEY item over alias "OpenRouter" if both exist
        if key in secrets and title in TITLE_ALIASES:
            continue
        val = read_item_secret(title, vault)
        if val:
            secrets[key] = val
        time.sleep(0.05)

    # aliases
    if secrets.get("DB_PASSWORD") and not secrets.get("PGPASSWORD"):
        secrets["PGPASSWORD"] = secrets["DB_PASSWORD"]
    if secrets.get("PGPASSWORD") and not secrets.get("DB_PASSWORD"):
        secrets["DB_PASSWORD"] = secrets["PGPASSWORD"]

    if secrets:
        save_cache(secrets)
    return secrets


def apply_to_environ(secrets: dict[str, str], overwrite: bool = False) -> int:
    n = 0
    for k, v in secrets.items():
        if not overwrite and os.environ.get(k):
            continue
        os.environ[k] = v
        n += 1
    return n


def write_generated(secrets: dict[str, str], path: Path = GENERATED) -> None:
    lines = [
        f"# AUTO-GENERATED from 1Password vault: {vault_name()}",
        f"# Generated: {datetime.now(timezone.utc).isoformat()}",
        f"# Do not edit by hand — run: python3 ~/.hermes/scripts/vault_to_env.py --write",
        f"# Source: vault → environment",
        "",
    ]
    for k in sorted(secrets):
        v = secrets[k]
        # escape nothing fancy; values may contain $ — write raw
        if "\n" in v or '"' in v:
            # basic quoting
            lines.append(f"{k}={json.dumps(v)}")
        else:
            lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)


def main():
    ap = argparse.ArgumentParser(description="Vault → environment secrets")
    ap.add_argument("--status", action="store_true", help="List keys only")
    ap.add_argument("--write", action="store_true", help="Write .env.generated + apply to env")
    ap.add_argument(
        "--replace-env",
        action="store_true",
        help="Backup and replace ~/.hermes/.env with generated file",
    )
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--overwrite-env", action="store_true", help="Overwrite already-set env vars")
    args = ap.parse_args()

    secrets = pull_from_vault(use_cache=not args.no_cache)
    print(f"vault={vault_name()} keys={len(secrets)}")
    for k in sorted(secrets):
        print(f"  {k}=<{len(secrets[k])} chars>")

    if args.status and not args.write:
        return 0

    if args.write or not args.status:
        n = apply_to_environ(secrets, overwrite=args.overwrite_env)
        print(f"applied_to_environ={n}")
        write_generated(secrets)
        print(f"wrote {GENERATED}")

        if args.replace_env:
            if ENV_PATH.exists():
                bak = ENV_PATH.with_name(
                    f".env.archived.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
                bak.write_text(ENV_PATH.read_text())
                bak.chmod(0o600)
                print(f"backed up {ENV_PATH} -> {bak.name}")
            # copy generated to .env
            ENV_PATH.write_text(GENERATED.read_text())
            ENV_PATH.chmod(0o600)
            print(f"replaced {ENV_PATH} from vault")

    return 0 if secrets else 1


if __name__ == "__main__":
    raise SystemExit(main())
