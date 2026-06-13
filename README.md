# Assertion — persistent memory for your coding agent

Give Claude Code a memory that persists across sessions: it **recalls** prior work
and **auto-captures** each turn into a shared, project-scoped memory tree. Reads run
over a hosted MCP endpoint (no local server); two small hooks handle capture and
context injection. By [Assertion AI](https://assertion-ai.com).

## Install

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

## What's included

- **MCP tools** (`recall`, `expand`, `evidence`, `conflicts`, `resolve`, `superseded`,
  `unsupersede`) over `https://memory.assertion-ai.com`.
- **Stop hook** — captures each finished turn into the tree.
- **SessionStart hook** — injects the project's working-set into context.

Both hooks **fail open**: if the backend is unreachable, your session is never blocked.
