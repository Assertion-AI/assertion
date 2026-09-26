---
description: Update the Assertion memory plugin to the latest version
allowed-tools: Bash(python3:*)
disable-model-invocation: true
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assertion.py" upgrade --client claude-code`

The update above has already run; its output is the complete result. Show me that output exactly
as written, then stop. Don't add to it, don't retry it, and don't run any other command.
