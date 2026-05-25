#!/usr/bin/env python3
"""
Composio tool execution wrapper for Hermes Agent.
Call this script to execute any Composio tool from Hermes.

Usage:
  python3 composio_run.py search "yahoo finance stock price"
  python3 composio_run.py tools_list github --limit 5
  python3 composio_run.py execute GITHUB_GET_THE_AUTHENTICATED_USER
  python3 composio_run.py link github
"""
import os, sys, json, subprocess, textwrap

COMPOSIO_PATH = os.path.expanduser("~/.composio")
API_KEY = os.environ.get("COMPOSIO_API_KEY", "uak_zwBd4-GiasWKW7yedRYW")

def run_composio_cmd(args):
    """Run a Composio CLI command and return parsed output."""
    env = os.environ.copy()
    env["PATH"] = f"{COMPOSIO_PATH}:{env.get('PATH', '')}"
    env["COMPOSIO_API_KEY"] = API_KEY
    cmd = ["composio"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    # Remove ANSI escape codes from stderr
    import re
    stderr_clean = re.sub(r'\x1b\[[0-9;]*m', '', stderr)
    if result.returncode == 0:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"output": stdout}
    else:
        try:
            return json.loads(stdout) if stdout else {"error": stderr_clean, "returncode": result.returncode}
        except json.JSONDecodeError:
            return {"error": stderr_clean, "returncode": result.returncode}

def composio_search(query, limit=10):
    """Search for Composio tools by use case."""
    return run_composio_cmd(["search", query, "--limit", str(limit)])

def composio_tools_list(toolkit, limit=20):
    """List tools available in a toolkit."""
    return run_composio_cmd(["tools", "list", toolkit, "--limit", str(limit)])

def composio_execute(tool_slug, data=None, dry_run=False):
    """Execute a Composio tool by slug."""
    args = ["execute", tool_slug]
    if data:
        args.extend(["-d", json.dumps(data)])
    else:
        # For tools with no args, pass empty dict + skip-checks to avoid validation errors
        args.extend(["-d", "{}"])
        args.append("--skip-checks")
    if dry_run:
        args.append("--dry-run")
    return run_composio_cmd(args)

def composio_link(toolkit):
    """Connect/link an app/toolkit."""
    return run_composio_cmd(["link", toolkit])

def print_json(data):
    print(json.dumps(data, indent=2, default=str))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 composio_run.py <COMMAND> [ARGS...]")
        print("")
        print("Commands:")
        print("  search <query> [--limit N]          Search tools")
        print("  tools_list <toolkit> [--limit N]    List tools in toolkit")
        print("  execute <slug> [-d JSON] [--dry]    Execute a tool")
        print("  link <toolkit>                      Link/connect an app")
        print("")
        print("Examples:")
        print('  python3 composio_run.py search "stock price"')
        print('  python3 composio_run.py tools_list github --limit 5')
        print('  python3 composio_run.py execute GITHUB_GET_THE_AUTHENTICATED_USER')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search":
        query = sys.argv[2] if len(sys.argv) > 2 else ""
        limit = 10
        if "--limit" in sys.argv:
            idx = sys.argv.index("--limit")
            limit = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 10
        result = composio_search(query, limit)
        if "output" in result:
            print(result["output"])
        else:
            print_json(result)

    elif cmd == "tools_list":
        toolkit = sys.argv[2] if len(sys.argv) > 2 else "github"
        limit = int(sys.argv[4]) if "--limit" in sys.argv and len(sys.argv) > 4 else 20
        result = composio_tools_list(toolkit, limit)
        print_json(result)

    elif cmd == "execute":
        slug = sys.argv[2] if len(sys.argv) > 2 else ""
        data = None
        dry_run = False
        if "-d" in sys.argv:
            idx = sys.argv.index("-d")
            data = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "{}"
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                pass
        if "--dry" in sys.argv or "--dry-run" in sys.argv:
            dry_run = True
        result = composio_execute(slug, data, dry_run)
        print_json(result)

    elif cmd == "link":
        toolkit = sys.argv[2] if len(sys.argv) > 2 else ""
        result = composio_link(toolkit)
        print_json(result)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
