Update the Assertion memory plugin to the latest version.

The Cursor install runs from a local git clone of the Assertion plugin, so it
updates with a pull in that clone (NOT a plugin-manager command):

```
cd assertion && git pull
```

Run this in the directory where the Assertion plugin was cloned. If it was cloned
somewhere other than `./assertion`, `cd` to that clone first, then `git pull`.

Then report the result plainly:

- If `git pull` brought in new commits, tell me to fully quit and reopen Cursor in
  a fresh session so the new hooks take effect — they only load at launch.
- If it says "Already up to date", just tell me I'm on the latest; no restart needed.

Run only that pull; don't change anything else.
