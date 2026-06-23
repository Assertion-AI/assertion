#!/usr/bin/env python3
"""One-command Cursor setup for Assertion memory.

Wires Cursor to the hosted Assertion memory backend by writing three files:
  - ~/.assertion/credentials.json  — your API key (read by the capture/inject hooks)
  - ~/.cursor/hooks.json           — sessionStart / beforeSubmitPrompt / afterAgentResponse
  - ~/.cursor/mcp.json             — the recall/expand MCP server

Defaults to PROD (memory.assertion-ai.com) and the shared `default` workspace. Merges
into existing Cursor config (won't clobber other hooks/MCP servers), is safe to re-run
(idempotent), and backs up any file it changes.

Usage:
  python3 install_cursor.py                       # prompts for the API key
  python3 install_cursor.py --key sk-...           # non-interactive
  python3 install_cursor.py --workspace my-ws      # different tree
  python3 install_cursor.py --server https://...   # point at a non-prod backend
  python3 install_cursor.py --uninstall            # remove what this installer added
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import sys
import time

HOME = os.path.expanduser("~")
CREDS = os.path.join(HOME, ".assertion", "credentials.json")
CURSOR_HOOKS = os.path.join(HOME, ".cursor", "hooks.json")
CURSOR_MCP = os.path.join(HOME, ".cursor", "mcp.json")
CURSOR_COMMANDS = os.path.join(HOME, ".cursor", "commands")
PROD = "https://memory.assertion-ai.com"
SCRIPT_NAMES = ("sessionstart_inject.py", "userpromptsubmit_delta.py", "hook_on_stop.py")


def _scripts_dir() -> str:
    # This file lives in plugin/cursor/; the hook scripts are in plugin/scripts/.
    d = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    missing = [n for n in SCRIPT_NAMES if not os.path.exists(os.path.join(d, n))]
    if missing:
        sys.exit(f"error: hook scripts not found in {d} (missing: {', '.join(missing)}).\n"
                 f"Run this from the plugin repo's plugin/cursor/ directory.")
    return d


def _pick_python() -> str:
    # Cursor's GUI runs hooks with a minimal PATH, so prefer an absolute interpreter.
    for cand in ("/usr/bin/python3", shutil.which("python3"), sys.executable):
        if cand and os.path.exists(cand):
            return cand
    return "python3"


def _load_json(path: str) -> dict:
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _backup(path: str) -> None:
    if os.path.exists(path):
        bak = f"{path}.bak.{int(time.time())}"
        shutil.copy2(path, bak)
        print(f"  backed up {path} -> {bak}")


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path}")


def _is_ours(cmd: str) -> bool:
    return any(name in cmd for name in SCRIPT_NAMES)


def install(key: str, server: str, workspace: str) -> None:
    scripts = _scripts_dir()
    py = _pick_python()
    print(f"scripts: {scripts}\npython : {py}\nserver : {server}\nworkspace: {workspace}\n")

    # 1) credentials file (key + server for the hooks) — preserve any other fields.
    creds = _load_json(CREDS)
    creds["api_key"] = key
    creds["server_url"] = server
    _backup(CREDS)
    _write_json(CREDS, creds)

    # 2) hooks.json — replace only OUR entries (idempotent), keep any other hooks the user has.
    def cmd(script):
        return f'ASSERTION_WORKSPACE={workspace} {py} "{os.path.join(scripts, script)}"'

    hooks = _load_json(CURSOR_HOOKS)
    hooks["version"] = 1
    hmap = hooks.get("hooks")
    if not isinstance(hmap, dict):
        hmap = {}
    for event, script in (("sessionStart", "sessionstart_inject.py"),
                          ("beforeSubmitPrompt", "userpromptsubmit_delta.py"),
                          ("afterAgentResponse", "hook_on_stop.py")):
        lst = [e for e in (hmap.get(event) or []) if not _is_ours((e or {}).get("command", ""))]
        lst.append({"command": cmd(script)})
        hmap[event] = lst
    hooks["hooks"] = hmap
    _backup(CURSOR_HOOKS)
    _write_json(CURSOR_HOOKS, hooks)

    # 3) mcp.json — set only our server, preserve any others.
    mcp = _load_json(CURSOR_MCP)
    servers = mcp.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["assertion"] = {
        "url": f"{server.rstrip('/')}/memory/mcp/{workspace}",
        "headers": {"Authorization": f"Bearer {key}"},
    }
    mcp["mcpServers"] = servers
    _backup(CURSOR_MCP)
    _write_json(CURSOR_MCP, mcp)

    # 4) /catchup slash command — copy our command into the global Cursor commands dir.
    src_cmd = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands", "catchup.md")
    if os.path.exists(src_cmd):
        os.makedirs(CURSOR_COMMANDS, exist_ok=True)
        shutil.copy2(src_cmd, os.path.join(CURSOR_COMMANDS, "catchup.md"))
        print(f"  wrote {os.path.join(CURSOR_COMMANDS, 'catchup.md')}")

    print("\n✅ Installed. Just:")
    print("  1. Fully quit and reopen Cursor (it loads the hooks + MCP server on launch).")
    print("  2. Start working — that's it. The 'assertion' server shows under Settings → Tools & MCPs,")
    print("     and capture + memory injection run automatically (no enable/Get step).")
    print("     If Cursor asks you to trust the hooks, approve them.")
    print("  Verify anytime: ask \"recall <a topic you've worked on>\".")
    print("  Tip: type /catchup (optionally with a topic or node id) for a grounded catch-up.")


def uninstall(server: str, workspace: str) -> None:
    # Remove only our hook entries and our MCP server; leave everything else (and creds) intact.
    hooks = _load_json(CURSOR_HOOKS)
    hmap = hooks.get("hooks") or {}
    changed = False
    for event in ("sessionStart", "beforeSubmitPrompt", "afterAgentResponse"):
        if event in hmap:
            kept = [e for e in hmap[event] if not _is_ours((e or {}).get("command", ""))]
            if kept != hmap[event]:
                changed = True
            if kept:
                hmap[event] = kept
            else:
                del hmap[event]
    if changed:
        hooks["hooks"] = hmap
        _backup(CURSOR_HOOKS)
        _write_json(CURSOR_HOOKS, hooks)
    mcp = _load_json(CURSOR_MCP)
    if isinstance(mcp.get("mcpServers"), dict) and "assertion" in mcp["mcpServers"]:
        del mcp["mcpServers"]["assertion"]
        _backup(CURSOR_MCP)
        _write_json(CURSOR_MCP, mcp)
    cmd_path = os.path.join(CURSOR_COMMANDS, "catchup.md")
    if os.path.exists(cmd_path):
        os.remove(cmd_path)
        print(f"  removed {cmd_path}")
    print("\n✅ Removed Assertion hooks + MCP server from Cursor config. "
          "Your key in ~/.assertion/credentials.json was left in place; delete it manually if you want.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Set up Assertion memory for Cursor.")
    ap.add_argument("--key", help="API key (else prompts / reads ASSERTION_API_KEY)")
    ap.add_argument("--server", default=PROD, help=f"backend base URL (default {PROD})")
    ap.add_argument("--workspace", default="default", help="workspace / tree (default: default)")
    ap.add_argument("--uninstall", action="store_true", help="remove what this installer added")
    args = ap.parse_args()

    if args.uninstall:
        uninstall(args.server, args.workspace)
        return 0

    key = args.key or os.environ.get("ASSERTION_API_KEY") or ""
    if not key:
        try:
            key = getpass.getpass("Assertion API key (get it at https://assertion-ai.com): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1
    if not key:
        sys.exit("error: no API key provided.")

    install(key, args.server.rstrip("/"), args.workspace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
