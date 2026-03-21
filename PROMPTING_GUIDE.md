# How to prompt Codex/GPT to fix this app without regressions

## Before EVERY prompt:
1. git add . && git commit -m "before: [what you're about to fix]"
2. Test the app — note what currently works
3. Write the prompt following the rules below
4. After applying: test ONLY the thing you changed
5. If it works: git commit -m "fixed: [what you fixed]"
6. If it broke something: git checkout . (reverts everything)

## Prompt template (copy this structure every time):

```
Read .cursorrules first. Follow every rule in it.

TASK: [one specific thing — e.g. "Fix scroll direction being inverted"]

FILE TO CHANGE: src/gesture_detector.py

EXACT CHANGE:
In the _resolve_scroll method, on the line:
    dy = float(self._scroll_prev_y) - current_y
Change to:
    dy = current_y - float(self._scroll_prev_y)

Do NOT change any other line in this file.
Do NOT change any threshold values.
Do NOT change any other method.
Output the COMPLETE file.
```

## Rules for writing prompts:
1. ONE file per prompt. Never "fix gesture_detector.py AND main_window.py"
2. NAME the exact method and line you want changed
3. Say what to change it FROM and what to change it TO
4. Always end with "Do NOT change any other line in this file"
5. Always say "Output the COMPLETE file"
6. Never say "refactor", "clean up", "improve", "optimize"
7. Never say "fix all issues" or "make it work better"
8. Never change the fingertip smoothing multiplier (tip_blend = base_blend * 0.55)
9. Never change the outer_slack_ratio (0.10) or max_jump (scr_diag * 0.25)
10. Never remove the _movement_suppress logic from gesture_detector
11. Never change _dual_cursor_point blend ratio (0.7 tip + 0.3 palm)

## If you need multiple fixes:
Do them as separate prompts, one at a time, committing between each:
- Prompt 1: fix scroll → test → commit
- Prompt 2: fix right-click → test → commit
- Prompt 3: fix cursor jitter → test → commit

## What to do when Codex changes things you didn't ask for:
1. Run: git diff (shows everything that changed)
2. Look for changes OUTSIDE the area you asked about
3. If you see threshold values changed, method signatures changed,
   or code removed: git checkout . and re-prompt more specifically
4. If the diff looks clean (only your requested change): test and commit

## Emergency recovery:
If the app is completely broken and you can't figure out what changed:
    git log --oneline          (see your commit history)
    git checkout [commit-hash] (go back to a working version)
    git checkout -b recovery   (make a new branch from there)
