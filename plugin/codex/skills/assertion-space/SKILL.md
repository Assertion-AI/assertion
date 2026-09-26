---
name: assertion-space
description: Show the user's Assertion memory spaces, or switch this session to one. Use when the user asks which memory space they are in, to list spaces, or to switch spaces.
---

Run exactly one command, from this skill's directory. To list spaces:

```
python3 ../../../scripts/assertion.py space --client codex
```

To switch, add the space name the user gave, in quotes, to the end of that command (use
`personal` for their own space). The user naming the space is the confirmation; if they only
hinted at a space, ask which one before switching.

(The script is at `<this skill's directory>/../../../scripts/assertion.py`; use that absolute path
if you are running from somewhere else.) Show the user the output exactly as written. Don't add
to it, don't call the `use_space` or `list_spaces` tools, and don't run anything else.
