# Assertion — persistent memory for your coding agent

Give **Claude Code** and **OpenAI Codex** a memory that persists across sessions: it
**recalls** prior work and **auto-captures** each turn into a shared, project-scoped
memory tree. Reads run over a hosted MCP endpoint (no local server); small hooks handle
capture and context injection. One codebase serves both agents (single copy of the
logic). By [Assertion AI](https://assertion-ai.com).

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

## What's included

- **MCP tools** (`recall`, `expand`, `evidence`, `conflicts`, `resolve`, `superseded`,
  `unsupersede`) over `https://memory.assertion-ai.com`.
- **Stop hook** — captures each finished turn into the tree.
- **SessionStart hook** — injects the project's working-set into context.

Both hooks **fail open**: if the backend is unreachable, your session is never blocked.
