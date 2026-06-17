# Assertion memory for Cursor

Persistent, structured project memory for Cursor. Each turn is captured into a shared,
project-scoped tree; at the start of every session the relevant part of that tree is
injected back so the agent already knows your prior decisions and context.

It uses the shared **`default`** workspace on `memory.assertion-ai.com` — the same tree
your other Assertion-memory sessions read and write. You only need an API key.

## What you get
- **sessionStart** — injects the working-set tree into the new conversation as context.
- **beforeSubmitPrompt** — stashes your prompt so the turn can be captured.
- **afterAgentResponse** — captures the turn `(prompt, response)` into the tree.
- **`recall` / `expand` MCP tools** — query the tree on demand from inside Cursor.

## Install

**1. Set your API key.** Cursor runs hooks without your shell environment, so the key
goes in a file (not `export`):
```bash
mkdir -p ~/.assertion && echo '{"api_key":"<your key>"}' > ~/.assertion/credentials.json
```

**2. Install the hooks.** Copy `cursor/hooks.json` into your project's `.cursor/hooks.json`
(or `~/.cursor/hooks.json` to enable it for every project), and replace
`/ABSOLUTE/PATH/TO/assertion-plugin/plugin/scripts` with the real path to this repo's
`plugin/scripts` directory. The scripts are stdlib-only and run on the system `python3`.

**3. Add the recall/expand tools (MCP).** Merge the `cursor/mcp.json` block into
`~/.cursor/mcp.json` and replace `YOUR_API_KEY` with your key:
```json
{
  "mcpServers": {
    "assertion": {
      "url": "https://memory.assertion-ai.com/memory/mcp/default",
      "headers": { "Authorization": "Bearer YOUR_API_KEY" }
    }
  }
}
```

**4. Reload Cursor.** Open a new chat — Cursor reads the hooks and the MCP server on start.

## Verify
- `recall` returns nodes from your `default` tree.
- Make a decision in one session; start a new one and ask about it — the agent answers
  from memory without you re-stating it.

## Changing the workspace
The workspace is the shared `default` tree. To use a different one, change the path in the
MCP url (`/memory/mcp/<workspace>`) and add `"workspace": "<workspace>"` to
`~/.assertion/credentials.json` so capture and recall point at the same tree.
