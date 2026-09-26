Update the Assertion memory plugin to the latest version. Run exactly this one command and wait
for it to finish:

```
python3 "$(ls -d ~/.codex/plugins/cache/*/assertion/*/scripts | sort -V | tail -1)/assertion.py" upgrade --client codex
```

Then show me its output exactly as written. Don't add to it, don't retry it, and don't run
anything else.
