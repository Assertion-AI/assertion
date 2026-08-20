#!/usr/bin/env python3
"""One-command Codex setup for Assertion memory.

Wires the Codex CLI (and the VS Code Codex panel) to the hosted Assertion memory
backend so the user never has to type a path, hand-write JSON, or hand-edit TOML:

  - finds the `codex` binary even when it is not on PATH, and offers to fix PATH
  - registers the marketplace from its git URL (no "/abs/path/to/..." to supply)
  - installs the `assertion` plugin
  - writes ~/.assertion/credentials.json  (0600) — read by the capture/inject hooks
  - adds [mcp_servers.assertion] to ~/.codex/config.toml — the recall/expand tools

Defaults to PROD (memory.assertion-ai.com) and the shared `default` workspace.
Merges into existing Codex config (won't clobber other MCP servers or plugins), is
safe to re-run (idempotent), and backs up any file it changes.

One step cannot be automated: Codex requires a human keypress to trust the three
lifecycle hooks. There is no --trust flag and the trusted-hash format is internal
and undocumented, so this installer does not forge it — it prints the exact
remaining action instead.

Usage:
  python3 install_codex.py                       # prompts for the API key
  python3 install_codex.py --key sk-...          # non-interactive
  python3 install_codex.py --workspace my-ws     # different tree
  python3 install_codex.py --server https://...  # point at a non-prod backend
  python3 install_codex.py --no-path-fix         # never touch shell rc files
  python3 install_codex.py --uninstall           # remove what this installer added
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import time

HOME = os.path.expanduser("~")
CREDS = os.path.join(HOME, ".assertion", "credentials.json")
CODEX_CONFIG = os.path.join(HOME, ".codex", "config.toml")
PROD = "https://memory.assertion-ai.com"
MARKETPLACE_SOURCE = "https://github.com/Assertion-AI/assertion.git"
PLUGIN_NAME = "assertion"
MCP_SECTION = "mcp_servers.assertion"

# Where codex lands depending on how it was installed. Checked in order.
CODEX_CANDIDATES = (
    os.path.join(HOME, ".local", "bin", "codex"),
    "/usr/local/bin/codex",
    "/opt/homebrew/bin/codex",
    os.path.join(HOME, ".codex", "packages", "standalone", "current", "bin", "codex"),
)


# --------------------------------------------------------------------------- #
# locating codex
# --------------------------------------------------------------------------- #

def find_codex() -> tuple[str, bool]:
    """Return (path_to_codex, is_on_PATH).

    Resolving an absolute path matters more than it looks: the documented install
    tells users to run bare `codex`, but the standalone installer drops it in
    ~/.local/bin, which is not on PATH on a default macOS zsh setup. That single
    gap is the most common "the install doesn't work" report.
    """
    on_path = shutil.which("codex")
    if on_path:
        return on_path, True
    for cand in CODEX_CANDIDATES:
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand, False
    sys.exit(
        "error: could not find the Codex CLI.\n\n"
        "Install it first, then re-run this script:\n"
        "  npm install -g @openai/codex\n"
        "    — or see https://developers.openai.com/codex/cli\n"
    )


def shell_rc() -> str | None:
    """Best-guess rc file for the user's login shell."""
    sh = os.path.basename(os.environ.get("SHELL", "") or "")
    if sh == "zsh":
        return os.path.join(HOME, ".zshrc")
    if sh == "bash":
        # Login shells on macOS read .bash_profile; Linux reads .bashrc.
        prof = os.path.join(HOME, ".bash_profile")
        return prof if sys.platform == "darwin" and os.path.exists(prof) else os.path.join(HOME, ".bashrc")
    if sh == "fish":
        return os.path.join(HOME, ".config", "fish", "config.fish")
    return None


def ensure_on_path(codex_path: str) -> None:
    """Add codex's directory to PATH in the user's rc file, once.

    Skipped silently when codex is already reachable. Guarded by a grep so
    re-running the installer cannot append the same line twice.
    """
    bindir = os.path.dirname(codex_path)
    rc = shell_rc()
    if not rc:
        print(f"  ! could not detect your shell; add this to your shell profile yourself:\n"
              f"      export PATH=\"{bindir}:$PATH\"")
        return

    marker = "# added by Assertion install_codex.py"
    if rc.endswith("config.fish"):
        line = f'set -gx PATH "{bindir}" $PATH  {marker}\n'
    else:
        line = f'export PATH="{bindir}:$PATH"  {marker}\n'

    existing = ""
    if os.path.exists(rc):
        with open(rc) as f:
            existing = f.read()
    if bindir in existing and marker in existing:
        print(f"  PATH already configured in {rc}")
        return

    os.makedirs(os.path.dirname(rc), exist_ok=True)
    with open(rc, "a") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        f.write(line)
    print(f"  added {bindir} to PATH in {rc}")
    print(f"    (open a new terminal, or run: source {rc})")


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

def run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        sys.exit(f"error: command failed: {' '.join(cmd)}\n{detail}")
    return proc


def backup(path: str) -> None:
    """Copy path aside before we modify it, never clobbering an earlier backup.

    A plain unix-seconds suffix is not enough: two writes within the same second
    resolve to the same filename, and the second silently overwrites the first —
    which is exactly the copy of the user's *original* file you would want back.
    """
    if not os.path.exists(path):
        return
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.bak.{stamp}"
    n = 1
    while os.path.exists(bak):
        bak = f"{path}.bak.{stamp}-{n}"
        n += 1
    shutil.copy2(path, bak)
    os.chmod(bak, 0o600)  # config.toml and credentials both hold secrets
    print(f"  backed up {path} -> {bak}")


def load_json(path: str) -> dict:
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# marketplace + plugin
# --------------------------------------------------------------------------- #

def marketplace_name(codex: str, source: str) -> str | None:
    """Name Codex assigned to the marketplace with this git source, if registered.

    Resolved from `marketplace list` rather than hardcoded: the name is derived by
    Codex, so assuming "assertion-ai" would silently break if that ever changes.
    """
    proc = run([codex, "plugin", "marketplace", "list", "--json"], check=False)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except Exception:
        return None
    want = source.rstrip("/").removesuffix(".git")
    for mp in data.get("marketplaces") or []:
        src = ((mp.get("marketplaceSource") or {}).get("source") or "").rstrip("/").removesuffix(".git")
        if src == want:
            return mp.get("name")
    return None


def ensure_marketplace(codex: str, source: str) -> str:
    name = marketplace_name(codex, source)
    if name:
        print(f"  marketplace already registered as '{name}'")
        return name
    print(f"  registering marketplace {source}")
    run([codex, "plugin", "marketplace", "add", source])
    name = marketplace_name(codex, source)
    if not name:
        sys.exit("error: marketplace was added but could not be resolved; run "
                 "`codex plugin marketplace list` to inspect.")
    print(f"  registered as '{name}'")
    return name


def ensure_plugin(codex: str, marketplace: str) -> None:
    selector = f"{PLUGIN_NAME}@{marketplace}"
    proc = run([codex, "plugin", "add", selector], check=False)
    if proc.returncode == 0:
        print(f"  installed plugin {selector}")
        return
    # Already-installed is not an error for an idempotent installer. Confirm by
    # looking for the plugin's own config stanza before treating it as success.
    blob = ""
    if os.path.exists(CODEX_CONFIG):
        with open(CODEX_CONFIG) as f:
            blob = f.read()
    if f'[plugins."{selector}"]' in blob:
        print(f"  plugin {selector} already installed")
        return
    detail = (proc.stderr or proc.stdout or "").strip()
    sys.exit(f"error: could not install {selector}\n{detail}")


# --------------------------------------------------------------------------- #
# config.toml editing
# --------------------------------------------------------------------------- #

def strip_section(text: str, section: str) -> str:
    """Remove [section] and any [section.*] subtables, leaving the rest intact.

    Hand-rolled rather than using a TOML library on purpose: tomllib is read-only
    and there is no writer in the stdlib, so a library approach would force users
    to `pip install` something before they can install anything. We only ever own
    one well-known table, which makes a section-scoped text edit safe.
    """
    out, skipping = [], False
    header = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*$")
    for line in text.splitlines(keepends=True):
        m = header.match(line)
        if m:
            name = m.group(1).strip()
            skipping = name == section or name.startswith(section + ".")
        if not skipping:
            out.append(line)
    return "".join(out)


def write_mcp_block(key: str, server: str, workspace: str) -> None:
    url = f"{server.rstrip('/')}/memory/mcp/{workspace}"
    # http_headers, NOT bearer_token: Codex rejects bearer_token for HTTP MCP
    # servers. Putting the literal key here (rather than an env var) is what makes
    # recall/expand work in the VS Code panel too, since GUI hosts do not pass the
    # user's shell environment through to plugins.
    block = (
        f"[{MCP_SECTION}]\n"
        f'url = "{url}"\n'
        f'http_headers = {{ Authorization = "Bearer {key}" }}\n'
    )

    existing = ""
    if os.path.exists(CODEX_CONFIG):
        with open(CODEX_CONFIG) as f:
            existing = f.read()
        backup(CODEX_CONFIG)

    cleaned = strip_section(existing, MCP_SECTION).rstrip()
    body = (cleaned + "\n\n" + block) if cleaned else block

    os.makedirs(os.path.dirname(CODEX_CONFIG), exist_ok=True)
    with open(CODEX_CONFIG, "w") as f:
        f.write(body)
    os.chmod(CODEX_CONFIG, 0o600)
    print(f"  wrote [{MCP_SECTION}] into {CODEX_CONFIG}")


def write_creds(key: str, server: str) -> None:
    creds = load_json(CREDS)
    creds["api_key"] = key
    creds["server_url"] = server
    backup(CREDS)
    os.makedirs(os.path.dirname(CREDS), exist_ok=True)
    with open(CREDS, "w") as f:
        json.dump(creds, f, indent=2)
    os.chmod(CREDS, 0o600)
    print(f"  wrote {CREDS}")


# --------------------------------------------------------------------------- #
# install / uninstall
# --------------------------------------------------------------------------- #

def install(key: str, server: str, workspace: str, source: str, path_fix: bool) -> None:
    codex, on_path = find_codex()
    print(f"codex    : {codex}{'' if on_path else '  (not on PATH)'}")
    print(f"server   : {server}")
    print(f"workspace: {workspace}\n")

    print("1/5 PATH")
    if on_path:
        print("  codex is already on your PATH")
    elif path_fix:
        ensure_on_path(codex)
    else:
        print(f"  skipped (--no-path-fix); invoke codex as {codex}")

    print("2/5 marketplace")
    marketplace = ensure_marketplace(codex, source)

    print("3/5 plugin")
    ensure_plugin(codex, marketplace)

    print("4/5 credentials")
    write_creds(key, server)

    print("5/5 recall/expand MCP server")
    write_mcp_block(key, server, workspace)

    invoke = "codex" if (on_path or path_fix) else codex
    print("\n✅ Installed. One step left, and only you can do it:\n")
    print(f"     {invoke}")
    print("\n   Codex shows a Trust dialog listing three hooks — SessionStart,")
    print("   UserPromptSubmit and Stop. Press 't' to trust all, then quit.")
    print("   Required once. Codex has no flag for this and the trust hash is")
    print("   internal, so no installer can do it for you.\n")
    print("   Then: memory injection and capture run automatically, in the CLI and")
    print("   the VS Code Codex panel alike.")
    print("   Verify with: recall <a topic you've worked on>")
    print("   Tip: /catchup for a grounded catch-up on recent work.")


def uninstall(source: str) -> None:
    codex, _ = find_codex()

    name = marketplace_name(codex, source)
    if name:
        proc = run([codex, "plugin", "remove", f"{PLUGIN_NAME}@{name}"], check=False)
        print(f"  removed plugin {PLUGIN_NAME}@{name}"
              if proc.returncode == 0 else f"  plugin {PLUGIN_NAME}@{name} not installed")

    if os.path.exists(CODEX_CONFIG):
        with open(CODEX_CONFIG) as f:
            existing = f.read()
        cleaned = strip_section(existing, MCP_SECTION)
        if cleaned != existing:
            backup(CODEX_CONFIG)
            with open(CODEX_CONFIG, "w") as f:
                f.write(cleaned.rstrip() + "\n")
            os.chmod(CODEX_CONFIG, 0o600)
            print(f"  removed [{MCP_SECTION}] from {CODEX_CONFIG}")

    print("\n✅ Removed the Assertion plugin and MCP server from Codex.")
    print(f"   Left in place on purpose: your key at {CREDS}, the registered")
    print("   marketplace, and the PATH line in your shell profile. Delete those")
    print("   by hand if you want them gone.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Set up Assertion memory for Codex.")
    ap.add_argument("--key", help="API key (else prompts / reads ASSERTION_API_KEY)")
    ap.add_argument("--server", default=PROD, help=f"backend base URL (default {PROD})")
    ap.add_argument("--workspace", default="default", help="workspace / tree (default: default)")
    ap.add_argument("--marketplace-source", default=MARKETPLACE_SOURCE,
                    help="plugin marketplace git URL or local path")
    ap.add_argument("--no-path-fix", action="store_true",
                    help="never modify shell rc files")
    ap.add_argument("--uninstall", action="store_true",
                    help="remove what this installer added")
    args = ap.parse_args()

    if args.uninstall:
        uninstall(args.marketplace_source)
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

    install(key, args.server.rstrip("/"), args.workspace,
            args.marketplace_source, not args.no_path_fix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
