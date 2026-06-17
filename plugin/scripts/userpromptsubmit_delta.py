#!/usr/bin/env python3
"""Assertion memory UserPromptSubmit hook — the read side of the attention-following
window. Every prompt, structurally (no lexical matching, no thresholds):

  focus   = deepest, most-recently-changed node (max turn, depth tiebreak)   [where work lands]
  A. AWARENESS    — inject L1/L2 nodes changed since last sync (cross-session updates)
  B. INVALIDATE   — a changed node X refreshes any lens that is X or X's direct child (one hop);
                    re-fetch + re-append (supersedes the stale copy; append-only)
  C. ZOOM-IN      — when focus is deep and not yet open, append its children (the next layer);
                    the session accumulates deep context as you descend
  RE-BASELINE     — a brand-new L1 (new workstream) → re-inject the L1/L2 map to re-orient

All injected append-only (prompt cache stays warm). State in assertion_session_<sid>.json =
{last_seen_turn, focus, lenses:{anchor: ancestor_path}}. Stdlib-only; fail-open (any error → 0).

Env: ASSERTION_API_KEY / ASSERTION_SERVER_URL (default https://memory.assertion-ai.com),
     ASSERTION_PATH_PREFIX (/memory), ASSERTION_WORKSPACE (default).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request

import _creds

_BASE = _creds.server_url()
_KEY = _creds.api_key()
_PREFIX = _creds.path_prefix()
_WS = _creds.workspace()


def _state_path(session_id: str) -> str:
    safe = "".join(c for c in (session_id or "default") if c.isalnum() or c in "-_")[:64] or "default"
    return os.path.join(tempfile.gettempdir(), f"assertion_session_{safe}.json")


def _get(path_qs: str, timeout: int = 5):
    req = urllib.request.Request(f"{_BASE}{_PREFIX}{path_qs}",
                                 headers={"x-api-key": _KEY, "X-Assertion-Workspace": _WS})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    return body


def _get_json(path_qs: str, timeout: int = 5):
    return json.loads(_get(path_qs, timeout))


def _expand(node_id: str):
    """Children of a node (the next layer down), active only."""
    try:
        d = _get_json("/expand?" + urllib.parse.urlencode({"node_id": node_id}))
        return d.get("children") or []
    except Exception:
        return []


def main() -> int:
    try:
        session_id = "default"
        prompt = ""
        is_cursor = False
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            # Cursor's beforeSubmitPrompt has no session_id — it keys turns by conversation_id;
            # both this hook and the capture hook fall back to it so their state files match.
            session_id = payload.get("session_id") or payload.get("conversation_id") or "default"
            prompt = payload.get("prompt") or ""   # stashed below as the capture hook's user_text
            is_cursor = bool(payload.get("cursor_version")) or payload.get("hook_event_name") == "beforeSubmitPrompt"
        except Exception:
            pass
        if not _BASE or not _KEY:
            return 0

        sp = _state_path(session_id)
        state = {}
        try:
            with open(sp) as f:
                state = json.load(f) or {}
        except Exception:
            state = {}
        last = state.get("last_seen_turn")
        focus = state.get("focus")
        lenses = state.get("lenses") or {}   # anchor_id -> ancestor_path

        qs = urllib.parse.urlencode({"since_turn": last if last is not None else 0, "levels": "all"})
        data = _get_json("/working-set/delta?" + qs)
        current = int(data.get("n_turns_processed", 0))
        changed = data.get("changed") or []
        active = [c for c in changed if c.get("status") == "active"]
        by_id = {c["id"]: c for c in changed}

        sections: list[str] = []
        first_run = last is None

        # focus = deepest most-recent active change FROM THIS SESSION (else keep prior).
        # Sourcing from own-session writes only is what stops a concurrent session's deep
        # writes from hijacking this session's focus. If this session hasn't written
        # (mine empty — including pre-attribution unstamped nodes), we KEEP the prior focus
        # rather than fall back to global; falling back would re-open the pollution. A brand
        # new session simply has no deep focus until it writes — correct (nothing to zoom yet).
        focus_meta = None
        mine = [c for c in active if c.get("session_id") == session_id]
        if mine:
            focus_meta = max(mine, key=lambda c: (c.get("turn", 0), c.get("level", 0)))
            focus = focus_meta["id"]

        # ---- B. INVALIDATE (one-hop): a changed X refreshes lenses == X or whose parent == X ----
        to_refresh: list[str] = []
        changed_ids = {c["id"] for c in changed}
        for anchor, anc in list(lenses.items()):
            parent = anc[0] if anc else None
            if anchor in changed_ids or (parent and parent in changed_ids):
                to_refresh.append(anchor)
        if not first_run:
            for anchor in to_refresh:
                kids = _expand(anchor)
                if kids:
                    lines = [f"  [{k['id']}] (L{k['level']}) {k['claim']}" for k in kids]
                    sections.append(
                        f"<assertion_lens_update anchor=\"{anchor}\">\n"
                        f"Updated detail under [{anchor}] (supersedes any earlier detail you saw for it):\n"
                        + "\n".join(lines) + "\n</assertion_lens_update>")

        # ---- C. ZOOM-IN: anchor on the focus's PARENT and show its children (the layer focus
        # lives in = focus + siblings). Works whether focus is a leaf or not; as you descend,
        # each new layer you enter gets appended once. ----
        if not first_run and focus_meta and focus_meta.get("level", 0) > 2:
            anc_path = focus_meta.get("ancestor_path") or []
            anchor = focus_meta.get("parent_id") or (anc_path[0] if anc_path else None)
            if anchor and anchor not in lenses:
                kids = _expand(anchor)
                if kids:
                    lines = [f"  [{k['id']}] (L{k['level']}) {k['claim']}" for k in kids]
                    sections.append(
                        f"<assertion_zoom anchor=\"{anchor}\">\n"
                        f"Zooming into the area you're working in (detail under [{anchor}]):\n"
                        + "\n".join(lines) + "\n</assertion_zoom>")
                lenses[anchor] = anc_path[1:]   # anchor's own ancestor path (grandparent up)

        # ---- RE-BASELINE: a brand-new L1 (new workstream) → re-inject the L1/L2 map ----
        if not first_run and any(c.get("level") == 1 for c in active):
            try:
                ws_md = _get("/working-set")
                if ws_md.strip():
                    sections.append(
                        "<assertion_rebaseline>\nNew workstream detected — re-orienting. "
                        "Current high-level map:\n\n" + ws_md.strip() + "\n</assertion_rebaseline>")
            except Exception:
                pass

        # ---- A. AWARENESS: L1/L2 changes since last sync ----
        sig = [c for c in changed if c.get("level") in (1, 2)]
        if not first_run and sig:
            lines = []
            for c in sig:
                tag = "" if c.get("status") == "active" else "/superseded"
                lines.append(f"[{c['id']}] (L{c['level']}{tag}) {c['claim']}")
            sections.insert(0,
                "<assertion_memory_updates>\n"
                "Significant shared-memory updates since you last synced (other sessions or your own "
                "prior turns may have made these). Treat as background you now know.\n\n"
                + "\n".join(lines) + "\n</assertion_memory_updates>")

        # persist state for Stop hook (focus + prompt) and next prompt (cursor, lenses).
        # `prompt` is read by the Stop hook as Codex's user_text (harmless/unused on Claude).
        try:
            with open(sp, "w") as f:
                json.dump({"last_seen_turn": current, "focus": focus,
                           "lenses": lenses, "prompt": prompt}, f)
        except Exception:
            pass

        # Cursor's beforeSubmitPrompt can only permit/block — it has no channel to inject
        # context (no additionalContext / updated_prompt), so we DON'T emit the lens delta there.
        # We still ran the logic above to stash the prompt + maintain focus state for capture;
        # on Cursor, mid-session orientation rides the sessionStart working-set injection instead.
        if sections and not is_cursor:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(sections)}}))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
