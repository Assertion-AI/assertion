#!/usr/bin/env python3
"""headersHelper for the Assertion MCP server (plugin/.mcp.json).

Claude Code runs this when it connects to the server, and again after a 401, then sends the JSON
object it prints as request headers. The key comes from ASSERTION_API_KEY if set, else from
~/.assertion/credentials.json, which /assertion:login writes. So a sign-in turns the memory tools
on in the running session, with no restart and no key to paste. Prints {} when there is no key.
Stdlib-only; never fails loudly (a crash here would take the server down with it).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import _creds
    headers = _creds.mcp_headers()
except Exception:
    headers = {}
sys.stdout.write(json.dumps(headers))
