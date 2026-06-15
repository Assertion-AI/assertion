# Assertion memory — Codex bundle

Runs the same Assertion memory engine under **OpenAI Codex** as under Claude Code.
**One copy of the logic:** the hooks invoke the shared scripts in `../scripts/`, which
auto-detect Codex vs Claude Code from the hook stdin shape. No duplicated code.

## Surface coverage (all verified on codex 0.139.0)
| Codex surface | Memory works? | Mechanism |
|---|---|---|
| **CLI, interactive** (`codex`) | ✅ | plugin hooks fire (inline `config.toml` hooks also work here) |
| **VS Code extension** | ✅ | plugin hooks fire after a one-time per-hook **Trust** toggle in the panel |
| CLI headless (`codex exec`) | ❌ | app-server path has no lifecycle-hook engine |
| Cloud / web | ❌ | runs on OpenAI's machines; local hooks can't reach it |

**Key lesson:** distribute as an **installed + enabled plugin** (marketplace → `codex plugin add`),
NOT loose `config.toml` hooks. Inline `[[hooks.*]]` tables fire only in the interactive CLI TUI;
a plugin's `hooks.json` fires in the CLI **and** the VS Code extension. Both proven with a
touch-probe (all three of SessionStart/UserPromptSubmit/Stop fired in each).

## How it maps (Codex ≈ Claude Code)
| Hook | Codex stdin | What the shared script does |
|------|-------------|------------------------------|
| `SessionStart` | `source` | fetch working set → inject via `hookSpecificOutput.additionalContext` (unchanged script) |
| `UserPromptSubmit` | `prompt`, `session_id` | run the attention lens → inject; **stash `prompt`** so Stop can use it |
| `Stop` | `last_assistant_message`, `session_id` | POST `(user_text=stashed prompt, assistant_text=last_assistant_message)` to `/memory/update` |

Backend (categorize / belief-revision / sweep on Claude opus + OpenAI embeddings) is
unchanged and agent-agnostic.

## Install (as a Codex plugin — the path that actually fires hooks)
Codex loads lifecycle hooks **only from an installed + enabled plugin** (or an
interactive TUI config layer). Loose `hooks.json` files are ignored, and **`codex exec`
fires no lifecycle hooks at all** — verified with a bare `touch` probe (valid config,
trust-bypass on, model ran, zero markers). So this is installed and used like
claude-mem's Codex integration.

1. Set env (in your shell or Codex profile):
   ```bash
   export ASSERTION_SCRIPTS_DIR="/abs/path/to/assertion-plugin/scripts"
   export ASSERTION_API_KEY="<your key>"
   export ASSERTION_SERVER_URL="https://auto-insight-product-dev-jbdf42voqq-uc.a.run.app"  # dev
   export ASSERTION_WORKSPACE="dev-<name>"   # NEVER 'default' on dev
   ```
2. Register this bundle as a local marketplace and enable the plugin:
   ```bash
   codex plugin marketplace add /abs/path/to/assertion-plugin/codex
   codex            # interactive TUI, then: /plugins → enable "assertion-memory"
   ```
   (`plugin.json` here is the Codex manifest; its `"hooks": "./hooks.json"` is the same
   shape as the Claude Code plugin and points at the same shared `../scripts`.)
3. Add the MCP server from `codex/config.toml.example` to `~/.codex/config.toml`.
4. Use Codex **interactively** (`codex`, not `codex exec`).

### Alternative (no plugin install): inline hooks in `~/.codex/config.toml`
For users who can't install plugins, Codex also reads inline `[[hooks.*]]` tables from a
trusted config layer. Note the array-of-tables shape — each event needs its own matcher
group **before** its handler list, or config fails to parse:
```toml
[[hooks.SessionStart]]
matcher = "startup|resume|clear|compact"
[[hooks.SessionStart.hooks]]
type = "command"
command = "python3 \"$ASSERTION_SCRIPTS_DIR/sessionstart_inject.py\""

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python3 \"$ASSERTION_SCRIPTS_DIR/userpromptsubmit_delta.py\""

[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = "python3 \"$ASSERTION_SCRIPTS_DIR/hook_on_stop.py\""
```
These still only fire in an **interactive** session, not under `codex exec`.

## Verify
- A `recall` returns **empty** (fresh `dev-<name>` workspace) — correct.
- Make a decision in one session, start another → it's there (cross-session memory).
- `curl -s -H "x-api-key: $ASSERTION_API_KEY" -H "X-Assertion-Workspace: $ASSERTION_WORKSPACE" \
    "$ASSERTION_SERVER_URL/memory/health"` → `status: ok`.

## Verification status (codex 0.139.0)
**Verified working end-to-end:**
- **CLI interactive:** real session captured "standardize on Kafka" into a fresh workspace
  (`Stop` hook) and a *new* session answered "Kafka" unprompted (`SessionStart` injection) —
  full read+write loop.
- **VS Code extension:** with the plugin installed+enabled, all three of
  SessionStart/UserPromptSubmit/Stop fired after a one-time per-hook **Trust** toggle in the
  Codex panel (touch-probe). The extension drives Codex via the app-server and *does* run
  enabled-plugin hooks.
- The shared scripts auto-detect Codex vs Claude Code; capture POSTs land in the right
  workspace (the `X-Assertion-Workspace` isolation fix).
- Backend MCP (Bearer auth + workspace-in-URL) on dev.

**Two gotchas, both settled:**
- **`codex exec` fires NO lifecycle hooks** (app-server path, no hook engine) — not a valid
  test harness. The IDE uses the same app-server but *does* honor enabled-plugin hooks once
  trusted, so exec's behavior doesn't generalize to the IDE.
- **Inline `[[hooks.*]]` in `config.toml` are TUI-only.** They never fired in the IDE; only
  a marketplace-installed, *enabled plugin's* `hooks.json` fires there. Ship as a plugin.

**recall/expand MCP tools — now supported (verified on dev).** Codex's HTTP MCP supports
only bearer-token/OAuth and silently drops custom headers, so the backend was aligned to the
MCP standard: it accepts `Authorization: Bearer <api_key>` and reads the workspace from the
URL path (`/memory/mcp/<workspace>`). Verified on dev (codex 0.139.0): Bearer auth works and
`recall` returns the correct workspace's tree (a control on `/memory/mcp/default` returned 0
hits, confirming the path actually routes the workspace). Wire it as:
`url = ".../memory/mcp/<workspace>"` + `bearer_token_env_var = "ASSERTION_API_KEY"`.
*(Live on dev now; prod after the `memory-v*` promote.)*

**Open productionization detail (not a blocker):** in the IDE the hooks run in the
extension's process env, which won't have `ASSERTION_API_KEY` exported. The real plugin's
`hooks.json` must therefore carry the key itself (embed in the command, or have the script
read a key file) rather than rely on a shell `export`. The CLI gets it from the launching
shell; the IDE does not.
