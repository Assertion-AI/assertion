#!/usr/bin/env python3
"""Assertion memory SessionStart hook → inject the working-set as session context.

Plugins don't auto-load a CLAUDE.md, so this hook fetches the project's working-set
from the backend and returns it as `additionalContext` — always fresh, no file on
disk. Stdlib-only; fail-open (any error → exit 0, no output, never blocks a session).

Env (you set the key; URL/workspace default to PROD and are overridable for dev):
  ASSERTION_API_KEY     your Assertion api_key  (fallback: CONTEXT_TREE_API_KEY)
  ASSERTION_SERVER_URL  backend base URL, default https://memory.assertion-ai.com (prod)
  ASSERTION_PATH_PREFIX optional, default "/memory"
  ASSERTION_WORKSPACE   optional workspace header, default "default"  (devs: dev-<name>)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import _creds


def main() -> int:
    try:
        try:
            sys.stdin.read()
        except Exception:
            pass

        base = _creds.server_url()
        key = _creds.api_key()
        if not base or not key:
            return 0

        prefix = _creds.path_prefix()
        workspace = _creds.workspace()
        url = f"{base}{prefix}/working-set"

        req = urllib.request.Request(url, headers={"x-api-key": key, "X-Assertion-Workspace": workspace})
        with urllib.request.urlopen(req, timeout=10) as resp:
            text = resp.read().decode("utf-8", "replace").strip()

        if not text:
            return 0

        context = (
            "<persistent_project_memory>\n"
            "Shared, structured memory of this project's work, accumulated across "
            "sessions and teammates. Treat it as background you already know; cite "
            "node ids like [n0042] and use the memory tools to drill in.\n\n"
            + text
            + "\n</persistent_project_memory>"
        )
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
        sys.stdout.write(json.dumps(out))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
