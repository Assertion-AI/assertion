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
