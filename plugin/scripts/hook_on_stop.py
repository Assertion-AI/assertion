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
import re
import subprocess
import sys
import tempfile
import urllib.request

import _creds


def _detect_repo(cwd: str) -> str:
    """Provenance: the codebase this turn happened in — the reliable 'same project' signal for coding
    work (claims are semantically diverse but share one repo). Prefer the git remote (org/repo), else
    the git toplevel dir name; empty if not a git repo. Best-effort, never blocks the turn."""
    cwd = cwd or os.getcwd()
    try:
        url = subprocess.run(["git", "-C", cwd, "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, timeout=2).stdout.strip()
        if url:
            url = re.sub(r"^git@[^:]+:", "", url)       # git@github.com:org/repo.git -> org/repo.git
            url = re.sub(r"^https?://[^/]+/", "", url)   # https://github.com/org/repo.git -> org/repo.git
            return re.sub(r"\.git$", "", url)
    except Exception:
        pass
    try:
        top = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2).stdout.strip()
        if top:
            return os.path.basename(top)
    except Exception:
        pass
    return ""

# Target defaults to PROD; ASSERTION_SERVER_URL (or the credentials file) redirects to dev.
_BASE = _creds.server_url()
_PREFIX = _creds.path_prefix()
UPDATE_URL = (os.environ.get("ASSERTION_UPDATE_URL")
              or os.environ.get("CONTEXT_TREE_UPDATE_URL")
              or f"{_BASE}{_PREFIX}/update")
TIMEOUT_SECONDS = 5  # don't block Claude Code if the server is down


def _read_state(session_id: str) -> dict:
    """Read this session's state file (written by the UserPromptSubmit hook): the current
    focus anchor (where work is landing) and the latest user prompt. The prompt is used as
    Codex's user_text — Codex's Stop hook provides the assistant message but not the prompt,
    whereas Claude Code's Stop walks the transcript for both."""
    safe = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")[:64] or "default"
    path = os.path.join(tempfile.gettempdir(), f"assertion_session_{safe}.json")
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _read_compactions(session_id: str) -> list:
    """This session's compaction-event ts (written by the compaction hook / SessionStart-compact).
    Forwarded to the backend so the assist log can flag cross-segment assists. Separate file from
    the per-prompt state so the per-turn state write can't clobber it."""
    safe = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")[:64] or "default"
    path = os.path.join(tempfile.gettempdir(), f"assertion_compaction_{safe}.json")
    try:
        with open(path) as f:
            return (json.load(f) or {}).get("compactions") or []
    except Exception:
        return []


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

    # Cursor keys turns by conversation_id (no session_id); fall back so the state file written
    # by the prompt hook is found.
    sid = payload.get("session_id") or payload.get("conversation_id")

    # --- Client LABEL: detect by the most-exclusive input signal (decoupled from the capture
    # source below). ORDER MATTERS: `transcript_path` is Claude-exclusive and MUST be tested before
    # `last_assistant_message` (Claude Code now sends both), or Claude turns get mislabeled `codex`.
    #   - Cursor's afterAgentResponse carries `cursor_version` (Cursor-exclusive).
    #   - Claude Code's Stop carries `transcript_path`.
    #   - Codex's Stop carries `last_assistant_message` and no `transcript_path`.
    if payload.get("cursor_version") is not None:
        client = "cursor"
    elif payload.get("transcript_path"):
        client = "claude"
    elif payload.get("last_assistant_message") is not None:
        client = "codex"
    else:
        return 0

    # --- Capture SOURCE, decoupled from the label. Prefer the INLINE assistant message
    # (`last_assistant_message`, or Cursor's `text`) + the prompt the submit-hook stashed: these
    # are present in the Stop payload itself, so they're immune to the transcript-flush race that
    # made claude-vscode silently drop turns (VSCode can fire Stop before the final assistant block
    # is written to the .jsonl). This is the robust v0.2.0 capture path. For Claude we ALSO read the
    # transcript and keep its fuller multi-message narration WHEN it already contains the final
    # answer (fully flushed); if the transcript is empty or only partially flushed, the inline answer
    # is authoritative. Net: robust like v0.2.0, plus Claude's richer narration when available. ---
    inline = payload.get("last_assistant_message") or payload.get("text") or ""
    user_text = _read_state(sid).get("prompt") or ""
    assistant_text = inline
    if payload.get("transcript_path"):
        t_user, t_assistant = extract_latest_turn(payload["transcript_path"])
        if not user_text.strip():
            user_text = t_user
        if not inline.strip():
            assistant_text = t_assistant                      # older Claude Code (no inline) → transcript
        elif inline.strip() in t_assistant:
            assistant_text = t_assistant                      # fully flushed → keep richer narration
        else:
            assistant_text = (f"{t_assistant}\n{inline}".strip()
                              if t_assistant.strip() else inline)  # partial/empty flush → inline wins

    if not user_text and not assistant_text:
        return 0

    api_key = _creds.api_key()
    if not api_key:
        # Don't post unauthenticated (it would 401 and silently drop the turn).
        # Warn loudly so a misconfigured setup is visible, not a quietly empty tree.
        sys.stderr.write(
            "Assertion memory: ASSERTION_API_KEY not set — capture is OFF for this turn.\n"
            "Add it to ~/.claude/settings.json under \"env\" so it reaches both the tools and the hook.\n")
        return 0
    update = {"user_text": user_text, "assistant_text": assistant_text}
    if sid:
        update["session_id"] = sid   # stamps last_session on touched nodes (focus attribution)
    focus = _read_state(sid).get("focus")
    if focus:
        update["focus"] = focus      # anchor placement to where this session is working
    surfaced = _read_state(sid).get("recall_surfaced")
    if surfaced:
        update["recall_surfaced"] = surfaced  # node ids this turn's recall surfaced → assist log (∩ cited)
    comps = _read_compactions(sid)
    if comps:
        update["compactions"] = comps         # this session's compaction ts → assist-log cross-segment
    repo = _detect_repo(payload.get("cwd") or os.getcwd())
    if repo:
        update["repo"] = repo        # provenance: route/group this turn's nodes by codebase
    update["client"] = client                       # which IDE this turn came from (claude/cursor/codex)
    pv = _creds.plugin_version()
    if pv:
        update["plugin_version"] = pv               # installed plugin version → studio upgrade nudge
    body = json.dumps(update).encode()
    # Send the workspace header so the WRITE lands in the same workspace the reads use.
    # Without it the backend defaults to "default" — which would route a dev's captures
    # (ASSERTION_WORKSPACE=dev-<name>) into the prod tree even though their reads are isolated.
    workspace = _creds.workspace()
    headers = {"Content-Type": "application/json", "x-api-key": api_key,
               "X-Assertion-Workspace": workspace}
    req = urllib.request.Request(UPDATE_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            resp.read()
    except Exception:
        pass  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
