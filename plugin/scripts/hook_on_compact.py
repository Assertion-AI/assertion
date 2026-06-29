#!/usr/bin/env python3
"""Assertion memory compaction hook — records a compaction event so the assist log can flag
CROSS-SEGMENT assists (memory carrying an exact fact across the lossy summary boundary, the
single-session analogue of cross-session). Wired to Cursor's `preCompact`; Claude Code / Codex
record the same marker via SessionStart(source=compact) in sessionstart_inject.py.

Appends a wall-clock ts (same epoch clock as node.updated_at) to the session's compaction-marker
file, which the Stop hook forwards to the backend. Stdlib-only; fail-open; observational (never
blocks the compaction)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    sid = payload.get("conversation_id") or payload.get("session_id")
    if sid:
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
    sys.stdout.write(json.dumps({"continue": True}))  # preCompact is observational — permit, don't block
    return 0


if __name__ == "__main__":
    sys.exit(main())
