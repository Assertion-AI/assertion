# Assertion — a second brain for your codebase

Gives **Claude Code**, **OpenAI Codex**, and **Cursor** memory that remembers the *why*
behind your decisions and the strategy across your project — and keeps it **current**,
superseding calls you've reversed instead of resurfacing them. It **recalls** that context
automatically as you work, into a shared, project-scoped tree. Reads run over a hosted MCP
endpoint (no local server); small hooks handle capture and context injection. One codebase
serves all three agents (single copy of the logic). By Assertion AI.

Install, then sign in once in your browser. There is no key to copy. Requires a system `python3`
(for the stdlib hooks); no other deps.

## Install — Claude Code

> **Already installed?** Keep the copy you have. If you installed from this repo (`assertion@assertion-ai`), don't also install it from the Claude Code community catalog (`assertion@claude-community`). Two copies means two sets of hooks, so every turn is captured twice. `/assertion:upgrade` updates whichever copy you have.

```
# 1) in Claude Code:
/plugin marketplace add Assertion-AI/assertion
/plugin install assertion@assertion-ai
/reload-plugins
```
`/reload-plugins` turns the plugin on in the session you're in, with no restart. Or install from
your terminal before you start Claude Code, and skip it:
`claude plugin marketplace add Assertion-AI/assertion && claude plugin install assertion@assertion-ai`

**2) Sign in:**
```
/assertion:login
```
Your browser opens at Assertion Studio; click **Connect** (new here? sign up on that page first).
Memory turns on in the same session: the memory tools and capture both pick up the sign-in, with
no restart and no key to copy. Then try `recall <topic>`. Until you sign in, each session starts
with a one-line notice that memory is off.

On a machine with no browser (SSH, a server), `/assertion:login code` shows a short code to
confirm from any device instead.

**Requirements:** a system `python3` (for the two stdlib hooks). No other deps — the
memory tools connect over HTTP.

> **Using a key instead** (CI, or a shared machine): `ASSERTION_API_KEY` still works and takes
> precedence over the sign-in. Put it in `~/.claude/settings.json` as
> `{"env": {"ASSERTION_API_KEY": "<key>"}}` rather than a shell `export`, so it reaches the plugin
> however you launch Claude Code.
>
> **Upgrading:** run `/assertion:upgrade`, then `/reload-plugins`. No restart needed.
>
> **Spaces:** `/assertion:space` lists your memory spaces and shows which one this session uses;
> `/assertion:space <name>` switches this session only (`/assertion:space personal` to go back).

## Install — OpenAI Codex

```bash
# 1) install the plugin
codex plugin marketplace add Assertion-AI/assertion
codex plugin add assertion@assertion-ai

# 2) sign in in your browser (no key to copy)
python3 "$(ls -d ~/.codex/plugins/cache/*/assertion/*/scripts | sort -V | tail -1)/assertion.py" login --client codex
```
Or, once Codex is open, ask it to "sign in to Assertion" (the plugin's `assertion-login` skill runs
the same sign-in). Either way the key is saved for the hooks and written into
`~/.codex/config.toml` for the memory tools.

3. Use Codex **interactively** (`codex` in a terminal, or the VS Code Codex panel — *not*
   `codex exec`). On first run, toggle the three hooks **Trust** on when prompted (once).

Capture + injection then work against the same shared tree, in CLI and VS Code. Full
Codex details (recall/expand setup, dev override): [plugin/codex/README.md](plugin/codex/README.md).

## Install — Cursor

Cursor has no plugin marketplace, so it installs via a one-time script that wires its
`hooks.json` + `mcp.json` for you:

```bash
git clone https://github.com/Assertion-AI/assertion
cd assertion/plugin/cursor && python3 install_cursor.py   # signs you in in the browser
```
Then fully quit and reopen Cursor. The installer merges into any existing Cursor config
(it won't touch your other hooks or MCP servers), backs up what it changes, and defaults
to prod + the shared `default` workspace. In Cursor, `/assertion-login` signs in again,
`/assertion-space` lists or switches memory spaces, and `/upgrade` updates the clone. Options
(`--key`, `--workspace`, `--server`, `--uninstall`) and a manual fallback:
[plugin/cursor/README.md](plugin/cursor/README.md).

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

## License

The plugin in this repository is licensed under the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE).

The license covers this client code only. The hosted Assertion service it connects to is governed by the [Terms of Service](https://assertion-ai.com/terms), and your data by the [privacy notice](https://assertion-ai.com/privacy). "Assertion" is a trademark of Assertion AI, Inc.
