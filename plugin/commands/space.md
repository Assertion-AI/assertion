---
description: Show your memory spaces, or switch THIS session to one
argument-hint: "[space name, or blank to list]"
allowed-tools: Bash(python3:*)
disable-model-invocation: true
---

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/assertion.py" space --client claude-code --session "${CLAUDE_SESSION_ID}" $ARGUMENTS`

The command above has already run; its output is the complete result, and naming the space was
my confirmation. Show me that output exactly as written, then stop. Don't add to it, don't call
`use_space` or `list_spaces`, and don't run any other command.
