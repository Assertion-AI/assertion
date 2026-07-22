# Assertion — a second brain for your codebase

Gives **Claude Code**, **OpenAI Codex**, and **Cursor** memory that remembers the *why*
behind your decisions and the strategy across your project — and keeps it **current**,
superseding calls you've reversed instead of resurfacing them. It **recalls** that context
automatically as you work, into a shared, project-scoped tree. Reads run over a hosted MCP
endpoint (no local server); small hooks handle capture and context injection. One codebase
serves all three agents (single copy of the logic). By Assertion AI.

Get your key at https://studio.assertion-ai.com/connect. Requires a system `python3` (for the stdlib
hooks) — no other deps.

## Install — Claude Code

```
# 1) in Claude Code:
/plugin marketplace add Assertion-AI/assertion
/plugin install assertion@assertion-ai
```

**2) Add your key to `~/.claude/settings.json`** (create the file if needed):
```json
{
  "env": { "ASSERTION_API_KEY": "<your key>" }
}
```
The `env` block is the reliable way to provide the key — Claude Code injects it into
**both** the memory tools (MCP) **and** the capture hook, so your turns are actually
recorded. It also works **regardless of how you launch Claude Code** (terminal or app).

Get your key at https://studio.assertion-ai.com/connect. Restart Claude Code; run `/mcp` to confirm
`assertion` is connected, then try `recall <topic>`.

**Requirements:** a system `python3` (for the two stdlib hooks). No other deps — the
memory tools connect over HTTP.

> Prefer `~/.claude/settings.json` `env` over `export ASSERTION_API_KEY`. With a bare
> `export`, the key only reaches the plugin if you launch Claude Code from that same
> shell — set it in `settings.json` and capture works either way.
>
> **Upgrading:** use `/plugin update assertion@assertion-ai` (then reload) — `install`
> does not upgrade an already-installed plugin.

## Install — OpenAI Codex

```bash
# 1) install the plugin
codex plugin marketplace add Assertion-AI/assertion
codex plugin add assertion@assertion-ai

# 2) drop your key (one line — works in the CLI and the VS Code extension)
mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json
```

3. Use Codex **interactively** (`codex` in a terminal, or the VS Code Codex panel — *not*
   `codex exec`). On first run, toggle the three hooks **Trust** on when prompted (once).

Capture + injection then work against the same shared tree, in CLI and VS Code. Full
Codex details (recall/expand setup, dev override): [plugin/codex/README.md](plugin/codex/README.md).

## Install — Cursor

Cursor has no plugin marketplace, so it installs via a one-time script that wires its
`hooks.json` + `mcp.json` for you:

```bash
git clone https://github.com/Assertion-AI/assertion
cd assertion/plugin/cursor && python3 install_cursor.py   # paste your key when prompted
```
Then fully quit and reopen Cursor. The installer merges into any existing Cursor config
(it won't touch your other hooks or MCP servers), backs up what it changes, and defaults
to prod + the shared `default` workspace. Options (`--key`, `--workspace`, `--server`,
`--uninstall`) and a manual fallback: [plugin/cursor/README.md](plugin/cursor/README.md).

## What's included

- **MCP tools** — query and curate your memory from inside the agent, over
  `https://memory.assertion-ai.com`:
  - `recall` — find past work relevant to what you're doing now
  - `expand` — open up a point to see the detail beneath it
  - `evidence` — see the supporting detail behind a claim
  - `conflicts` — surface where the record disagrees with itself
  - `resolve` — settle a conflict and keep the memory coherent
  - `superseded` — see what's been replaced as decisions changed
  - `unsupersede` — bring back something that was replaced
- **Stop hook** — captures each finished turn into the tree.
- **SessionStart hook** — injects the project's working-set into context.

Both hooks **fail open**: if the backend is unreachable, your session is never blocked.

## Optional: show your memory space in the Claude Code status line

A permanent `📁 <space>` indicator at the bottom of your terminal — instant, local, per-session-accurate. In `~/.claude/settings.json`:

```json
"statusLine": {
  "type": "command",
  "command": "python3 ~/.claude/plugins/cache/assertion-ai/assertion/scripts/statusline_space.py"
}
```

(If you already have a statusline command, chain this after it.)
