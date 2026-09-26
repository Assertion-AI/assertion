"""Sign-in, spaces and the MCP headers helper, offline: a fake backend on 127.0.0.1, a temp HOME,
and the browser's part played by this test. Run: python3 plugin/scripts/test_native_commands.py"""
import hashlib, base64, json, os, re, secrets, stat, subprocess, sys, tempfile, threading, time, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
fails = 0
def check(name, cond, detail=""):
    global fails
    fails += not cond
    print(("PASS " if cond else "FAIL ") + name + ("" if cond or not detail else f"  [{detail}]"))

KEY = "sk-test-" + secrets.token_hex(8)
# ---- fake backend ----------------------------------------------------------------------------
S = {"grants": {}, "devices": {}, "tool_calls": [], "delta_calls": [], "pending": None, "pins": {}}
SPACES = {"default_for_new_sessions": "personal", "personal": "home_u1",
          "spaces": [{"workspace": "home_u1", "name": "home_u1", "member_count": 1, "is_owner": True},
                     {"workspace": "team-alpha", "name": "Team Alpha", "member_count": 3, "is_owner": False}]}
class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, obj):
        b = (json.dumps(obj) if not isinstance(obj, str) else obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def _body(self):
        n = int(self.headers.get("content-length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")
    def _authed(self):
        return self.headers.get("x-api-key") == KEY
    def do_POST(self):
        u = urllib.parse.urlparse(self.path); b = self._body()
        if u.path == "/auth/device":
            dc = secrets.token_urlsafe(16); S["devices"][dc] = {"status": "pending", "user_code": "BCDF-GHJK"}
            return self._send(200, {"device_code": dc, "user_code": "BCDF-GHJK", "verification_uri": "http://studio/device",
                                    "verification_uri_complete": "http://studio/device?code=BCDF-GHJK", "interval": 2, "expires_in": 600})
        if u.path == "/auth/device/exchange":
            g = S["grants"].pop(b.get("code"), None)
            if not g: return self._send(404, {"ok": False, "error": "unknown or used grant"})
            ch = base64.urlsafe_b64encode(hashlib.sha256(b.get("verifier", "").encode()).digest()).rstrip(b"=").decode()
            if ch != g: return self._send(403, {"ok": False, "error": "verifier does not match"})
            return self._send(200, {"ok": True, "api_key": KEY, "email": "sam@acme.test"})
        if u.path == "/memory/tool":
            if not self._authed(): return self._send(401, {"error": "no key"})
            S["tool_calls"].append(b)
            if b.get("name") == "use_space" and b["arguments"].get("confirm"):
                S["pending"] = b["arguments"]["workspace"]
                return self._send(200, {"switched": True, "message": "Done"})
            return self._send(200, {"pending_confirmation": True})
        self._send(404, {})
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = dict(urllib.parse.parse_qsl(u.query))
        if u.path.startswith("/auth/device/"):
            d = S["devices"].get(u.path.rsplit("/", 1)[1])
            if not d: return self._send(404, {"status": "unknown"})
            if d["status"] == "approved":
                S["devices"].pop(u.path.rsplit("/", 1)[1]); return self._send(200, {"status": "approved", "api_key": KEY, "email": "sam@acme.test"})
            return self._send(200, {"status": "pending", "interval": 2})
        if not self._authed(): return self._send(401, {"error": "no key"})
        if u.path == "/memory/spaces": return self._send(200, SPACES)
        if u.path == "/memory/working-set/delta":
            S["delta_calls"].append(q); sid = q.get("session_id")
            if sid and S["pending"]: S["pins"][sid] = S["pending"]; S["pending"] = None   # claim, as _session_route does
            ws = S["pins"].get(sid, "home_u1")
            n = 3 if ws == "team-alpha" else 1
            return self._send(200, {"changed": [], "effective_space": {"workspace": ws, "personal": ws == "home_u1",
                                                                       "name": "Team Alpha" if n == 3 else ws, "member_count": n}})
        if u.path == "/memory/working-set": return self._send(200, "## memory")
        if u.path == "/memory/recap": return self._send(200, "")
        self._send(404, {})
srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake); threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{srv.server_address[1]}"

HOME = tempfile.mkdtemp()
def env(**extra):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("ASSERTION_", "CONTEXT_TREE_"))}
    e.update(HOME=HOME, ASSERTION_SERVER_URL=BASE, ASSERTION_STUDIO_DEVICE_URL="http://studio.test/device",
             ASSERTION_NO_BROWSER="1", ASSERTION_LOGIN_CALLBACK="on", DISPLAY=":0", TMPDIR=os.path.join(HOME, "tmp"))
    e.pop("SSH_CONNECTION", None); e.pop("SSH_TTY", None); e.pop("SSH_CLIENT", None)
    e.update(extra); return e
os.makedirs(os.path.join(HOME, "tmp"))
CREDS = os.path.join(HOME, ".assertion", "credentials.json")
def run(args, **extra):
    p = subprocess.run([sys.executable, os.path.join(HERE, "assertion.py")] + args, env=env(**extra),
                       capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout + p.stderr
def mode(p): return stat.S_IMODE(os.stat(p).st_mode)
def reset_home():
    for p in (CREDS, os.path.join(HOME, ".cursor", "mcp.json"), os.path.join(HOME, ".codex", "config.toml")):
        if os.path.exists(p): os.remove(p)

# ---- 1. the headers helper -------------------------------------------------------------------
def helper(**extra):
    p = subprocess.run([sys.executable, os.path.join(HERE, "mcp_headers.py")], env=env(**extra), capture_output=True, text=True)
    return json.loads(p.stdout)
check("helper: no key -> {} (discovery still works, tool calls are refused)", helper() == {})
old = {"x-api-key": "env-key-1", "X-Assertion-Workspace": "default"}   # what ${ASSERTION_API_KEY} / ${ASSERTION_WORKSPACE:-default} gave
check("helper: env-var user gets byte-identical headers", json.dumps(helper(ASSERTION_API_KEY="env-key-1")) == json.dumps(old))
check("helper: env workspace passes through like ${ASSERTION_WORKSPACE}",
      helper(ASSERTION_API_KEY="k", ASSERTION_WORKSPACE="dev-sam") == {"x-api-key": "k", "X-Assertion-Workspace": "dev-sam"})
os.makedirs(os.path.dirname(CREDS)); open(CREDS, "w").write(json.dumps({"api_key": "file-key"}))
check("helper: signed in (file) -> key from the credentials file", helper()["x-api-key"] == "file-key")
check("helper: the environment still wins over the file", helper(ASSERTION_API_KEY="env-key-1")["x-api-key"] == "env-key-1")
os.remove(CREDS)
mcp = json.load(open(os.path.join(ROOT, "plugin", ".mcp.json")))["mcpServers"]["assertion"]
check(".mcp.json: key comes from the helper, not a template", "headers" not in mcp and "mcp_headers.py" in mcp.get("headersHelper", ""))
check(".mcp.json: URL unchanged", mcp["url"] == "${ASSERTION_SERVER_URL:-https://memory.assertion-ai.com}/memory/mcp")

# ---- 2. browser sign-in (local callback + PKCE) ------------------------------------------------
os.makedirs(os.path.join(HOME, ".cursor"))
open(os.path.join(HOME, ".cursor", "mcp.json"), "w").write(json.dumps({"mcpServers": {
    "other": {"url": "https://x"}, "assertion": {"url": "https://memory.assertion-ai.com/memory/mcp/default",
                                                 "headers": {"Authorization": "Bearer OLD"}}}}))
os.makedirs(os.path.join(HOME, ".codex"))
TOML_OTHER = 'model = "o3"\n\n[mcp_servers.other]\nurl = "https://y"\n'
open(os.path.join(HOME, ".codex", "config.toml"), "w").write(
    TOML_OTHER + '\n[mcp_servers.assertion]\nurl = "https://memory.assertion-ai.com/memory/mcp/ws1"\nhttp_headers = { Authorization = "Bearer OLD" }\n'
    '\n[mcp_servers.assertion.env]\nX = "1"\n\n[profiles.fast]\nmodel = "o4"\n')

p = subprocess.Popen([sys.executable, os.path.join(HERE, "assertion.py"), "login", "--client", "claude-code"],
                     env=env(ASSERTION_LOGIN_WAIT="30"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
url = ""
lines = []
for line in p.stdout:
    lines.append(line)
    if "studio.test/device?" in line:
        url = line.strip(); break
q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
check("login: opens Studio's /device with port, state, challenge and a device name",
      all(q.get(k) for k in ("port", "state", "challenge", "device")) and q["device"].startswith("Claude Code on"), url)
cb = f"http://127.0.0.1:{q.get('port')}/callback"
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k): return None
def get(u):
    try:
        return urllib.request.build_opener(NoRedirect).open(u, timeout=15).status
    except urllib.error.HTTPError as e:
        return e.code
check("login: a callback with the wrong state is refused", get(cb + "?" + urllib.parse.urlencode({"state": "x" * 32, "code": "c"})) == 400)
# Studio: the signed-in user clicks Connect -> a one-time grant bound to the challenge -> browser to the callback.
code = secrets.token_urlsafe(16); S["grants"][code] = q["challenge"]
try:
    r = urllib.request.build_opener(NoRedirect).open(cb + "?" + urllib.parse.urlencode({"state": q["state"], "code": code}), timeout=15)
    status, loc = r.status, r.headers.get("Location")
except urllib.error.HTTPError as e:
    status, loc = e.code, e.headers.get("Location")
check("login: callback redeems the grant and sends the browser to Studio's Connected page",
      status == 302 and loc and loc.startswith("http://studio.test/device?connected=1"), f"{status} {loc}")
out = "".join(lines) + p.stdout.read(); p.wait(30)
check("login: reports the account and that memory is on now", "Signed in as sam@acme.test" in out and "no restart" in out, out)
check("login: never prints the key", KEY not in out)
creds = json.load(open(CREDS))
check("login: key saved to ~/.assertion/credentials.json", creds.get("api_key") == KEY and creds.get("email") == "sam@acme.test")
check("login: credentials file is 0600", mode(CREDS) == 0o600, oct(mode(CREDS)))
cm = json.load(open(os.path.join(HOME, ".cursor", "mcp.json")))
check("login: Cursor's assertion server gets the new key", cm["mcpServers"]["assertion"]["headers"] == {"Authorization": f"Bearer {KEY}"})
check("login: Cursor's other servers and URL are kept", cm["mcpServers"]["other"] == {"url": "https://x"}
      and cm["mcpServers"]["assertion"]["url"].endswith("/memory/mcp/default"))
check("login: Cursor mcp.json is 0600", mode(os.path.join(HOME, ".cursor", "mcp.json")) == 0o600)
toml = open(os.path.join(HOME, ".codex", "config.toml")).read()
check("login: Codex's assertion table gets the new key, same URL",
      f'http_headers = {{ Authorization = "Bearer {KEY}" }}' in toml and 'url = "https://memory.assertion-ai.com/memory/mcp/ws1"' in toml
      and "Bearer OLD" not in toml, toml)
check("login: the rest of config.toml is kept byte for byte",
      toml.startswith(TOML_OTHER) and '[profiles.fast]\nmodel = "o4"\n' in toml, toml)
check("login: config.toml is 0600", mode(os.path.join(HOME, ".codex", "config.toml")) == 0o600)

# ---- 3. already signed in ------------------------------------------------------------------
rc, out = run(["login"])
check("login: already signed in -> says so, starts nothing", rc == 0 and "Already signed in as sam@acme.test" in out and "studio.test" not in out, out)

# ---- 4. the click comes after the foreground gives up -----------------------------------------
reset_home()
p = subprocess.Popen([sys.executable, os.path.join(HERE, "assertion.py"), "login", "--client", "cursor"],
                     env=env(ASSERTION_LOGIN_WAIT="1"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
out = p.communicate(timeout=60)[0]
q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse([l for l in out.split() if "studio.test/device?" in l][0]).query))
check("login: still waiting -> says the sign-in stays open", "Still waiting" in out and not os.path.exists(CREDS), out)
code = secrets.token_urlsafe(16); S["grants"][code] = q["challenge"]
get(f"http://127.0.0.1:{q['port']}/callback?" + urllib.parse.urlencode({"state": q["state"], "code": code}))
t = time.time()
while not os.path.exists(CREDS) and time.time() - t < 10: time.sleep(0.2)
check("login: a late click still signs in (the detached worker saves the key)", os.path.exists(CREDS) and json.load(open(CREDS))["api_key"] == KEY)
check("login from Cursor: creates Cursor's assertion server when there was none",
      json.load(open(os.path.join(HOME, ".cursor", "mcp.json")))["mcpServers"]["assertion"]["headers"]["Authorization"] == f"Bearer {KEY}")
check("login from Cursor: does not create a Codex config", not os.path.exists(os.path.join(HOME, ".codex", "config.toml")))

# ---- 5. device code (no browser on this machine) ------------------------------------------------
reset_home()
p = subprocess.Popen([sys.executable, os.path.join(HERE, "assertion.py"), "login", "code"],
                     env=env(ASSERTION_LOGIN_WAIT="20"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
time.sleep(1.5)
for d in S["devices"].values(): d["status"] = "approved"
out = p.communicate(timeout=60)[0]
check("login code: shows the code and the link", "BCDF-GHJK" in out and "http://studio/device?code=BCDF-GHJK" in out, out)
check("login code: approval signs in", "Signed in as sam@acme.test" in out and json.load(open(CREDS))["api_key"] == KEY, out)
check("login code: never prints the key", KEY not in out)
check("login over SSH: falls back to the code flow", subprocess.run([sys.executable, "-c",
      "import sys; sys.path.insert(0, %r); import assertion as a; print(a.can_use_local_callback({'SSH_TTY': '/dev/ttys1'}, 'Darwin'))" % HERE],
      capture_output=True, text=True).stdout.strip() == "False")

# ---- 6. spaces ------------------------------------------------------------------------------
SID = "7f1c2d3e-aaaa-bbbb-cccc-1234567890ab"
rc, out = run(["space", "--session", SID])
check("space: lists spaces with member counts", rc == 0 and "team-alpha" in out and "Team Alpha" in out and "3 members" in out, out)
check("space: states this session's space and the default", "This session:              personal" in out and "Default for new sessions:  personal" in out, out)
check("space: listing switches nothing", not S["tool_calls"])
rc, out = run(["space", "--session", SID, "Team", "Alpha"])
tc = S["tool_calls"][-1] if S["tool_calls"] else {}
check("space NAME: the name is the confirmation (one confirmed use_space)",
      tc == {"name": "use_space", "arguments": {"workspace": "team-alpha", "confirm": True}}, str(S["tool_calls"]))
check("space NAME: claimed for THIS session at once", S["pins"].get(SID) == "team-alpha" and S["delta_calls"][-1].get("session_id") == SID)
check("space NAME: says where memory goes now, who sees it, and how to undo",
      "now reads from and saves memory to the team space \"Team Alpha\", shared with 2 teammates" in out
      and "Undo: /assertion:space personal" in out, out)
rc, out = run(["space", "--session", SID])
check("space: now shows the team space for this session", "This session:              Team Alpha (team space, 3 members)" in out, out)
n = len(S["tool_calls"])
rc, out = run(["space", "--session", SID, "nope"])
check("space: unknown name -> nothing switched", rc == 1 and len(S["tool_calls"]) == n and "No space called" in out, out)
dn = len(S["delta_calls"])
rc, out = run(["space", "--client", "cursor", "team-alpha"])
check("space from Cursor (no session id): switches from the next message, says so",
      "from your next message" in out and len(S["delta_calls"]) == dn and "Undo: /assertion-space personal" in out, out)
check("space: a literal ${CLAUDE_SESSION_ID} is never sent as a session id", subprocess.run([sys.executable, "-c",
      "import sys; sys.path.insert(0, %r); import assertion as a; print(repr(a._usable_sid('${CLAUDE_SESSION_ID}')))" % HERE],
      capture_output=True, text=True).stdout.strip() == "''")
os.remove(CREDS)
rc, out = run(["space"])
check("space: signed out -> points at /assertion:login", rc == 1 and "/assertion:login" in out, out)

# ---- 7. SessionStart when signed out ----------------------------------------------------------
def hook(payload, **extra):
    p = subprocess.run([sys.executable, os.path.join(HERE, "sessionstart_inject.py")], input=json.dumps(payload),
                       env=env(**extra), capture_output=True, text=True, timeout=30)
    return json.loads(p.stdout) if p.stdout.strip() else {}
check("SessionStart signed out: says memory is off and how to turn it on",
      hook({"source": "startup"}) == {"systemMessage": "Assertion memory is off — run /assertion:login to turn it on."})
check("SessionStart signed out, Cursor: asks the assistant to pass it on",
      "/assertion-login" in hook({"cursor_version": "1.7"}).get("additional_context", ""))
check("SessionStart signed out: quiet after a compaction", hook({"source": "compact"}) == {})
got = hook({"source": "startup"}, ASSERTION_API_KEY=KEY)
check("SessionStart signed in: unchanged working-set injection, no signed-out notice",
      "## memory" in json.dumps(got) and "memory is off" not in json.dumps(got), json.dumps(got)[:200])

# ---- 8. commands are run by Claude Code, not interpreted ----------------------------------------
for name, needle in (("login", "assertion.py\" login --client claude-code"), ("space", "space --client claude-code --session \"${CLAUDE_SESSION_ID}\""),
                     ("upgrade", "upgrade --client claude-code")):
    text = open(os.path.join(ROOT, "plugin", "commands", f"{name}.md")).read()
    check(f"/assertion:{name}: runs the script from a ! line", "!`python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/assertion.py" in text and needle in text)
    check(f"/assertion:{name}: only the user can run it (args reach a shell)", "disable-model-invocation: true" in text)

# ---- 9. Cursor installer: commands carry this clone's path; key files are owner-only ----------
reset_home()
inst = os.path.join(ROOT, "plugin", "cursor", "install_cursor.py")
r = subprocess.run([sys.executable, inst, "--key", KEY, "--server", BASE], env=env(), capture_output=True, text=True, timeout=60)
cdir = os.path.join(HOME, ".cursor", "commands")
sp = open(os.path.join(cdir, "assertion-space.md")).read() if os.path.exists(os.path.join(cdir, "assertion-space.md")) else ""
check("cursor install: copies catchup, upgrade, assertion-login and assertion-space",
      all(os.path.exists(os.path.join(cdir, n)) for n in ("catchup.md", "upgrade.md", "assertion-login.md", "assertion-space.md")), r.stdout + r.stderr)
check("cursor install: commands name this clone's script by absolute path",
      os.path.join(HERE, "assertion.py") in sp and "{{ASSERTION}}" not in sp and "space --client cursor" in sp)
check("cursor install: mcp.json and credentials are 0600",
      mode(os.path.join(HOME, ".cursor", "mcp.json")) == 0o600 and mode(CREDS) == 0o600)
check("cursor install: never prints the key", KEY not in r.stdout + r.stderr)
os.remove(os.path.join(cdir, "upgrade.md"))
subprocess.run([sys.executable, inst, "--commands-only"], env=env(), capture_output=True, text=True, timeout=60)
check("cursor --commands-only: restores the commands (what /upgrade runs after a pull)", os.path.exists(os.path.join(cdir, "upgrade.md")))
subprocess.run([sys.executable, inst, "--uninstall"], env=env(), capture_output=True, text=True, timeout=60)
check("cursor uninstall: removes all four commands", not any(os.path.exists(os.path.join(cdir, n))
      for n in ("catchup.md", "upgrade.md", "assertion-login.md", "assertion-space.md")))

# ---- 10. no SessionStart (plugin turned on by /reload-plugins): the first prompt covers it -----
def prompt(payload, **extra):
    p = subprocess.run([sys.executable, os.path.join(HERE, "userpromptsubmit_delta.py")], input=json.dumps(payload),
                       env=env(**extra), capture_output=True, text=True, timeout=30)
    return json.loads(p.stdout) if p.stdout.strip() else {}
ctx = lambda o: (o.get("hookSpecificOutput") or {}).get("additionalContext", "")
reset_home()
sid = "reload-" + secrets.token_hex(6)
first = prompt({"session_id": sid, "prompt": "hi"}, ASSERTION_API_KEY=KEY)
check("reload, signed in: first prompt carries the working set", "<persistent_project_memory>" in ctx(first) and "## memory" in ctx(first), json.dumps(first)[:300])
check("reload, signed in: only once", "<persistent_project_memory>" not in ctx(prompt({"session_id": sid, "prompt": "again"}, ASSERTION_API_KEY=KEY)))
sid = "normal-" + secrets.token_hex(6)
hook({"source": "startup", "session_id": sid}, ASSERTION_API_KEY=KEY)
check("normal start: SessionStart already injected, the first prompt does not repeat it",
      "<persistent_project_memory>" not in ctx(prompt({"session_id": sid, "prompt": "hi"}, ASSERTION_API_KEY=KEY)))
sid = "reload-out-" + secrets.token_hex(6)
check("reload, signed out: first prompt says memory is off", prompt({"session_id": sid, "prompt": "hi"}).get("systemMessage") == "Assertion memory is off — run /assertion:login to turn it on.")
check("reload, signed out: said once, not every prompt", prompt({"session_id": sid, "prompt": "again"}) == {})
check("reload, then sign in: the next prompt brings the working set", "## memory" in ctx(prompt({"session_id": sid, "prompt": "go"}, ASSERTION_API_KEY=KEY)))
sid = "start-out-" + secrets.token_hex(6)
hook({"source": "startup", "session_id": sid})
check("signed out at start: the prompt hook does not repeat the notice", prompt({"session_id": sid, "prompt": "hi"}) == {})
check("signed out at start, signed in since: the next prompt brings the working set",
      "## memory" in ctx(prompt({"session_id": sid, "prompt": "go"}, ASSERTION_API_KEY=KEY)))
check("Cursor: no first-prompt working set (it has its own delivery)",
      not os.path.exists(os.path.join(HOME, "proj", ".cursor")) and
      prompt({"conversation_id": "cur-" + secrets.token_hex(6), "cursor_version": "1.7", "prompt": "hi"}, ASSERTION_API_KEY=KEY) == {"continue": True})

# ---- 11. Codex hooks run through a stable launcher, so an upgrade can't break an open session --
import shutil
CX = os.path.join(HOME, "cx")                                  # a stand-in CODEX_HOME
PARENT = os.path.join(CX, "plugins", "cache", "assertion-ai", "assertion")
LAUNCHER = os.path.join(HOME, ".assertion", "bin", "codex-hook")
REAL = open(os.path.join(HERE, "codex_hook.py")).read()
def fake_version(v):
    d = os.path.join(PARENT, v, "scripts"); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "codex_hook.py"), "w").write(REAL + f"\n# version {v}\n")
    for name in ("sessionstart_inject.py", "userpromptsubmit_delta.py", "hook_on_stop.py"):
        open(os.path.join(d, name), "w").write(
            "import os, sys\nprint(%r, os.environ.get('PLUGIN_ROOT'), sys.stdin.read(), sys.argv[1:])\n" % f"{name}@{v}")
for v in ("0.3.8", "0.3.9", "0.3.10"):
    fake_version(v)
hooks = json.load(open(os.path.join(ROOT, "plugin", "codex", "hooks.json")))["hooks"]
cmds = {ev: hooks[ev][0]["hooks"][0]["command"] for ev in ("SessionStart", "UserPromptSubmit", "Stop")}
def run_hook(ev, plugin_root, stdin='{"hook_event_name": "x"}', **extra):
    e = env(CODEX_HOME=CX, PLUGIN_ROOT=plugin_root, CLAUDE_PLUGIN_ROOT=plugin_root, **extra)
    p = subprocess.run(["sh", "-c", cmds[ev]], input=stdin, env=e, capture_output=True, text=True, timeout=30)
    return p.returncode, p.stdout.strip(), p.stderr.strip()
check("codex hooks: no command names a version", not any(re.search(r"\d+\.\d+\.\d+", c) for c in cmds.values()))
check("codex hooks: every command goes through the stable launcher",
      all('$HOME/.assertion/bin/codex-hook' in c and c.endswith(s) for c, s in
          zip(cmds.values(), ("sessionstart_inject.py", "userpromptsubmit_delta.py", "hook_on_stop.py"))))
check("Claude Code hooks are unchanged (no launcher)", "codex-hook" not in open(os.path.join(ROOT, "plugin", "hooks", "hooks.json")).read())
if os.path.exists(LAUNCHER): os.remove(LAUNCHER)
rc, out, err = run_hook("SessionStart", os.path.join(PARENT, "0.3.9"))
check("launcher: runs the NEWEST version (0.3.10 beats 0.3.9 and 0.3.8)", rc == 0 and out.startswith("sessionstart_inject.py@0.3.10"), out + err)
check("launcher: passes stdin through", '{"hook_event_name": "x"}' in out, out)
check("launcher: points PLUGIN_ROOT at the version it runs", os.path.join(PARENT, "0.3.10") in out, out)
check("launcher: first run installs the stable copy, 0755, from the newest version",
      os.path.exists(LAUNCHER) and mode(LAUNCHER) == 0o755 and "# version 0.3.10" in open(LAUNCHER).read())
shutil.rmtree(os.path.join(PARENT, "0.3.9"))                  # the session's own version is gone (upgrade)
rc, out, err = run_hook("Stop", os.path.join(PARENT, "0.3.9"))
check("after an upgrade removes the session's version: the hook still runs, from the new version",
      rc == 0 and out.startswith("hook_on_stop.py@0.3.10"), out + err)
fake_version("0.3.11")
rc, out, _ = run_hook("UserPromptSubmit", os.path.join(PARENT, "0.3.9"))
check("a later version is picked up at call time, and refreshes the stable copy",
      out.startswith("userpromptsubmit_delta.py@0.3.11") and "# version 0.3.11" in open(LAUNCHER).read(), out)
rc, out, _ = run_hook("SessionStart", "", ASSERTION_SCRIPTS_DIR=os.path.join(PARENT, "0.3.8", "scripts"))
check("ASSERTION_SCRIPTS_DIR still overrides", out.startswith("sessionstart_inject.py@0.3.8"), out)
p = subprocess.run([sys.executable, LAUNCHER, "../../etc/x.py"], env=env(CODEX_HOME=CX), capture_output=True, text=True)
check("launcher: refuses a script name that isn't a plain file name", p.returncode == 0 and not p.stdout)
shutil.rmtree(CX)
rc, out, err = run_hook("SessionStart", os.path.join(PARENT, "0.3.9"))
check("launcher: nothing installed -> exits 0 silently (fail-open)", rc == 0 and out == "" and err == "", out + err)
os.remove(LAUNCHER)
rc, out, err = run_hook("SessionStart", "/nonexistent/0.3.7")
check("no launcher and the plugin dir is gone -> exits 0 silently", rc == 0 and out == "" and err == "", out + err)

srv.shutdown()
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
