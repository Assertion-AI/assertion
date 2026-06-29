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
import tempfile
import time
import urllib.request

import _creds


def _mark_compaction(sid) -> None:
    """Append a wall-clock compaction ts to the session's marker file (read by the Stop hook → assist
    log cross-segment). Same epoch clock as node.updated_at, so the backend can tell which assisted
    facts predate the latest compaction. Separate file so the per-prompt state write can't clobber it.
    Best-effort."""
    if not sid:
        return
    try:
        safe = "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:64] or "default"
        p = os.path.join(tempfile.gettempdir(), f"assertion_compaction_{safe}.json")
        try:
            comps = json.load(open(p)).get("compactions") or []
        except Exception:
            comps = []
        comps.append(int(time.time()))
        json.dump({"compactions": comps[-50:]}, open(p, "w"))
    except Exception:
        pass


def main() -> int:
    try:
        payload = {}
        try:
            raw = sys.stdin.read()
            if raw:
                payload = json.loads(raw) or {}
        except Exception:
            payload = {}

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
        # Cursor's sessionStart expects a top-level {"additional_context": ...}; Claude Code
        # and Codex expect the nested hookSpecificOutput shape. Detect Cursor ONLY by
        # `cursor_version` — it's in every Cursor hook payload and never in Claude/Codex, so this
        # can't false-positive and flip an existing agent into the wrong output shape.
        is_cursor = bool(payload.get("cursor_version"))
        if is_cursor:
            out = {"additional_context": context}
        else:
            out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}
            # Visible recap → rendered to the USER via `systemMessage` (the working set above only
            # reaches the model's context, invisibly). systemMessage renders in the Claude Code
            # terminal; in the VS Code GUI it's a silent no-op (harmless). Skip on `compact`
            # (mid-work — don't interrupt); show on startup/resume/clear. Fail-open: any error
            # just omits the recap, never the (cache-warm) additionalContext above.
            src = (payload.get("source") or "").lower()
            if src == "compact":
                _mark_compaction(payload.get("session_id"))   # Claude Code / Codex compaction event
            if src != "compact":
                try:
                    rreq = urllib.request.Request(
                        f"{base}{prefix}/recap",
                        headers={"x-api-key": key, "X-Assertion-Workspace": workspace})
                    with urllib.request.urlopen(rreq, timeout=10) as rresp:
                        recap = rresp.read().decode("utf-8", "replace").strip()
                    if recap:
                        out["systemMessage"] = recap
                except Exception:
                    pass
        sys.stdout.write(json.dumps(out))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
