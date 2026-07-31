Update the Assertion memory plugin to the latest version.

Run these two commands (this is Codex — note Codex has no `plugin update`, so the
second command re-adds the plugin, which upgrades it):

```
codex plugin marketplace upgrade assertion-ai
codex plugin add assertion@assertion-ai
```

Then report the result plainly:

- If a newer version was installed, say so and tell me to fully quit and reopen
  Codex in a fresh session so the new hooks take effect — they only load at launch.
- If it was already up to date, just tell me I'm on the latest; no restart needed.

Run only those two commands; don't change anything else.
