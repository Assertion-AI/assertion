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

## Install (works in the Codex CLI and the VS Code extension)

Run this. It prompts for your API key and does everything else:

```bash
python3 install_codex.py
```

Then start Codex once and press **`t`** to trust the hooks:

```bash
codex
```

That's the whole install. Codex shows a **Trust** dialog listing the
SessionStart / UserPromptSubmit / Stop hooks — `t` trusts all three, then quit.
Required once, and it is the one step no installer can do for you: Codex has no
`--trust` flag, and the trusted-hash format is internal, so the installer does not
forge it. Afterwards the hooks run automatically, in the terminal CLI and the
VS Code Codex panel alike.

The installer needs no paths, no hand-written JSON and no TOML editing. It:

- finds the `codex` binary **even when it isn't on your `PATH`** (the standalone
  installer puts it in `~/.local/bin`, which a default macOS zsh does not search —
  the most common "install didn't work" report), and adds it to your shell profile
- registers the marketplace from its git URL, so there is no absolute path to supply
- installs the `assertion` plugin
- writes `~/.assertion/credentials.json` (mode `0600`) — where the capture/inject
  hooks read your key, since GUI hosts don't pass your shell environment to hooks
- adds `[mcp_servers.assertion]` to `~/.codex/config.toml` for the recall/expand tools

It merges into existing config rather than replacing it (other MCP servers, plugins
and hook-trust entries are preserved), is safe to re-run, and backs up every file it
touches.

```bash
python3 install_codex.py --key sk-...          # non-interactive (also reads $ASSERTION_API_KEY)
python3 install_codex.py --workspace my-ws     # a different tree
python3 install_codex.py --server https://...  # a non-prod backend
python3 install_codex.py --no-path-fix         # never modify shell rc files
python3 install_codex.py --uninstall           # remove what it added
```

<details>
<summary>Manual install, if you'd rather not run the script</summary>

```bash
codex plugin marketplace add https://github.com/Assertion-AI/assertion.git
codex plugin add assertion@assertion-ai      # or: codex → /plugins → enable "assertion"
mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json
chmod 600 ~/.assertion/credentials.json
```

Then add to `~/.codex/config.toml` (see `config.toml.example`), with a **literal**
bearer token:

```toml
[mcp_servers.assertion]
url = "https://memory.assertion-ai.com/memory/mcp/default"
http_headers = { Authorization = "Bearer <your key>" }
```

Because the key is in `config.toml`, this works in **both the CLI and the VS Code
extension** with no shell env — verified on codex 0.139 (a `recall` returned
results). Use `http_headers`, not `bearer_token` (Codex rejects the latter for HTTP
MCP). Capture + inject work from the credentials file regardless; this block only
adds the recall/expand tools.

If `codex: command not found`, it is installed but not on your `PATH` — use
`~/.local/bin/codex`, or let the installer fix it.

</details>

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
