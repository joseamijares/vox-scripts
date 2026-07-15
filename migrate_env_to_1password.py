#!/usr/bin/env python3
"""
Migrate ~/.hermes/.env secrets into 1Password vault "Vox Hermes".

Creates one API Credential item per KEY named exactly as the env var.
Field convention (matches hermes_secrets_bootstrap):
  - *PASSWORD*  → password
  - *TOKEN*     → token
  - *SECRET*    → secret
  - else        → credential

Usage:
  # dry-run (default)
  python3 migrate_env_to_1password.py

  # write to 1Password
  python3 migrate_env_to_1password.py --apply

  # after verify: archive local .env (keeps pointer only)
  python3 migrate_env_to_1password.py --apply --archive-env

Requires working `op` (service account recommended):
  export OP_SERVICE_ACCOUNT_TOKEN=ops_...
  # or file: ~/.hermes/secrets/1password_service_account
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VAULT = os.environ.get("HERMES_OP_VAULT", "Vox Hermes")
ENV_PATH = Path.home() / ".hermes" / ".env"
TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "1password_service_account"
OP_TIMEOUT = 20

SKIP_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "SHELL",
    "TERM",
    "LANG",
    "PWD",
}


def ensure_token():
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN"):
        return True
    if TOKEN_PATH.exists():
        for line in TOKEN_PATH.read_text().splitlines():
            if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                os.environ["OP_SERVICE_ACCOUNT_TOKEN"] = line.split("=", 1)[1].strip()
                os.environ.setdefault("OP_BIOMETRIC_UNLOCK_TIMEOUT", "1")
                return True
    return False


def field_name(key: str) -> str:
    kl = key.upper()
    if "PASSWORD" in kl:
        return "password"
    if "SECRET" in kl and "KEY" in kl:
        return "secret"
    if "SECRET" in kl:
        return "secret"
    if "TOKEN" in kl:
        return "token"
    return "credential"


def op(args, timeout=OP_TIMEOUT):
    return subprocess.run(
        ["op", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )


def parse_env(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        k = k.strip()
        if not k or k in SKIP_KEYS:
            continue
        v = v.strip().strip('"').strip("'")
        if " #" in v:
            v = v.split(" #", 1)[0].strip()
        if not v:
            continue
        out[k] = v
    return out


def item_exists(title: str) -> bool:
    r = op(["item", "get", title, "--vault", VAULT], timeout=12)
    return r.returncode == 0


def create_or_update(key: str, value: str, apply: bool) -> str:
    field = field_name(key)
    if item_exists(key):
        if not apply:
            return "would_update"
        # edit field
        r = op(
            [
                "item",
                "edit",
                key,
                f"{field}[password]={value}" if field == "password" else f"{field}[text]={value}",
                "--vault",
                VAULT,
            ],
            timeout=20,
        )
        if r.returncode != 0:
            # try generic assignment
            r2 = op(
                ["item", "edit", key, f"{field}={value}", "--vault", VAULT],
                timeout=20,
            )
            if r2.returncode != 0:
                return f"edit_fail:{(r2.stderr or r.stderr)[:120]}"
        return "updated"

    if not apply:
        return "would_create"

    # API Credential category works well for keys
    # op item create --category "API Credential" --title KEY --vault VAULT credential=...
    assignment = f"{field}={value}"
    r = op(
        [
            "item",
            "create",
            "--category",
            "API Credential",
            "--title",
            key,
            "--vault",
            VAULT,
            assignment,
            f"notesPlain=Migrated from Hermes .env on {datetime.utcnow().date().isoformat()}",
        ],
        timeout=25,
    )
    if r.returncode != 0:
        return f"create_fail:{(r.stderr or r.stdout)[:160]}"
    return "created"


def archive_env(keys_migrated: list):
    if not ENV_PATH.exists():
        return
    bak = ENV_PATH.with_name(
        f".env.archived.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    bak.write_text(ENV_PATH.read_text())
    os.chmod(bak, 0o600)
    # leave pointer file only — no secrets
    ENV_PATH.write_text(
        "\n".join(
            [
                "# Hermes secrets moved to 1Password",
                f"# vault: {VAULT}",
                f"# archived: {bak.name}",
                "# keys were:",
                *[f"#   {k}" for k in sorted(keys_migrated)],
                "#",
                "# Loader: hermes_secrets_bootstrap.py (1Password first)",
                "# Token:  ~/.hermes/secrets/1password_service_account",
                "# Set HERMES_SECRETS_NO_ENV=1 to refuse any .env fallback",
                "",
            ]
        )
    )
    os.chmod(ENV_PATH, 0o600)
    print(f"Archived secrets → {bak}")
    print(f"Replaced {ENV_PATH} with pointer (no secret values)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write to 1Password")
    ap.add_argument(
        "--archive-env",
        action="store_true",
        help="After apply, archive .env and leave pointer only",
    )
    ap.add_argument("--vault", default=VAULT)
    args = ap.parse_args()
    global VAULT
    VAULT = args.vault

    if not ensure_token():
        print("ERROR: No OP_SERVICE_ACCOUNT_TOKEN. Put it in")
        print(f"  {TOKEN_PATH}")
        print("or export OP_SERVICE_ACCOUNT_TOKEN=ops_...")
        return 1

    # health
    try:
        r = op(["whoami"], timeout=10)
    except subprocess.TimeoutExpired:
        print("ERROR: `op whoami` hung/timed out.")
        print("Fix 1Password CLI first (service account / network / unlock), then re-run.")
        return 2
    if r.returncode != 0:
        print("ERROR: op whoami failed:", (r.stderr or r.stdout)[:300])
        return 2
    print("op ok:", r.stdout.strip()[:120])

    secrets = parse_env(ENV_PATH)
    if not secrets:
        print(f"No secrets found in {ENV_PATH}")
        return 0
    print(f"Found {len(secrets)} keys in .env")

    results = {}
    for k, v in sorted(secrets.items()):
        try:
            results[k] = create_or_update(k, v, apply=args.apply)
            print(f"  {k}: {results[k]} (field={field_name(k)})")
        except subprocess.TimeoutExpired:
            results[k] = "timeout"
            print(f"  {k}: timeout")
        except Exception as e:
            results[k] = f"err:{e}"
            print(f"  {k}: {results[k]}")

    ok = [k for k, s in results.items() if s in ("created", "updated", "would_create", "would_update")]
    bad = {k: s for k, s in results.items() if k not in ok}
    print(f"\nOK/planned: {len(ok)}  problems: {len(bad)}")
    if bad:
        for k, s in bad.items():
            print(f"  ! {k}: {s}")

    if args.apply and args.archive_env:
        if bad:
            print("Not archiving .env because some keys failed.")
            return 3
        migrated = [k for k, s in results.items() if s in ("created", "updated")]
        archive_env(migrated)

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write items.")
    return 0 if not bad else 3


if __name__ == "__main__":
    raise SystemExit(main())
