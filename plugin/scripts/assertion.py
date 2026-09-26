#!/usr/bin/env python3
"""The Assertion plugin's own commands, run as a script rather than interpreted by the model.

  assertion.py login   [--client C] [--code] [--again]   sign in in the browser; turns memory on
  assertion.py space   [--client C] [--session ID] [NAME] list spaces, or switch this session
  assertion.py upgrade [--client C]                       update the plugin in place

Claude Code runs these from `!` lines in plugin/commands/*.md, before the model sees anything, so
the model only relays what they print. Cursor and Codex have no such hook, so their commands and
skills ask the model to run exactly one of these lines. C is claude-code, cursor or codex.

Sign-in is the one Assertion's terminal agent uses (backend memory_backend/app_signin.py): listen
on 127.0.0.1, open Studio at /device?port=…&state=…&challenge=…, the signed-in user clicks
Connect, Studio sends the browser back to our listener with a one-time grant, and we redeem it
with the PKCE verifier for the account's key. With no browser on this machine (SSH, a headless
box, or --code) it is the device-code flow instead: a short code confirmed in Studio from any
device. Either way the key goes straight to ~/.assertion/credentials.json (0600) and is never
printed.

The listener runs in a detached worker because Claude Code gives a `!` line about two minutes.
The foreground waits up to LOGIN_WAIT seconds and reports; if the click comes later the worker
still saves the key, and memory turns on then.

Stdlib-only.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _creds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO_DEVICE_URL = (os.environ.get("ASSERTION_STUDIO_DEVICE_URL") or "https://studio.assertion-ai.com/device").rstrip("/")
LOGIN_TTL = 600            # the worker gives up after ten minutes, like the backend's device codes
LOGIN_WAIT = float(os.environ.get("ASSERTION_LOGIN_WAIT") or 90)   # under Claude Code's `!` limit
CLIENT_NAMES = {"claude-code": "Claude Code", "cursor": "Cursor", "codex": "Codex"}
CURSOR_MCP = os.path.expanduser("~/.cursor/mcp.json")
CODEX_CONFIG = os.path.expanduser("~/.codex/config.toml")
CODEX_KEYFILE = os.path.expanduser("~/.codex/assertion.json")
OFF = {"off", "0", "false", "no"}


# --------------------------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------------------------- #

def _auth_base() -> str:
    """The service that runs device sign-in: the memory backend (same host the plugin talks to)."""
    return (os.environ.get("ASSERTION_AUTH_URL") or _creds.server_url()).rstrip("/")


def _http(method: str, url: str, body=None, headers=None, timeout: float = 15):
    """(status, parsed JSON or text). Network failure → (0, message)."""
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json", "User-Agent": f"assertion-plugin/{_creds.plugin_version() or 'dev'}"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except Exception as e:
        return 0, str(getattr(e, "reason", e))
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text)
    except Exception:
        return status, text


def _memory(method: str, path: str, body=None, key: str | None = None, timeout: float = 15):
    key = key or _creds.api_key()
    url = f"{_creds.server_url()}{_creds.path_prefix()}{path}"
    return _http(method, url, body, {"x-api-key": key, "X-Assertion-Workspace": _creds.workspace()}, timeout)


# --------------------------------------------------------------------------------------------- #
# login
# --------------------------------------------------------------------------------------------- #

def challenge_for(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def can_use_local_callback(env=None, system=None) -> bool:
    """Can a browser on this machine reach a listener on 127.0.0.1? Not over SSH or without a display."""
    env = os.environ if env is None else env
    system = platform.system() if system is None else system
    if (env.get("ASSERTION_LOGIN_CALLBACK") or "").strip().lower() in OFF:
        return False
    if env.get("SSH_CONNECTION") or env.get("SSH_TTY") or env.get("SSH_CLIENT"):
        return False
    if system == "Linux" and not env.get("DISPLAY") and not env.get("WAYLAND_DISPLAY"):
        return False
    return True


def describe_device(client: str) -> str:
    host = socket.gethostname().split(".")[0] or "this computer"
    return f"{CLIENT_NAMES.get(client, 'Assertion plugin')} on {host}"[:120]


def open_browser(url: str) -> bool:
    if os.environ.get("ASSERTION_NO_BROWSER"):
        return False
    system = platform.system()
    cmd = (["open", url] if system == "Darwin" else
           ["cmd", "/c", "start", "", url] if system == "Windows" else
           ["xdg-open", url] if shutil.which("xdg-open") else None)
    if not cmd:
        return False
    try:
        return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except Exception:
        return False


def _status_path(token: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "", token)[:40]
    return os.path.join(tempfile.gettempdir(), f"assertion_login_{safe}.json")


def _write_status(path: str, d: dict) -> None:
    # Holds no secret (never the key), but keep it private anyway.
    _creds.write_private(path, json.dumps(d))


def _read_status(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f) or {}
    except Exception:
        return {}


def finish_signin(key: str, email: str | None, client: str) -> dict:
    """Save a freshly issued key everywhere this machine's clients read it. Returns what was written
    (paths only). Claude Code needs nothing beyond the credentials file: its headersHelper reads it.
    Cursor and Codex read the MCP key from their own config, literally, so it is written there too —
    but only into an Assertion entry that is already there, or for the client that asked."""
    written = [_creds.save_api_key(key, email)]
    notes = []
    for name, fn in (("cursor", _write_cursor_mcp), ("codex", _write_codex_mcp)):
        try:
            p = fn(key, create=(client == name))
            if p:
                written.append(p)
        except Exception as e:
            notes.append(f"could not update the {CLIENT_NAMES[name]} memory tools config: {e}")
    try:
        if os.path.exists(CODEX_KEYFILE):   # an older Codex setup; keep it from holding a stale key
            d = _load_json(CODEX_KEYFILE)
            if d.get("api_key") and d.get("api_key") != key:
                d["api_key"] = key
                _creds.write_private(CODEX_KEYFILE, json.dumps(d, indent=2) + "\n")
                written.append(CODEX_KEYFILE)
    except Exception:
        pass
    return {"written": written, "notes": notes}


def _load_json(path: str) -> dict:
    with open(path) as f:
        d = json.load(f)
    if not isinstance(d, dict):
        raise ValueError(f"{path} is not a JSON object")
    return d


def _default_mcp_url(workspace: str | None = None) -> str:
    return f"{_creds.server_url()}/memory/mcp/{workspace or _creds.workspace()}"


def _write_cursor_mcp(key: str, create: bool = False) -> str | None:
    """Cursor has no headers helper: its mcp.json takes a literal header. Replace only ours."""
    if os.path.exists(CURSOR_MCP):
        d = _load_json(CURSOR_MCP)   # unreadable → raise, and leave the user's file alone
    elif create:
        d = {}
    else:
        return None
    servers = d.get("mcpServers") if isinstance(d.get("mcpServers"), dict) else {}
    ours = servers.get("assertion") if isinstance(servers.get("assertion"), dict) else None
    if ours is None and not create:
        return None
    ours = dict(ours or {})
    ours.setdefault("url", _default_mcp_url())
    headers = ours.get("headers") if isinstance(ours.get("headers"), dict) else {}
    headers = {k: v for k, v in headers.items() if k.lower() not in ("authorization", "x-api-key")}
    headers["Authorization"] = f"Bearer {key}"
    ours["headers"] = headers
    servers["assertion"] = ours
    d["mcpServers"] = servers
    _creds.write_private(CURSOR_MCP, json.dumps(d, indent=2) + "\n")
    return CURSOR_MCP


_CODEX_SECTION = "mcp_servers.assertion"
_TOML_HEADER = re.compile(r"^\s*\[\[?([^\]]+)\]\]?\s*$")


def _codex_section(text: str):
    """(lines of our [mcp_servers.assertion] table incl. subtables, text without them)."""
    ours, rest, inside = [], [], False
    for line in text.splitlines(keepends=True):
        m = _TOML_HEADER.match(line)
        if m:
            name = m.group(1).strip().strip('"')
            inside = name == _CODEX_SECTION or name.startswith(_CODEX_SECTION + ".")
        (ours if inside else rest).append(line)
    return ours, "".join(rest)


def _write_codex_mcp(key: str, create: bool = False) -> str | None:
    """Codex has no headers helper either, and `${VAR}` is not expanded inside http_headers; a
    literal bearer token is the one form that works in the CLI, the desktop app and VS Code (see
    codex/install_codex.py write_mcp_block). Same table the installer writes; the rest of
    config.toml is kept byte for byte."""
    text = ""
    if os.path.exists(CODEX_CONFIG):
        with open(CODEX_CONFIG) as f:
            text = f.read()
    elif not create:
        return None
    ours, rest = _codex_section(text)
    if not ours and not create:
        return None
    url = None
    for line in ours:
        m = re.match(r'^\s*url\s*=\s*"([^"]+)"', line)
        if m:
            url = m.group(1)
    block = (f"[{_CODEX_SECTION}]\n"
             f'url = "{url or _default_mcp_url()}"\n'
             f'http_headers = {{ Authorization = "Bearer {key}" }}\n')
    rest = rest.rstrip()
    _creds.write_private(CODEX_CONFIG, (rest + "\n\n" + block) if rest else block)
    return CODEX_CONFIG


class _CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _page(self, status: int, title: str, body: str):
        html = ('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f"<title>{title}</title><body style=\"font:15px/1.5 system-ui,-apple-system,sans-serif;background:#0f1d29;"
                "color:#eef4f8;display:grid;place-items:center;min-height:100vh;margin:0;padding:0 16px\">"
                f'<div style="max-width:420px"><h1 style="font-size:20px;font-weight:600;margin:0 0 8px">{title}</h1>'
                f'<p style="color:#8c959b;margin:0">{body}</p></div>').encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_GET(self):
        srv = self.server
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        one = lambda k: (q.get(k) or [""])[0]
        if u.path != "/callback":
            return self._page(404, "Not found", "This address only finishes an Assertion sign-in.")
        if not secrets.compare_digest(one("state"), srv.state):
            return self._page(400, "Sign-in link not recognised", "Start the sign-in again from your editor.")
        if srv.result is not None:
            return self._page(409, "Already handled", "This sign-in has finished. You can close this tab.")
        if one("error"):
            srv.result = {"status": "denied", "message": "cancelled in the browser"}
            return self._page(200, "Sign-in cancelled", "Nothing was connected. You can close this tab.")
        status, j = _http("POST", f"{srv.auth_base}/auth/device/exchange", {"code": one("code"), "verifier": srv.verifier})
        key = j.get("api_key") if isinstance(j, dict) else None
        if status != 200 or not isinstance(key, str) or not key:
            why = (j.get("error") if isinstance(j, dict) else "") or (f"sign-in service error {status}" if status else f"could not reach Assertion: {j}")
            srv.result = {"status": "error", "message": why}
            return self._page(502, "Sign-in didn't finish", f"{why}. Start the sign-in again from your editor.")
        email = j.get("email") if isinstance(j.get("email"), str) else None
        try:
            done = finish_signin(key, email, srv.client)
        except Exception as e:
            srv.result = {"status": "error", "message": f"could not save the sign-in on this computer: {e}"}
            return self._page(500, "Sign-in didn't finish", "Assertion could not save the sign-in on this computer.")
        srv.result = {"status": "approved", "email": email, "notes": done["notes"]}
        # Studio's "Connected" screen is the nicer ending, and it is where the user already is.
        self.send_response(302)
        self.send_header("Location", f"{STUDIO_DEVICE_URL}?connected=1&device={urllib.parse.quote(srv.device)}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def _worker_local(status_path: str, client: str, device: str, ttl: float) -> int:
    verifier = secrets.token_urlsafe(48)
    state = secrets.token_urlsafe(24)
    srv = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    srv.timeout = 1
    srv.state, srv.verifier, srv.client, srv.device = state, verifier, client, device
    srv.auth_base, srv.result = _auth_base(), None
    q = urllib.parse.urlencode({"port": srv.server_address[1], "state": state,
                                "challenge": challenge_for(verifier), "device": device})
    _write_status(status_path, {"status": "pending", "mode": "browser", "url": f"{STUDIO_DEVICE_URL}?{q}"})
    deadline = time.time() + ttl
    while srv.result is None and time.time() < deadline:
        srv.handle_request()
    result = srv.result or {"status": "expired"}
    # Let the redirect flush before the listener goes away.
    end = time.time() + 1
    while time.time() < end:
        srv.handle_request()
    srv.server_close()
    _write_status(status_path, result)
    return 0


def _worker_code(status_path: str, client: str, device: str, ttl: float) -> int:
    base = _auth_base()
    status, j = _http("POST", f"{base}/auth/device", {"device": device})
    if status != 200 or not isinstance(j, dict) or not j.get("device_code"):
        _write_status(status_path, {"status": "error", "message": f"Assertion sign-in is unavailable ({status or j})"})
        return 0
    interval = max(2, int(j.get("interval") or 5))
    _write_status(status_path, {"status": "pending", "mode": "code", "user_code": j.get("user_code"),
                                "url": j.get("verification_uri_complete") or j.get("verification_uri")})
    deadline = time.time() + min(ttl, float(j.get("expires_in") or ttl))
    code = urllib.parse.quote(str(j["device_code"]), safe="")
    while time.time() < deadline:
        time.sleep(interval)
        status, r = _http("GET", f"{base}/auth/device/{code}")
        if status == 404:
            _write_status(status_path, {"status": "expired"})
            return 0
        if status != 200 or not isinstance(r, dict):
            continue   # transient: keep waiting until the deadline
        s = r.get("status")
        if s == "slow_down":
            interval += 1
        elif s == "approved" and isinstance(r.get("api_key"), str) and r["api_key"]:
            email = r.get("email") if isinstance(r.get("email"), str) else None
            try:
                done = finish_signin(r["api_key"], email, client)
                _write_status(status_path, {"status": "approved", "email": email, "notes": done["notes"]})
            except Exception as e:
                _write_status(status_path, {"status": "error", "message": f"could not save the sign-in: {e}"})
            return 0
        elif s in ("denied", "expired"):
            _write_status(status_path, {"status": s})
            return 0
    _write_status(status_path, {"status": "expired"})
    return 0


def _spawn_worker(mode: str, client: str, device: str) -> str:
    status_path = _status_path(secrets.token_urlsafe(12))
    _write_status(status_path, {"status": "starting"})
    args = [sys.executable, os.path.abspath(__file__), "_login-worker", "--mode", mode,
            "--status", status_path, "--client", client, "--device", device]
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(args, **kw)
    return status_path


def _wait_status(path: str, until, timeout: float) -> dict:
    end = time.time() + timeout
    while True:
        d = _read_status(path)
        if until(d) or time.time() >= end:
            return d
        time.sleep(0.25)


def _done_line(client: str) -> str:
    if client == "claude-code":
        return "Memory is on. The memory tools and capture work in this session now, with no restart."
    if client == "cursor":
        return "Memory is on. Fully quit and reopen Cursor once so it picks up the memory tools."
    if client == "codex":
        return "Memory is on. Quit and reopen Codex once so it picks up the memory tools."
    return "Memory is on."


def _key_works(key: str) -> bool | None:
    status, _ = _memory("GET", "/spaces", key=key, timeout=10)
    return True if status == 200 else False if status in (401, 403) else None


def _say(*a):
    print(*a, flush=True)   # the link must show while we wait, not when we exit


def obtain_key(client: str, mode: str = "auto", wait: float | None = None, out=_say) -> dict:
    """Run a sign-in: start the worker, open the browser, wait. Returns the final status dict
    (status approved / pending / denied / expired / error). Shared by `login` and the installers."""
    device = describe_device(client)
    if mode == "auto":
        mode = "browser" if can_use_local_callback() else "code"
    path = _spawn_worker(mode, client, device)
    st = _wait_status(path, lambda d: d.get("status") not in (None, "starting"), 20)
    if st.get("status") in (None, "starting"):
        return {"status": "error", "message": "the sign-in helper did not start"}
    if st.get("status") != "pending":
        return st
    url = st.get("url") or ""
    if st.get("mode") == "code":
        out(f"To sign in, open {url}")
        out(f"and confirm this code: {st.get('user_code')}")
        opened = can_use_local_callback() and open_browser(url)
    else:
        opened = open_browser(url)
        out("Opening your browser to sign in to Assertion. Click Connect there." if opened else
            "Open this link to sign in to Assertion, then click Connect:")
        if not opened:
            out(url)
    if opened and st.get("mode") != "code":
        out(f"If no browser opened, use this link: {url}")
    return _wait_status(path, lambda d: d.get("status") not in ("pending", "starting"),
                        LOGIN_WAIT if wait is None else wait)


def cmd_login(a) -> int:
    client = a.client
    env_key = os.environ.get("ASSERTION_API_KEY") or os.environ.get("CONTEXT_TREE_API_KEY")
    key = _creds.api_key()
    if key and not a.again:
        ok = _key_works(key)
        if ok:
            email = _creds._file().get("email") if not env_key else None
            who = f" as {email}" if email else ""
            src = "the ASSERTION_API_KEY environment variable" if env_key else _creds.credentials_file()
            print(f"Already signed in{who}. Memory is on (key from {src}).")
            print("To sign in as someone else: /assertion:login again" if client == "claude-code" else
                  "To sign in as someone else, run the sign-in again with --again.")
            return 0
        if ok is None:
            print("You have a saved key, but Assertion could not be reached to check it. Try again in a minute.")
            return 1
        print("Your saved key is no longer accepted, so let's sign in again.")
    st = obtain_key(client, "code" if a.code else "auto")
    s = st.get("status")
    if s == "approved":
        who = f" as {st['email']}" if st.get("email") else ""
        print(f"\nSigned in{who}. {_done_line(client)}")
        if env_key:
            print("Note: ASSERTION_API_KEY is set in your environment and takes precedence over this sign-in. "
                  "Remove it to use the account you just signed in with.")
        for n in st.get("notes") or []:
            print(f"Note: {n}")
        return 0
    if s == "pending":
        print("\nStill waiting for you to finish in the browser. Take your time: the sign-in stays open for "
              "10 minutes, and memory turns on as soon as you click Connect"
              + (", with no restart." if client == "claude-code" else "."))
        return 0
    if s == "denied":
        print("\nSign-in was cancelled. Nothing was connected.")
        return 1
    if s == "expired":
        print("\nThe sign-in expired. Run it again when you're ready.")
        return 1
    print(f"\nSign-in didn't finish: {st.get('message') or 'unknown error'}")
    return 1


# --------------------------------------------------------------------------------------------- #
# space
# --------------------------------------------------------------------------------------------- #

def _usable_sid(sid: str | None) -> str:
    s = (sid or "").strip()
    return s if len(s) >= 8 and s.lower() != "default" and "${" not in s else ""


def _space_label(ws: str, spaces: list, personal_id: str) -> str:
    if ws == personal_id:
        return "personal"
    for s in spaces:
        if s.get("workspace") == ws:
            n = s.get("member_count") or 1
            return f"{s.get('name') or ws} (team space, {n} member{'s' if n != 1 else ''})"
    return ws


def _session_space(sid: str) -> dict | None:
    """This session's effective space, from a session-naming read (the same call the prompt hook
    makes each turn). since_turn far ahead means no changes come back, so nothing is credited."""
    q = urllib.parse.urlencode({"since_turn": 10 ** 9, "session_id": sid})
    status, d = _memory("GET", f"/working-set/delta?{q}")
    if status == 200 and isinstance(d, dict) and isinstance(d.get("effective_space"), dict):
        return d["effective_space"]
    return None


def cmd_space(a) -> int:
    if not _creds.api_key():
        print("You're not signed in to Assertion, so memory is off. " + _login_hint(a.client))
        return 1
    status, data = _memory("GET", "/spaces")
    if status in (401, 403):
        print("Your saved key is no longer accepted. " + _login_hint(a.client))
        return 1
    if status != 200 or not isinstance(data, dict) or "spaces" not in data:
        print(f"Could not reach Assertion to list your spaces ({status or data}). Try again in a minute.")
        return 1
    personal = data.get("personal") or "default"
    spaces = [s for s in data.get("spaces") or [] if s.get("workspace") and s.get("workspace") != personal]
    default = data.get("default_for_new_sessions") or "personal"
    default_id = personal if default == "personal" else default
    sid = _usable_sid(a.session)
    name = " ".join(a.name or []).strip()
    if not name:
        return _list_spaces(a, sid, spaces, personal, default_id)
    return _switch_space(a, sid, name, spaces, personal)


def _list_spaces(a, sid, spaces, personal, default_id) -> int:
    print("Your memory spaces")
    here = _session_space(sid) if sid else None
    if here:
        print(f"  This session:              {_space_label(here.get('workspace'), spaces, personal)}")
    else:
        print("  This session:              shown in the memory note at the top of each reply"
              if a.client != "claude-code" else "  This session:              (could not be read)")
    print(f"  Default for new sessions:  {_space_label(default_id, spaces, personal)}")
    print("")
    rows = [("personal", "", "just you")]
    for s in spaces:
        n = s.get("member_count") or 1
        label = s.get("name") or s["workspace"]
        rows.append((s["workspace"], label if label != s["workspace"] else "",
                     f"{n} member{'s' if n != 1 else ''}" + (", you own it" if s.get("is_owner") else "")))
    w0 = max(len(r[0]) for r in rows)
    w1 = max(len(r[1]) for r in rows)
    for ws, label, who in rows:
        print(f"  {ws.ljust(w0)}  {label.ljust(w1)}  {who}".rstrip())
    print("")
    cmd = _space_cmd(a.client)
    print(f"Switch this session: {cmd} <name>. Back to your own: {cmd} personal.")
    print("Change the default for new sessions at studio.assertion-ai.com/agent")
    return 0


def _switch_space(a, sid, name, spaces, personal) -> int:
    cmd = _space_cmd(a.client)
    want = name.strip().lower()
    if want in ("personal", "home", personal.lower()):
        target, label, members = personal, "your personal space", 1
    else:
        match = [s for s in spaces if want in (s["workspace"].lower(), (s.get("name") or "").lower())]
        if not match:
            names = ", ".join(["personal"] + [s["workspace"] for s in spaces])
            print(f'No space called "{name}". Yours: {names}.')
            return 1
        s = match[0]
        target, members = s["workspace"], s.get("member_count") or 1
        label = f'the team space "{s.get("name") or target}"'
    status, r = _memory("POST", "/tool", {"name": "use_space", "arguments": {"workspace": target, "confirm": True}})
    if status != 200 or not isinstance(r, dict):
        print(f"Could not switch ({status or r}). Nothing changed.")
        return 1
    if not r.get("switched"):
        print(r.get("message") or "Could not switch. Nothing changed.")
        return 1
    shared = f", shared with {members - 1} teammate{'s' if members - 1 != 1 else ''}" if members > 1 else ""
    if sid:
        # Claim the switch for THIS session now. use_space leaves a short-lived pending switch that
        # the session's next session-naming read claims; making that read here, with this session's
        # id, means no other session can pick it up first.
        here = _session_space(sid)
        if here and here.get("workspace") == target:
            print(f"This session now reads from and saves memory to {label}{shared}.")
            print("Other sessions, and sessions you start later, are unaffected.")
            if target != personal:
                print(f"Anything you work on in this session from here on is visible to its members. Undo: {cmd} personal")
            return 0
    print(f"This session switches to {label}{shared} from your next message.")
    print("Other sessions, and sessions you start later, are unaffected.")
    if target != personal:
        print(f"From then on, what you work on in this session is visible to its members. Undo: {cmd} personal")
    return 0


def _space_cmd(client: str) -> str:
    return {"claude-code": "/assertion:space", "cursor": "/assertion-space"}.get(client, "the assertion-space skill")


def _login_hint(client: str) -> str:
    return {"claude-code": "Run /assertion:login to turn it on.",
            "cursor": "Run /assertion-login to turn it on."}.get(client, "Ask Codex to sign in to Assertion (the assertion-login skill).")


# --------------------------------------------------------------------------------------------- #
# upgrade
# --------------------------------------------------------------------------------------------- #

def _run(cmd, timeout=180, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"{cmd[0]} not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def _vkey(v: str):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-+]", v or "0"))


def _claude_installs() -> list:
    code, out = _run(["claude", "plugin", "list", "--json"], timeout=60)
    if code != 0:
        return []
    try:
        items = json.loads(out[out.index("["):])
    except Exception:
        return []
    return [i for i in items if isinstance(i, dict) and str(i.get("id", "")).startswith("assertion@")]


def _upgrade_claude() -> int:
    before = {i["id"]: i.get("version") or "" for i in _claude_installs()}
    if not before:
        print("Could not find the Assertion plugin in `claude plugin list`. Nothing changed.")
        return 1
    for pid in before:
        mkt = pid.split("@", 1)[1]
        code, out = _run(["claude", "plugin", "marketplace", "update", mkt])
        if code != 0:
            print(f"Could not refresh the {mkt} marketplace: {out.strip()[-300:]}")
            return 1
        code, out = _run(["claude", "plugin", "update", pid])
        if code != 0:
            print(f"Could not update {pid}: {out.strip()[-300:]}")
            return 1
    after = {i["id"]: i.get("version") or "" for i in _claude_installs()}
    changed = [(p, before[p], after.get(p, "")) for p in before if after.get(p) and after.get(p) != before[p]]
    for p, old, new in changed:
        print(f"Updated {p} from {old} to {new}.")
    if changed:
        print("Fully quit Claude Code and start a fresh session (not --continue) so the new version loads.")
    else:
        print(f"Already on the latest version ({', '.join(sorted(set(before.values())))}). Nothing to do.")
    if len(before) > 1:
        print(f"Note: you have {len(before)} copies installed ({', '.join(before)}), so every turn is captured "
              "more than once. Keep one: claude plugin uninstall <the other one>")
    return 0


def _upgrade_cursor() -> int:
    code, root = _run(["git", "-C", HERE, "rev-parse", "--show-toplevel"], timeout=20)
    root = root.strip()
    if code != 0 or not root:
        print(f"This copy of the plugin ({HERE}) is not a git clone, so it cannot update itself. "
              "Clone https://github.com/Assertion-AI/assertion and run plugin/cursor/install_cursor.py.")
        return 1
    old_v = _creds.plugin_version()
    _, old_sha = _run(["git", "-C", root, "rev-parse", "HEAD"], timeout=20)
    code, out = _run(["git", "-C", root, "pull", "--ff-only"])
    if code != 0:
        print(f"Could not update the clone at {root}:\n{out.strip()[-500:]}\nNothing changed.")
        return 1
    _, new_sha = _run(["git", "-C", root, "rev-parse", "HEAD"], timeout=20)
    if old_sha.strip() == new_sha.strip():
        print(f"Already on the latest version ({old_v}). Nothing to do.")
        return 0
    # The installer copies the slash commands into ~/.cursor/commands; refresh them from the new version.
    _run([sys.executable, os.path.join(root, "plugin", "cursor", "install_cursor.py"), "--commands-only"], timeout=60)
    try:
        with open(os.path.join(root, "plugin", ".claude-plugin", "plugin.json")) as f:
            new_v = json.load(f).get("version") or "?"
    except Exception:
        new_v = "?"
    print(f"Updated the Assertion plugin from {old_v} to {new_v} (clone at {root}).")
    print("Fully quit and reopen Cursor so the new version loads.")
    return 0


def _codex_bin() -> str | None:
    for c in (shutil.which("codex"), os.path.expanduser("~/.local/bin/codex"), "/usr/local/bin/codex",
              "/opt/homebrew/bin/codex", os.path.expanduser("~/.codex/packages/standalone/current/bin/codex")):
        if c and os.path.exists(c):
            return c
    return None


def _codex_cached_version(mkt: str) -> str:
    d = os.path.expanduser(f"~/.codex/plugins/cache/{mkt}/assertion")
    try:
        vs = [v for v in os.listdir(d) if re.match(r"^\d", v)]
    except Exception:
        return ""
    return max(vs, key=_vkey) if vs else ""


def _upgrade_codex() -> int:
    codex = _codex_bin()
    if not codex:
        print("Could not find the codex command. Nothing changed.")
        return 1
    mkt = _creds.install_source() or "assertion-ai"
    old = _codex_cached_version(mkt) or _creds.plugin_version()
    code, out = _run([codex, "plugin", "marketplace", "upgrade", mkt])
    if code != 0:
        print(f"Could not refresh the {mkt} marketplace: {out.strip()[-300:]}")
        return 1
    # Codex has no `plugin update`; adding the plugin again installs the newest version.
    code, out = _run([codex, "plugin", "add", f"assertion@{mkt}"])
    if code != 0:
        print(f"Could not update assertion@{mkt}: {out.strip()[-300:]}")
        return 1
    new = _codex_cached_version(mkt)
    if new and old and _vkey(new) > _vkey(old):
        print(f"Updated the Assertion plugin from {old} to {new}.")
        print("Quit and reopen Codex so the new version loads.")
    else:
        print(f"Already on the latest version ({old or new or 'unknown'}). Nothing to do.")
    return 0


def cmd_upgrade(a) -> int:
    return {"claude-code": _upgrade_claude, "cursor": _upgrade_cursor, "codex": _upgrade_codex}[a.client]()


# --------------------------------------------------------------------------------------------- #

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="assertion.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("login", "space", "upgrade"):
        p = sub.add_parser(name)
        p.add_argument("--client", choices=sorted(CLIENT_NAMES), default="claude-code")
        if name == "login":
            p.add_argument("--code", action="store_true", help="use a code instead of a local callback")
            p.add_argument("--again", action="store_true", help="sign in even if already signed in")
            p.add_argument("rest", nargs="*")
        if name == "space":
            p.add_argument("--session", default="")
            p.add_argument("name", nargs="*")
    w = sub.add_parser("_login-worker")
    w.add_argument("--mode", choices=("browser", "code"), required=True)
    w.add_argument("--status", required=True)
    w.add_argument("--client", default="claude-code")
    w.add_argument("--device", default="")
    w.add_argument("--ttl", type=float, default=LOGIN_TTL)
    a = ap.parse_args(argv)
    if a.cmd == "_login-worker":
        fn = _worker_local if a.mode == "browser" else _worker_code
        try:
            return fn(a.status, a.client, a.device, a.ttl)
        except Exception as e:
            _write_status(a.status, {"status": "error", "message": str(e)[:300]})
            return 0
    if a.cmd == "login":
        # Free text after the command (`/assertion:login again`, `/assertion:login code`) works too.
        words = {w.lower().lstrip("-") for w in a.rest}
        a.again = a.again or bool(words & {"again", "force", "switch"})
        a.code = a.code or "code" in words
    return {"login": cmd_login, "space": cmd_space, "upgrade": cmd_upgrade}[a.cmd](a)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
