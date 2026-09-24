"""install_source(): only the marketplace name, never a path. Run: python3 plugin/scripts/test_install_source.py"""
import importlib.util, os, sys, shutil, tempfile
root = os.path.dirname(os.path.abspath(__file__))
fails = 0
def load(at):
    spec = importlib.util.spec_from_file_location("_creds_t", at); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def case(name, path, want):
    global fails
    d = tempfile.mkdtemp(); full = os.path.join(d, path); os.makedirs(full)
    shutil.copy(os.path.join(root, "_creds.py"), full)
    got = load(os.path.join(full, "_creds.py")).install_source()
    ok = got == want; fails += not ok
    print(("PASS " if ok else "FAIL ") + f"{name}: {got!r}" + ("" if ok else f" (want {want!r})"))
case("catalog install", ".claude/plugins/cache/claude-community/assertion/0.3.6/scripts", "claude-community")
case("GitHub repo install", ".claude/plugins/cache/assertion-ai/assertion/0.3.6/scripts", "assertion-ai")
case("Codex marketplace install", ".codex/plugins/cache/assertion-ai/assertion/0.3.6/scripts", "assertion-ai")
case("local checkout (Cursor, dev)", "code/assertion-plugin/plugin/scripts", "")
case("odd characters stripped, no path leaks", ".claude/plugins/cache/We ird$Name/assertion/1/scripts", "weirdname")
print("ALL PASS" if not fails else f"{fails} FAILED"); sys.exit(1 if fails else 0)
