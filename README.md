# Assertion — persistent memory for your coding agent

Give **Claude Code**, **OpenAI Codex**, and **Cursor** a memory that persists across
sessions: it **recalls** prior work and **auto-captures** each turn into a shared,
project-scoped memory tree. Reads run over a hosted MCP endpoint (no local server);
small hooks handle capture and context injection. One codebase serves all three agents
(single copy of the logic). By [Assertion AI](https://assertion-ai.com).

Get your key at https://assertion-ai.com. Requires a system `python3` (for the stdlib
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

Get your key at https://assertion-ai.com. Restart Claude Code; run `/mcp` to confirm
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

Cursor uses its own `hooks.json` + `mcp.json` (it has no plugin marketplace), so install
is a short manual copy. Full steps: [plugin/cursor/README.md](plugin/cursor/README.md).

```bash
# drop your key (Cursor runs hooks without your shell env, so it goes in a file)
mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json
```
Then copy `plugin/cursor/hooks.json` into `.cursor/hooks.json` (replacing the absolute
scripts path), merge `plugin/cursor/mcp.json` into `~/.cursor/mcp.json`, and reload Cursor.

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
