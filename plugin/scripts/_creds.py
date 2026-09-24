#!/usr/bin/env python3
"""Shared credential/target resolution for the Assertion hooks.

Resolution order for each value:
  1. environment variable (ASSERTION_* then legacy CONTEXT_TREE_*)
  2. a credentials file
  3. a built-in default

Why the file: GUI hosts — notably the Codex VS Code extension — run hook commands
WITHOUT the user's shell environment, so an exported ASSERTION_API_KEY never reaches
them. The file makes the IDE one-step. Env always wins, so the CLI / Claude Code path
is unchanged (an exported key takes precedence over the file).

Credentials file (first one found), JSON:
  {"api_key": "...", "server_url": "...", "workspace": "..."}
  ~/.assertion/credentials.json
  ~/.codex/assertion.json     (handy place for Codex users)
Only api_key is needed; server_url defaults to prod and workspace to "default".
Stdlib-only.
"""
from __future__ import annotations

import json
import os

_FILES = ["~/.assertion/credentials.json", "~/.codex/assertion.json"]
_CACHE = None


def _file() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    for p in _FILES:
        try:
            with open(os.path.expanduser(p)) as f:
                d = json.load(f)
            if isinstance(d, dict):
                _CACHE = d
                return _CACHE
        except Exception:
            continue
    _CACHE = {}
    return _CACHE


def _resolve(env_names, file_key, default=""):
    for n in env_names:
        v = os.environ.get(n)
        if v:
            return v
    v = _file().get(file_key)
    return v if v else default


def api_key() -> str:
    return _resolve(["ASSERTION_API_KEY", "CONTEXT_TREE_API_KEY"], "api_key", "")


def server_url() -> str:
    return _resolve(["ASSERTION_SERVER_URL", "CONTEXT_TREE_SERVER_URL"],
                    "server_url", "https://memory.assertion-ai.com").rstrip("/")


def path_prefix() -> str:
    return _resolve(["ASSERTION_PATH_PREFIX", "CONTEXT_TREE_PATH_PREFIX"],
                    "path_prefix", "/memory").rstrip("/")


def workspace() -> str:
    return _resolve(["ASSERTION_WORKSPACE", "CONTEXT_TREE_WORKSPACE"], "workspace", "default")


_VERSION_CACHE = None


def plugin_version() -> str:
    """The installed plugin version, read from the plugin manifest (single source of truth).
    Scripts live in plugin/scripts/; the manifest is a sibling under .claude-plugin/ (Codex uses
    .codex-plugin/ — same version). Sent to the backend each turn so the studio page can show the
    user's version and nudge an upgrade. Empty string if it can't be read (treated as 'unknown')."""
    global _VERSION_CACHE
    if _VERSION_CACHE is not None:
        return _VERSION_CACHE
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in ("../.claude-plugin/plugin.json", "../.codex-plugin/plugin.json"):
        try:
            with open(os.path.normpath(os.path.join(here, rel))) as f:
                v = (json.load(f) or {}).get("version") or ""
            if v:
                _VERSION_CACHE = v
                return v
        except Exception:
            continue
    _VERSION_CACHE = ""
    return ""

def install_source() -> str:
    """Which copy of the plugin this is: the marketplace it was installed from, read from where the
    host unpacked it (`.../plugins/cache/<marketplace>/<plugin>/<version>/`). `claude-community` is
    the Claude Code catalog; `assertion-ai` is this GitHub repo. Only that one name is sent, never
    the path. Empty when the scripts don't live in a plugin cache (Cursor, a local checkout)."""
    parts = os.path.normpath(os.path.abspath(__file__)).split(os.sep)
    for i in range(len(parts) - 2):
        if parts[i] == "plugins" and parts[i + 1] == "cache":
            name = "".join(c for c in parts[i + 2].lower() if c.isalnum() or c in "-_.")[:40]
            return name
    return ""
