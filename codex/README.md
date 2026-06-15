# Assertion memory for OpenAI Codex

Persistent, structured project memory for Codex. Each turn is captured into a shared,
project-scoped tree; at the start of every session the relevant part of that tree is
injected back so Codex already knows your prior decisions and context.

By default it uses **prod** (`memory.assertion-ai.com`) and the shared **`default`**
workspace — the same tree your other Assertion-memory agents read and write. You only
need an API key.

## What you get
- **SessionStart** — injects the working-set tree into the new session.
- **UserPromptSubmit** — runs the attention lens (zoom to what you're working on) and
  stashes the prompt for capture.
- **Stop** — captures the turn `(prompt, response)` into the tree.
- **`recall` / `expand` MCP tools** — query the tree on demand from inside Codex.

## Install (plugin — works in the Codex CLI and the VS Code extension)
```bash
codex plugin marketplace add /abs/path/to/assertion-plugin/codex
codex            # then: /plugins → enable "assertion-memory"
```
On first use Codex shows a **Trust** dialog listing the SessionStart/UserPromptSubmit/Stop
hooks — toggle each on. That's required once; afterwards the hooks run automatically (in
the terminal CLI and in the VS Code Codex panel alike).

Set your key once — this works in **both** the CLI and the VS Code extension (GUI hosts
don't pass your shell environment to hooks, so the key goes in a file, not `export`):
```bash
mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json
```
The hooks read the key from that file. Then add the MCP server (for `recall`/`expand`)
from `config.toml.example` to `~/.codex/config.toml` — it carries the same key as a literal
`bearer_token`, so it also works without env.

## Verify
- `recall` returns nodes from your `default` tree (the same memory you see elsewhere).
- Make a decision in one session; start a new one and ask about it — Codex answers from
  memory without you re-stating it.

## Where it works
| Codex surface | Works? |
|---|---|
| CLI, interactive (`codex`) | ✅ |
| VS Code extension | ✅ (after the one-time Trust toggle) |
| CLI headless (`codex exec`) | ❌ — no lifecycle-hook engine |
| Cloud / web | ❌ — runs on OpenAI's machines |
