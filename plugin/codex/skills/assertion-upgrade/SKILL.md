---
name: assertion-upgrade
description: Update the Assertion memory plugin to the latest version. Use when the user asks to update or upgrade Assertion, or accepts an Assertion update notice.
---

Run exactly one command, from this skill's directory, and wait for it to finish:

```
python3 ../../../scripts/assertion.py upgrade --client codex
```

(The script is at `<this skill's directory>/../../../scripts/assertion.py`; use that absolute path
if you are running from somewhere else.) Show the user the output exactly as written. Don't add
to it, don't retry it, and don't run anything else.
