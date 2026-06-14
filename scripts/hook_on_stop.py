#!/usr/bin/env python3
"""Claude Code Stop hook → Assertion memory /update.

Runs when the assistant finishes a turn. Reads the transcript, extracts the latest
(user, assistant) text pair, and POSTs it to the backend so the shared memory tree
grows. Stdlib-only (runs on the system python3 — no deps). Fail-open: never blocks
the session if the backend is slow or down.

Env (the URL is set inline by the plugin's hook command; you only set the key):
  ASSERTION_API_KEY     your Assertion api_key  (fallback: CONTEXT_TREE_API_KEY)
  ASSERTION_UPDATE_URL  backend /update URL     (fallback: CONTEXT_TREE_UPDATE_URL)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.request

# Target defaults to PROD; one env var (ASSERTION_SERVER_URL) redirects all hooks to dev.
_BASE = (os.environ.get("ASSERTION_SERVER_URL")
         or os.environ.get("CONTEXT_TREE_SERVER_URL")
         or "https://memory.assertion-ai.com").rstrip("/")
_PREFIX = (os.environ.get("ASSERTION_PATH_PREFIX")
           or os.environ.get("CONTEXT_TREE_PATH_PREFIX") or "/memory").rstrip("/")
UPDATE_URL = (os.environ.get("ASSERTION_UPDATE_URL")
              or os.environ.get("CONTEXT_TREE_UPDATE_URL")
              or f"{_BASE}{_PREFIX}/update")
TIMEOUT_SECONDS = 5  # don't block Claude Code if the server is down


def _read_focus(session_id: str):
    """Read this session's current focus anchor (where work is landing), written by the
    UserPromptSubmit hook. Passed to /update so the backend anchors placement there."""
    safe = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")[:64] or "default"
    path = os.path.join(tempfile.gettempdir(), f"assertion_session_{safe}.json")
    try:
        with open(path) as f:
            return (json.load(f) or {}).get("focus")
    except Exception:
        return None


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                parts.append(b.get("text", ""))
        return "\n".join(p for p in parts if p)
    return ""


def extract_latest_turn(transcript_path: str) -> tuple[str, str]:
    """Walk the JSONL and return (user_text, assistant_text) for the most recent
    user → assistant exchange."""
    user_text = ""
    assistant_parts: list[str] = []
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = d.get("type")
                msg = d.get("message", {}) or {}
                if t == "user":
                    content = _extract_text(msg.get("content"))
                    stripped = content.strip()
                    if stripped.startswith("<command-") and stripped.endswith(">"):
                        continue
                    if stripped.startswith("[TOOL_RESULT]"):
                        continue
                    if not stripped:
                        continue
                    user_text = content
                    assistant_parts = []
                elif t == "assistant":
                    text = _extract_text(msg.get("content"))
                    if text.strip():
                        assistant_parts.append(text)
    except (FileNotFoundError, OSError):
        return "", ""
    return user_text, "\n".join(assistant_parts)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    transcript_path = payload.get("transcript_path")
    if not transcript_path:
        return 0

    user_text, assistant_text = extract_latest_turn(transcript_path)
    if not user_text and not assistant_text:
        return 0

    api_key = os.environ.get("ASSERTION_API_KEY") or os.environ.get("CONTEXT_TREE_API_KEY", "")
    if not api_key:
        # Don't post unauthenticated (it would 401 and silently drop the turn).
        # Warn loudly so a misconfigured setup is visible, not a quietly empty tree.
        sys.stderr.write(
            "Assertion memory: ASSERTION_API_KEY not set — capture is OFF for this turn.\n"
            "Add it to ~/.claude/settings.json under \"env\" so it reaches both the tools and the hook.\n")
        return 0
    update = {"user_text": user_text, "assistant_text": assistant_text}
    sid = payload.get("session_id")
    if sid:
        update["session_id"] = sid   # stamps last_session on touched nodes (focus attribution)
    focus = _read_focus(sid)
    if focus:
        update["focus"] = focus      # anchor placement to where this session is working
    body = json.dumps(update).encode()
    headers = {"Content-Type": "application/json", "x-api-key": api_key}
    req = urllib.request.Request(UPDATE_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            resp.read()
    except Exception:
        pass  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
