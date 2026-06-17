# Assertion memory for Cursor

Persistent, structured project memory for Cursor. Each turn is captured into a shared,
project-scoped tree; at the start of every session the relevant part of that tree is
injected back so the agent already knows your prior decisions and context.

It uses the shared **`default`** workspace on `memory.assertion-ai.com` — the same tree
your other Assertion-memory sessions read and write. You only need an API key.

## What you get
- **sessionStart** — injects the working-set tree into the new conversation as context.
- **beforeSubmitPrompt** — stashes your prompt for capture, and writes the live attention-lens
  (what changed, what you're zooming into) to a Cursor Rules file, `.cursor/rules/assertion-memory.mdc`,
  refreshed every prompt. Cursor auto-loads that file, so the relevant memory follows your work.
- **afterAgentResponse** — captures the turn `(prompt, response)` into the tree.
- **`recall` / `expand` MCP tools** — query the tree on demand from inside Cursor.

The rules file is generated — add `\.cursor/rules/assertion-memory.mdc` to your `.gitignore`.

## Install (one command)

From this directory, run the installer and paste your key when prompted:
```bash
python3 install_cursor.py
```
It writes your key to `~/.assertion/credentials.json`, adds the three hooks to
`~/.cursor/hooks.json`, and adds the recall/expand MCP server to `~/.cursor/mcp.json` —
merging into any existing Cursor config (it won't touch your other hooks or MCP servers)
and backing up anything it changes. Get your key at https://assertion-ai.com.

Then **fully quit and reopen Cursor** so it loads the hooks and MCP server. Approve the
hooks if Cursor prompts to trust them.

Options: `--key <key>` (non-interactive), `--workspace <name>` (a different tree),
`--server <url>` (a non-prod backend), `--uninstall` (remove what it added).

<details><summary>Manual install (if you'd rather not run the script)</summary>

1. Set your key (Cursor runs hooks without your shell env, so it goes in a file):
   `mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json`
2. Copy `hooks.json` into `~/.cursor/hooks.json`, replacing
   `/ABSOLUTE/PATH/TO/assertion-plugin/plugin/scripts` with this repo's `plugin/scripts` path.
3. Merge `mcp.json` into `~/.cursor/mcp.json`, replacing `YOUR_API_KEY`.
4. Reload Cursor.
</details>

## Verify
- `recall` returns nodes from your `default` tree.
- Make a decision in one session; start a new one and ask about it — the agent answers
  from memory without you re-stating it.

## Changing the workspace
The workspace is the shared `default` tree. To use a different one, change the path in the
MCP url (`/memory/mcp/<workspace>`) and add `"workspace": "<workspace>"` to
`~/.assertion/credentials.json` so capture and recall point at the same tree.
