#!/usr/bin/env python3
"""Assertion memory UserPromptSubmit hook — the read side of the attention-following
window. Every prompt:

  A. AWARENESS    — inject L1/L2 nodes changed since last sync (cross-session updates)
  B. INVALIDATE   — a changed node X refreshes any lens that is X or X's direct child (one hop);
                    re-fetch + re-append (supersedes the stale copy; append-only)
  C. RECALL       — PRIMARY: semantic search (/memory/search) on the user's actual prompt →
                    ranked seeds + one-hop children (follows what you ASKED). Falls back to the
                    write-following ZOOM-IN (focus = deepest most-recent node, show its layer)
                    only when the search endpoint is unavailable/empty.
  RE-BASELINE     — a brand-new L1 (new workstream) → re-inject the L1/L2 map to re-orient

All injected append-only (prompt cache stays warm). State in assertion_session_<sid>.json =
{last_seen_turn, focus, lenses:{anchor: ancestor_path}}. Stdlib-only; fail-open (any error → 0).

Env: ASSERTION_API_KEY / ASSERTION_SERVER_URL (default https://memory.assertion-ai.com),
     ASSERTION_PATH_PREFIX (/memory), ASSERTION_WORKSPACE (default).
"""
from __future__ import annotations

import concurrent.futures
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


# Cursor has no per-prompt context-injection channel (beforeSubmitPrompt can only
# permit/block), so — like claude-mem — we deliver the attention-lens deltas by writing
# a Cursor Rules file the agent auto-loads. It's refreshed every prompt and accumulates
# the session's lens updates (the working-set base still rides sessionStart additionalContext).
_RULES_MAX_CHARS = 12000


def _write_cursor_rules(project_dir: str, sections_accum: list) -> None:
    if not project_dir or not sections_accum:
        return
    try:
        rdir = os.path.join(project_dir, ".cursor", "rules")
        os.makedirs(rdir, exist_ok=True)
        body = "\n\n".join(sections_accum).strip()
        if len(body) > _RULES_MAX_CHARS:
            body = body[-_RULES_MAX_CHARS:]
        doc = (
            "---\n"
            "description: Assertion project memory — live updates for your current work\n"
            "alwaysApply: true\n"
            "---\n"
            "Live updates from the shared project-memory tree, refreshed as you work. "
            "Treat as background you already know; cite node ids like [n0042].\n\n"
            + body + "\n"
        )
        with open(os.path.join(rdir, "assertion-memory.mdc"), "w") as f:
            f.write(doc)
    except Exception:
        pass


def main() -> int:
    try:
        session_id = "default"
        prompt = ""
        is_cursor = False
        project_dir = None
        try:
            payload = json.loads(sys.stdin.read() or "{}")
            # Cursor's beforeSubmitPrompt has no session_id — it keys turns by conversation_id;
            # both this hook and the capture hook fall back to it so their state files match.
            session_id = payload.get("session_id") or payload.get("conversation_id") or "default"
            prompt = payload.get("prompt") or ""   # stashed below as the capture hook's user_text
            # Detect Cursor ONLY by `cursor_version` (Cursor-exclusive, always present) so this
            # can't misfire on a Claude/Codex prompt payload.
            is_cursor = bool(payload.get("cursor_version"))
            # Cursor Rules files are project-scoped; find the project root for the rules write.
            project_dir = ((payload.get("workspace_roots") or [None])[0]
                           or os.environ.get("CURSOR_PROJECT_DIR")
                           or os.environ.get("CLAUDE_PROJECT_DIR"))
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
        # Fork-join: /working-set/delta (cross-session deltas + focus) and /search (prompt-driven
        # recall) share no inputs or outputs, so fire both concurrently — the per-prompt hook then
        # waits ~max(delta, search) instead of the sum. Blocking urllib calls release the GIL during
        # the network wait, so threads parallelize fine. stdlib-only (concurrent.futures).
        _pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        _search_fut = (_pool.submit(_get_json, "/search?" + urllib.parse.urlencode({"q": prompt[:2000]}))
                       if prompt.strip() else None)
        _delta_fut = _pool.submit(_get_json, "/working-set/delta?" + qs)
        data = _delta_fut.result()   # delta failure propagates → outer try fails open (return 0)
        current = int(data.get("n_turns_processed", 0))
        changed = data.get("changed") or []
        active = [c for c in changed if c.get("status") == "active"]
        by_id = {c["id"]: c for c in changed}

        sections: list[str] = []
        first_run = last is None
        # For the visible per-prompt banner (CLI terminal renders systemMessage; VS Code ignores
        # it — harmless). We surface only SUBSTANCE the user didn't have — the actual claims that
        # changed since they last worked here, and new-workstream re-orientation — NOT plumbing
        # (zoom/invalidate just feed the model detail; they're not news to the user). Tracked
        # alongside the existing injection logic, so what gets injected (and the cache) is untouched.
        update_claims: list[str] = []   # AWARENESS: human-readable L1/L2 cross-session changes
        rebaselined = False             # RE-BASELINE: new workstream

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

        # ---- C. PROMPT-DRIVEN RECALL (primary): semantic search on the user's actual prompt →
        # ranked seeds (each with its one-hop children). This is the attention-following window
        # following what you ASKED, not just where capture last wrote. Fires every prompt incl.
        # the first; fail-open. Falls back to the write-following zoom below only if the search
        # endpoint is unavailable (e.g. not yet deployed → 404) or returns nothing. ----
        recall_injected = False
        recall_seeds: list = []   # (id, claim) of surfaced seeds, for the visible banner
        recall_error = None       # set if /search FAILED — distinguishes false-silence from below-floor
        if _search_fut is not None:
            try:
                res = _search_fut.result()   # already in flight since the top (ran during delta)
                results = res.get("results") or []
                if results:
                    lines = []
                    for r in results:
                        lines.append(f"[{r['id']}] (L{r.get('level')}) {r['claim']}")
                        for c in (r.get("children") or [])[:4]:
                            lines.append(f"    └ [{c['id']}] {c['claim']}")
                    sections.append(
                        "<assertion_recall>\n"
                        "Relevant prior memory for what you're working on (cite the ids you actually "
                        "use; call recall/expand to go deeper):\n"
                        + "\n".join(lines) + "\n</assertion_recall>")
                    recall_injected = True
                    recall_seeds = [(r["id"], r.get("claim") or "") for r in results]
            except Exception as e:
                recall_error = (str(e) or "error")[:80]
        _pool.shutdown(wait=False)   # both futures consumed (delta above, search here)

        # ---- C (fallback). ZOOM-IN write-following: anchor on the focus's PARENT and show its
        # children. Only when prompt-driven recall didn't fire (endpoint absent/empty). ----
        if not recall_injected and not first_run and focus_meta and focus_meta.get("level", 0) > 2:
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
                    rebaselined = True
            except Exception:
                pass

        # ---- A. AWARENESS: L1/L2 changes since last sync ----
        sig = [c for c in changed if c.get("level") in (1, 2)]
        if not first_run and sig:
            # Stash (id, claim) for the visible banner — substance with a verifiable handle the
            # user can act on ("expand [n0269]"), mirroring the session-start recap. Not a count.
            update_claims = [(c["id"], c["claim"]) for c in sig
                             if c.get("status") == "active" and c.get("claim")]
            lines = []
            for c in sig:
                tag = "" if c.get("status") == "active" else "/superseded"
                lines.append(f"[{c['id']}] (L{c['level']}{tag}) {c['claim']}")
            sections.insert(0,
                "<assertion_memory_updates>\n"
                "Significant shared-memory updates since you last synced (other sessions or your own "
                "prior turns may have made these). Treat as background you now know.\n\n"
                + "\n".join(lines) + "\n</assertion_memory_updates>")

        # On Cursor, accumulate this turn's lens sections across the session so the rules file
        # is a growing snapshot (Cursor re-reads it whole each prompt), bounded by char cap.
        accum = (state.get("cursor_sections") or []) if is_cursor else []
        if is_cursor and sections:
            accum = (accum + sections)[-25:]

        # persist state for Stop hook (focus + prompt) and next prompt (cursor, lenses).
        # `prompt` is read by the Stop hook as Codex's user_text (harmless/unused on Claude).
        try:
            with open(sp, "w") as f:
                st = {"last_seen_turn": current, "focus": focus, "lenses": lenses, "prompt": prompt,
                      "recall_surfaced": [sid for sid, _ in recall_seeds]}  # for the Stop-hook assist log
                if is_cursor:
                    st["cursor_sections"] = accum
                json.dump(st, f)
        except Exception:
            pass

        # Inject the lens deltas. Claude Code/Codex take additionalContext via stdout. Cursor's
        # beforeSubmitPrompt can't inject through stdout, so we write the deltas to a Cursor Rules
        # file (auto-loaded, refreshed per prompt) and just permit the prompt.
        if is_cursor:
            _write_cursor_rules(project_dir, accum)
            sys.stdout.write(json.dumps({"continue": True}))
        else:
            out = {}
            if sections:
                out["hookSpecificOutput"] = {
                    "hookEventName": "UserPromptSubmit", "additionalContext": "\n\n".join(sections)}
            # Visible banner (CLI renders systemMessage; VS Code GUI ignores it — harmless). Priority:
            #   recall-fired  → the per-turn 'what memory am I using' signal (closes the observability gap)
            #   recall-error  → distinguishes a FAILED search (false silence) from a real below-floor miss
            #   awareness     → cross-session claims the user didn't have
            #   rebaseline    → new workstream
            # Silent on a genuine below-floor miss, so the mapping is unambiguous:
            #   '🧠 recalled N' = fired · '⚠️ recall unavailable' = errored · (no banner) = nothing relevant.
            if recall_seeds:
                shown = recall_seeds[:3]
                body = "\n".join(
                    f"  • [{nid}] {cl if len(cl) <= 100 else cl[:97] + '…'}" for nid, cl in shown)
                more = len(recall_seeds) - len(shown)
                if more > 0:
                    body += f"\n  • …and {more} more"
                out["systemMessage"] = f"🧠 recalled {len(recall_seeds)} node(s) for this turn:\n" + body
            elif recall_error:
                out["systemMessage"] = f"⚠️ memory recall unavailable this turn ({recall_error})"
            elif update_claims:
                shown = update_claims[:3]
                body = "\n".join(
                    f"  • [{nid}] {cl if len(cl) <= 110 else cl[:107] + '…'}" for nid, cl in shown)
                more = len(update_claims) - len(shown)
                if more > 0:
                    body += f"\n  • …and {more} more"
                out["systemMessage"] = "🌳 Updated since you last worked here:\n" + body
            elif rebaselined:
                out["systemMessage"] = "🌳 New workstream detected — re-oriented to the current project map."
            if out:
                sys.stdout.write(json.dumps(out))
    except Exception:
        return 0  # fail-open
    return 0


if __name__ == "__main__":
    sys.exit(main())
