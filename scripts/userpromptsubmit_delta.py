#!/usr/bin/env python3
"""Assertion memory UserPromptSubmit hook — two jobs, both structural (no thresholds):

1. Cross-session awareness: inject the L1/L2 nodes changed since this session last synced,
   so a session in motion sees decisions made by other sessions without a restart. Injects
   only on real change; append-only, so the prompt cache stays warm.

2. Focus tracking (write-driven): focus = the deepest, most-recently-changed node in the
   tree (where work is landing) — read straight from the delta's turn/level numbers, no
   lexical matching. Written to the shared session state file so the Stop hook can pass it
   to /update, anchoring placement to where this session is working.

Stdlib-only; fail-open (any error → exit 0, no output, never blocks).

Env (URL set inline by the plugin's hook command; you only set the key):
  ASSERTION_API_KEY  / CONTEXT_TREE_API_KEY
  ASSERTION_SERVER_URL / CONTEXT_TREE_SERVER_URL   (default https://memory.assertion-ai.com)
  ASSERTION_PATH_PREFIX (default "/memory")   ASSERTION_WORKSPACE (default "default")
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
    return os.path.join(tempfile.gettempdir(), f"assertion_session_{safe}.json")


def main() -> int:
    try:
        session_id = "default"
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            session_id = payload.get("session_id") or "default"
        except Exception:
            pass

        base = (os.environ.get("ASSERTION_SERVER_URL")
                or os.environ.get("CONTEXT_TREE_SERVER_URL") or "https://memory.assertion-ai.com").rstrip("/")
        key = os.environ.get("ASSERTION_API_KEY") or os.environ.get("CONTEXT_TREE_API_KEY", "")
        if not base or not key:
            return 0
        prefix = (os.environ.get("ASSERTION_PATH_PREFIX")
                  or os.environ.get("CONTEXT_TREE_PATH_PREFIX") or "/memory").rstrip("/")
        workspace = (os.environ.get("ASSERTION_WORKSPACE")
                     or os.environ.get("CONTEXT_TREE_WORKSPACE") or "default")

        state_path = _state_path(session_id)
        state = {}
        try:
            with open(state_path) as f:
                state = json.load(f) or {}
        except Exception:
            state = {}
        last = state.get("last_seen_turn")
        focus = state.get("focus")

        # All-levels delta so we can see where deep writes landed (focus is structural).
        qs = urllib.parse.urlencode({"since_turn": last if last is not None else 0, "levels": "all"})
        req = urllib.request.Request(
            f"{base}{prefix}/working-set/delta?{qs}",
            headers={"x-api-key": key, "X-Assertion-Workspace": workspace})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))

        current = int(data.get("n_turns_processed", 0))
        changed = data.get("changed") or []

        # Focus = deepest, most-recently-changed node (where work is landing). Pure numbers:
        # max turn, tie-break deepest level. No match landed since last sync → keep prior focus.
        active = [c for c in changed if c.get("status") == "active"]
        if active:
            top = max(active, key=lambda c: (c.get("turn", 0), c.get("level", 0)))
            focus = top["id"]

        # Persist state for the Stop hook (focus) and next prompt (cursor).
        try:
            with open(state_path, "w") as f:
                json.dump({"last_seen_turn": current, "focus": focus}, f)
        except Exception:
            pass

        # Awareness injection: only L1/L2 changes, only after a baseline exists, only on change.
        sig = [c for c in changed if c.get("level") in (1, 2)]
        if last is None or not sig:
            return 0
        lines = []
        for c in sig:
            tag = "" if c.get("status") == "active" else "/superseded"
            lines.append(f"[{c['id']}] (L{c['level']}{tag}) {c['claim']}")
        context = (
            "<assertion_memory_updates>\n"
            "Significant shared-memory updates since you last synced (other sessions or your "
            "own prior turns may have made these). Treat as background you now know; drill in "
            "with the memory tools.\n\n"
            + "\n".join(lines)
            + "\n</assertion_memory_updates>"
        )
        sys.stdout.write(json.dumps(
            {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
