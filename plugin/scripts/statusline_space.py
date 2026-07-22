#!/usr/bin/env python3
"""Optional Claude Code statusline segment: the current session's memory space,
permanently visible at the bottom of the terminal. Reads the plugin's per-session
state file (written by the prompt hook each turn) — no network, instant.

Setup — in ~/.claude/settings.json:
  "statusLine": {"type": "command",
                 "command": "python3 ~/.claude/plugins/cache/assertion-ai/assertion/scripts/statusline_space.py"}
(Or chain it after your existing statusline command.)
"""
import json
import os
import sys
import tempfile

try:
    payload = json.loads(sys.stdin.read() or "{}")
    sid = payload.get("session_id") or "default"
    safe = "".join(c for c in str(sid) if c.isalnum() or c in "-_")[:64] or "default"
    path = os.path.join(tempfile.gettempdir(), f"assertion_session_{safe}.json")
    space = (json.load(open(path)).get("last_space") or "").strip()
except Exception:
    space = ""

# "default" is the personal baseline in legacy orgs; empty = no data yet this session.
print(f"📁 {space}" if space and space != "default" else "📁 personal")
