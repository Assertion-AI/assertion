# Changelog

Notable changes to the Assertion plugin for Claude Code, Cursor and Codex. Each version here
becomes a GitHub release when it reaches `main`.

## [0.3.8] — 2026-09-25

- Sign in with `/assertion:login`: your browser opens, you click Connect, and memory is on. There is
  no key to copy, and in Claude Code no restart: the memory tools read the sign-in through a
  headers helper, and capture reads the same file. Cursor (`/assertion-login`) and Codex (the
  `assertion-login` skill) sign in the same way, and both installers now sign you in instead of
  asking for a key. On a machine with no browser, `/assertion:login code` uses a short code
  instead. One sign-in covers every client on this machine: it also refreshes the key in an
  existing Cursor or Codex setup. `ASSERTION_API_KEY` still works and still takes precedence.
- Until you sign in, each session starts with a one-line notice that memory is off and how to turn
  it on. Before, it stayed silent.
- Installing the plugin inside a running Claude Code session needs no new session: run
  `/reload-plugins`. That doesn't count as a session start, so your first message now brings what
  session start would have (the project memory summary, or the signed-out notice), once. The same
  applies when you sign in after a session has started.
- `/assertion:space` and `/assertion:upgrade` run as scripts instead of instructions the assistant
  interprets, so they do the same thing every time. `/assertion:space <name>` switches this session
  at once (naming the space is the confirmation), and says who else can see it and how to undo.
  Cursor gets `/assertion-space` and an `/upgrade` that pulls the exact clone it runs from; Codex
  gets `assertion-space` and `assertion-upgrade` skills.
- Codex: updating the plugin no longer breaks capture in sessions that are already open. The hooks
  now run through `~/.assertion/bin/codex-hook`, which starts the newest installed version, so
  their commands stay the same from version to version (no new trust prompt on later updates).
  Codex drops the old version's files on update, and before this every hook in an open session
  failed until Codex restarted. Coming from 0.3.7 or earlier, this one update still needs a
  restart and a one-time trust of the hooks.
- Files that hold the key (`~/.assertion/credentials.json`, Cursor's `mcp.json`, Codex's
  `config.toml`) are written owner-only (0600).

## [0.3.7] — 2026-09-23

- Each capture also reports which copy of the plugin is installed: the name of the marketplace it
  came from (`claude-community` for the Claude Code catalog, `assertion-ai` for this repo). Only
  that name is sent, never a file path. Nothing is sent for a local checkout.

## [0.3.6] — 2026-09-22

- The plugin is licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
- `/assertion:upgrade` updates whichever copy you have installed, including one from the Claude Code
  community catalog. It previously named this repo's marketplace directly.
- The README tells existing users not to install a second copy from the community catalog, which
  would capture every turn twice.
- Every manifest now reports the same version, and a check keeps them that way.

## [0.3.5] — 2026-09-17

- Recall waits up to 8 seconds for the memory service instead of 5, so slow responses no longer
  arrive empty.
- Codex has a one-command installer that registers the marketplace and opens Codex itself, with no
  paths to type and no config to edit by hand.
- Credential files are created with owner-only permissions (0600) from the moment they are opened.

## [0.3.4] — 2026-07-31

- When a newer plugin version is available, a notice appears once during the session, not only at
  launch, so long-running sessions see it too.

## [0.3.3] — 2026-07-31

- `/assertion:upgrade` updates the plugin on demand, in Claude Code, Cursor and Codex.

## [0.3.2] — 2026-07-22

- Workspace awareness: each turn knows which memory space the session is using. The assistant says
  so when it changes, on the first turn in a team space, and after a resume. An optional Claude Code
  status line shows it permanently.

## [0.3.1] — 2026-07-22

- `/assertion:space` lists your memory spaces or switches this session to one.

## [0.3.0] — 2026-07-22

- Sessions keep the memory space they started in. Changing your default on the website affects new
  sessions only. Same code as 0.2.4, renumbered because it changes behaviour.

## [0.2.4] — 2026-07-22

- Recall calls name their session, so a session can be switched to a different space mid-way.
- The first reply of a session states where its memory goes.

## [0.2.3] — 2026-06-30

- Capture no longer drops a turn when the editor ends it before the transcript has finished writing,
  and each turn is labelled with the right client.

## [0.2.2] — 2026-06-29

- Short follow-ups such as "why?" recall relevant memory, using the previous reply as context.

## [0.2.1] — 2026-06-29

- Claude Code is detected correctly in the capture hook.
