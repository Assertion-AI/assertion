#!/usr/bin/env python3
"""Assertion memory UserPromptSubmit hook → inject significant changes since last sync.

A session already in motion does not see decisions made by *other* concurrent
sessions (its working-set was injected at SessionStart and won't refresh until the
next startup/resume/clear/compact). This hook closes that gap: on each prompt it
asks the backend for L1/L2 nodes changed since this session last synced, and injects
only the delta as `additionalContext`.

Cheap by design: the backend delta is a tree read + filter (no LLM), and because it
is filtered to L1/L2, `changed` is empty on the vast majority of turns even as the
turn counter climbs — so injection (and prompt-cache disruption) happens only when a
genuinely significant decision lands. Stdlib-only; fail-open (any error → exit 0).

Env (URL set inline by the plugin's hook command; you only set the key):
  ASSERTION_API_KEY     your Assertion api_key  (fallback: CONTEXT_TREE_API_KEY)
  ASSERTION_SERVER_URL  backend base URL        (fallback: CONTEXT_TREE_SERVER_URL)
  ASSERTION_PATH_PREFIX optional, default "/memory"
  ASSERTION_WORKSPACE   optional workspace header, default "default"
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request


def _state_path(session_id: str) -> str:
    safe = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")[:64] or "default"
    return os.path.join(tempfile.gettempdir(), f"assertion_delta_{safe}.turn")


def main() -> int:
    try:
        session_id = "default"
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            session_id = payload.get("session_id") or "default"
        except Exception:
            pass

        base = (os.environ.get("ASSERTION_SERVER_URL")
                or os.environ.get("CONTEXT_TREE_SERVER_URL") or "").rstrip("/")
        key = os.environ.get("ASSERTION_API_KEY") or os.environ.get("CONTEXT_TREE_API_KEY", "")
        if not base or not key:
            return 0

        prefix = (os.environ.get("ASSERTION_PATH_PREFIX")
                  or os.environ.get("CONTEXT_TREE_PATH_PREFIX") or "/memory").rstrip("/")
        workspace = (os.environ.get("ASSERTION_WORKSPACE")
                     or os.environ.get("CONTEXT_TREE_WORKSPACE") or "default")

        state = _state_path(session_id)
        last = None
        try:
            with open(state) as f:
                last = int(f.read().strip())
        except Exception:
            last = None

        qs = urllib.parse.urlencode({"since_turn": last if last is not None else 0})
        url = f"{base}{prefix}/working-set/delta?{qs}"
        req = urllib.request.Request(url, headers={"x-api-key": key, "X-Assertion-Workspace": workspace})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))

        current = int(data.get("n_turns_processed", 0))
        changed = data.get("changed") or []

        # Always advance the baseline so we never re-inject the same delta twice.
        try:
            with open(state, "w") as f:
                f.write(str(current))
        except Exception:
            pass

        # First prompt of a session: SessionStart already injected the full working
        # set, so just record the baseline and inject nothing. Otherwise inject only
        # when something significant actually changed.
        if last is None or not changed:
            return 0

        lines = []
        for c in changed:
            tag = "" if c.get("status") == "active" else "/superseded"
            lines.append(f"[{c['id']}] (L{c['level']}{tag}) {c['claim']}")
        context = (
            "<assertion_memory_updates>\n"
            "Significant shared-memory updates since you last synced "
            "(other sessions or your own prior turns may have made these). "
            "Treat as background you now know; drill in with the memory tools.\n\n"
            + "\n".join(lines)
            + "\n</assertion_memory_updates>"
        )
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}
        sys.stdout.write(json.dumps(out))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
