---
name: assertion-login
description: Sign in to Assertion memory in the browser, which turns memory on. Use when the user asks to sign in or log in to Assertion, or when Assertion memory says it is off.
---

Run exactly one command, from this skill's directory, and wait for it to finish. It opens the
browser, where the user clicks Connect; it can take a minute or two:

```
python3 ../../../scripts/assertion.py login --client codex
```

(The script is at `<this skill's directory>/../../../scripts/assertion.py`; use that absolute path
if you are running from somewhere else.) Add `--again` only if the user asked to sign in as a
different account, and `--code` only if they are on a machine with no browser.

Then show the user the command's output exactly as written. Don't add to it, don't retry it, and
don't run anything else. Never print, read, or ask for an API key.
