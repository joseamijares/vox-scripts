#!/usr/bin/env python3
"""Hang-tolerant 1Password CLI wrapper.

`op` authenticates and prints results, then often never exits (daemon stuck).
This helper reads stdout and kills the process once output looks complete.
"""
from __future__ import annotations

import json
import os
import select
import subprocess
import tempfile
import time
from pathlib import Path

TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "1password_service_account"
DEFAULT_VAULT = os.environ.get("HERMES_OP_VAULT", "Vox Hermes Vault")


def load_token() -> str:
    if os.environ.get("OP_SERVICE_ACCOUNT_TOKEN", "").startswith("ops_"):
        return os.environ["OP_SERVICE_ACCOUNT_TOKEN"].strip()
    if TOKEN_PATH.exists():
        for line in TOKEN_PATH.read_text().splitlines():
            if line.startswith("OP_SERVICE_ACCOUNT_TOKEN=ops_"):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"No service account token in {TOKEN_PATH}")


def op(args: list[str], timeout: float = 30.0, settle: float = 1.2) -> tuple[int, str, str]:
    """Run `op args`; return (rc, stdout, stderr). rc=0 if useful stdout even after kill."""
    tok = load_token()
    env = os.environ.copy()
    env["OP_SERVICE_ACCOUNT_TOKEN"] = tok
    env["OP_BIOMETRIC_UNLOCK_TIMEOUT"] = "0"
    cfg = tempfile.mkdtemp(prefix="op-wrap-")
    env["OP_CONFIG_DIR"] = cfg

    proc = subprocess.Popen(
        ["op", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )
    t0 = time.time()
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    first_out_at = None

    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            o, e = proc.communicate(timeout=2)
            out = "".join(out_chunks) + (o or "")
            err = "".join(err_chunks) + (e or "")
            return proc.returncode or 0, out, err

        r, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.3)
        for f in r:
            data = f.read()
            if not data:
                continue
            if f is proc.stdout:
                out_chunks.append(data)
                if first_out_at is None:
                    first_out_at = time.time()
            else:
                err_chunks.append(data)

        if first_out_at and (time.time() - first_out_at) >= settle:
            # allow a bit more drain
            time.sleep(0.4)
            r, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.3)
            for f in r:
                data = f.read()
                if data:
                    if f is proc.stdout:
                        out_chunks.append(data)
                    else:
                        err_chunks.append(data)
            proc.kill()
            try:
                o, e = proc.communicate(timeout=2)
                if o:
                    out_chunks.append(o)
                if e:
                    err_chunks.append(e)
            except Exception:
                pass
            out = "".join(out_chunks)
            err = "".join(err_chunks)
            # treat non-empty successful-looking output as rc 0
            rc = 0 if out.strip() else 1
            return rc, out, err

    proc.kill()
    try:
        o, e = proc.communicate(timeout=2)
    except Exception:
        o, e = "", ""
    out = "".join(out_chunks) + (o or "")
    err = "".join(err_chunks) + (e or "")
    return (-1, out, err)


def vault_name() -> str:
    return DEFAULT_VAULT


if __name__ == "__main__":
    import sys

    args = sys.argv[1:] or ["whoami"]
    rc, out, err = op(args)
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    raise SystemExit(0 if rc == 0 else 1)
