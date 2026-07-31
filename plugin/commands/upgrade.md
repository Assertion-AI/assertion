---
description: Update the Assertion memory plugin to the latest version
allowed-tools: Bash(claude plugin marketplace update:*), Bash(claude plugin update:*)
---

Update the Assertion memory plugin to the latest version.

Run these two commands (this is Claude Code):

```
claude plugin marketplace update assertion-ai
claude plugin update assertion@assertion-ai
```

Then report the result plainly, based on the command output:

- **If a newer version was installed** — say so (include the old → new version if the output shows it), then tell me I must **fully quit and reopen Claude Code in a fresh session** (not `--continue`) for the new hooks to take effect — they only load at launch.
- **If it was already up to date** — just tell me I'm on the latest; no restart needed.

Run only those two commands; don't change anything else.
