---
name: assertion-logout
description: Sign out of Assertion memory on this computer, which turns memory off. Use when the user asks to sign out or log out of Assertion, or to turn Assertion memory off.
---

Run exactly one command, from this skill's directory, and wait for it to finish:

```
python3 ../../../scripts/assertion.py logout --client codex
```

(The script is at `<this skill's directory>/../../../scripts/assertion.py`; use that absolute path
if you are running from somewhere else.)

Then show the user the command's output exactly as written. Don't add to it, don't retry it, and
don't run anything else. Never print, read, or ask for an API key.
