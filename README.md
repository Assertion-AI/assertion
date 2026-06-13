# Assertion — persistent memory for your coding agent

Give Claude Code a memory that persists across sessions: it **recalls** prior work
and **auto-captures** each turn into a shared, project-scoped memory tree. Reads run
over a hosted MCP endpoint (no local server); two small hooks handle capture and
context injection. By [Assertion AI](https://assertion-ai.com).

## Install

```bash
# 1) in Claude Code:
/plugin marketplace add Assertion-AI/assertion
/plugin install assertion@assertion-ai

# 2) in your shell (add to ~/.zshrc to persist), then launch Claude Code from that terminal:
export ASSERTION_API_KEY=<your key>
```

Get your key at https://assertion-ai.com. Restart Claude Code; run `/mcp` to confirm
`assertion` is connected, then try `recall <topic>`.

**Requirements:** a system `python3` (for the two stdlib hooks). No other deps — the
memory tools connect over HTTP.

**Note:** launch Claude Code from a terminal where `ASSERTION_API_KEY` is exported
(a Dock/GUI launch won't see your shell env).

## What's included

- **MCP tools** (`recall`, `expand`, `evidence`, `conflicts`, `resolve`, `superseded`,
  `unsupersede`) over `https://memory.assertion-ai.com`.
- **Stop hook** — captures each finished turn into the tree.
- **SessionStart hook** — injects the project's working-set into context.

Both hooks **fail open**: if the backend is unreachable, your session is never blocked.
