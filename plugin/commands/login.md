---
description: Sign in to Assertion in your browser, which turns memory on
argument-hint: "[again | code]"
allowed-tools: Bash(python3:*)
disable-model-invocation: true
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assertion.py" login --client claude-code $ARGUMENTS`

The Assertion sign-in above has already run; its output is the complete result. Show me that
output exactly as written, then stop. Don't add to it, don't retry it, and don't run any other
command.
