#!/usr/bin/env python3
"""Hang-tolerant 1Password CLI wrapper.

`op` often authenticates, prints results, then never exits (daemon stuck).
Worse: blocking pipe reads can hang forever even after select() says ready.

This helper:
  - runs `op` in its own process group
  - uses non-blocking stdout/stderr reads
  - kills the whole group on complete-looking output or hard timeout
"""
from __future__ import annotations

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


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill process group first, then the process itself."""
    try:
        if proc.pid:
            os.killpg(proc.pid, 9)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass
    try:
        proc.communicate(timeout=2)
    except Exception:
        pass


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
        start_new_session=True,  # own process group for killpg
    )
    assert proc.stdout is not None and proc.stderr is not None
    try:
        os.set_blocking(proc.stdout.fileno(), False)
        os.set_blocking(proc.stderr.fileno(), False)
    except Exception:
        pass

    t0 = time.time()
    out_chunks: list[str] = []
    err_chunks: list[str] = []
    first_out_at = None

    try:
        while time.time() - t0 < timeout:
            if proc.poll() is not None:
                # drain nonblocking
                try:
                    o = proc.stdout.read() or ""
                    e = proc.stderr.read() or ""
                except Exception:
                    o, e = "", ""
                out = "".join(out_chunks) + o
                err = "".join(err_chunks) + e
                return proc.returncode or 0, out, err

            try:
                r, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.3)
            except Exception:
                r = []

            for f in r:
                try:
                    data = f.read()
                except BlockingIOError:
                    continue
                except Exception:
                    continue
                if not data:
                    continue
                if f is proc.stdout:
                    out_chunks.append(data)
                    if first_out_at is None:
                        first_out_at = time.time()
                else:
                    err_chunks.append(data)

            if first_out_at and (time.time() - first_out_at) >= settle:
                # brief extra drain then kill group (op often never exits)
                time.sleep(0.35)
                try:
                    r, _, _ = select.select([proc.stdout, proc.stderr], [], [], 0.2)
                except Exception:
                    r = []
                for f in r:
                    try:
                        data = f.read()
                    except Exception:
                        data = None
                    if not data:
                        continue
                    if f is proc.stdout:
                        out_chunks.append(data)
                    else:
                        err_chunks.append(data)
                _kill_tree(proc)
                out = "".join(out_chunks)
                err = "".join(err_chunks)
                rc = 0 if out.strip() else 1
                return rc, out, err

        _kill_tree(proc)
        out = "".join(out_chunks)
        err = "".join(err_chunks)
        return (-1, out, err)
    except Exception as e:
        _kill_tree(proc)
        return (-1, "".join(out_chunks), f"{''.join(err_chunks)}\nop_wrap_error={e}")


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
