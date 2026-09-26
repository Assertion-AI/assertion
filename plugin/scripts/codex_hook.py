#!/usr/bin/env python3
"""Stable entry point for the Codex hooks: `codex_hook.py <script> [args...]`.

Codex keeps each plugin version in its own cache directory (<CODEX_HOME>/plugins/cache/<marketplace>/
<plugin>/<version>) and deletes the old one when the plugin is updated. A session that is already
open keeps the hook commands it loaded at launch, so a command that names a script inside the
version directory stops working the moment that directory is replaced: every hook in the open
session fails until Codex restarts, and /new does not help.

So the hook commands in codex/hooks.json never name a version. They run a copy of this file kept at
~/.assertion/bin/codex-hook, which finds the newest installed version at call time and runs the
requested script from it, with stdin and arguments passed straight through. The command strings
stay the same from version to version, so Codex does not ask to trust the hooks again on upgrade.

Each run also keeps that copy current (the newest version's codex_hook.py), which is how it gets
installed in the first place: the hook command falls back to this file inside the plugin when the
copy does not exist yet. ASSERTION_SCRIPTS_DIR, if set, is used as the scripts directory instead.
Stdlib-only; fail-open: when nothing resolves it exits 0 without output, so a session never breaks.
"""
from __future__ import annotations

import glob
import os
import re
import sys

STABLE = os.path.join(os.path.expanduser("~"), ".assertion", "bin", "codex-hook")


def _vkey(v: str):
    return tuple(int(x) if x.isdigit() else -1 for x in re.split(r"[.\-+]", v or "0"))


def _version_dirs() -> list[str]:
    """Installed version directories of this plugin, newest first. Anchored on the plugin directory
    this session was started from (PLUGIN_ROOT's parent, which survives an upgrade even though the
    version under it does not), else every marketplace's `assertion` plugin in the Codex cache."""
    parents = []
    for var in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        root = (os.environ.get(var) or "").rstrip("/")
        if root:
            parents.append(os.path.dirname(root))
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # <version>/scripts/.. = <version>
    parents.append(os.path.dirname(here))
    codex_home = os.environ.get("CODEX_HOME") or os.path.join(os.path.expanduser("~"), ".codex")
    parents += sorted(glob.glob(os.path.join(codex_home, "plugins", "cache", "*", "assertion")))
    seen, dirs = set(), []
    for parent in parents:
        if not os.path.isdir(parent) or parent in seen:
            continue
        seen.add(parent)
        vs = [os.path.join(parent, v) for v in os.listdir(parent) if re.match(r"^\d", v)]
        vs = [d for d in vs if os.path.isdir(os.path.join(d, "scripts"))]
        if vs:
            dirs += sorted(vs, key=lambda d: _vkey(os.path.basename(d)), reverse=True)
            break   # the first plugin directory that has a version wins; don't mix marketplaces
    return dirs


def resolve(script: str) -> str | None:
    """Absolute path of `script` in the newest installed version, or None."""
    if not re.fullmatch(r"[A-Za-z0-9_]+\.py", script or ""):
        return None
    override = os.environ.get("ASSERTION_SCRIPTS_DIR")
    if override:
        p = os.path.join(override, script)
        return p if os.path.isfile(p) else None
    for d in _version_dirs():
        p = os.path.join(d, "scripts", script)
        if os.path.isfile(p):
            return p
    return None


def refresh_stable(source: str) -> None:
    """Make ~/.assertion/bin/codex-hook a copy of `source` (the newest codex_hook.py). Atomic, so
    a hook running at the same moment sees the old copy or the new one, never half a file."""
    try:
        with open(source, "rb") as f:
            new = f.read()
        try:
            with open(STABLE, "rb") as f:
                if f.read() == new:
                    return
        except OSError:
            pass
        os.makedirs(os.path.dirname(STABLE), exist_ok=True)
        tmp = f"{STABLE}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            f.write(new)
        os.chmod(tmp, 0o755)
        os.replace(tmp, STABLE)
    except Exception:
        pass


def main(argv: list[str]) -> int:
    try:
        if len(argv) < 2:
            return 0
        target = resolve(argv[1])
        if not target:
            return 0
        newest = os.path.join(os.path.dirname(target), "codex_hook.py")
        if os.path.isfile(newest):
            refresh_stable(newest)
        root = os.path.dirname(os.path.dirname(target))
        env = dict(os.environ, PLUGIN_ROOT=root, CLAUDE_PLUGIN_ROOT=root)
        sys.stdout.flush()
        os.execve(sys.executable, [sys.executable, target] + argv[2:], env)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
