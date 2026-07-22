---
description: Show your memory spaces, or switch THIS session to one
argument-hint: [space name, or blank to list]
allowed-tools: mcp__plugin_assertion_assertion__list_spaces, mcp__plugin_assertion_assertion__use_space
---

Space argument: **$ARGUMENTS**

If the argument above is empty: call `list_spaces` and present the result compactly — which
space is the default for new sessions, which space THIS session is on (if stated earlier in
this conversation; otherwise it's the default), and the team spaces I belong to with member
counts. Mention that `/assertion:space <name>` switches this session.

If a space name was given: run the `use_space` flow for it —
1. Call `use_space` WITHOUT `confirm` first and relay its consequence statement to me verbatim.
2. Only call again with `confirm: true` after I explicitly agree in this conversation.
3. After a confirmed switch, state plainly where this session's memory now goes, and remind me
   that other sessions and future sessions are unaffected.

Use "personal" to switch this session back to my personal tree.
