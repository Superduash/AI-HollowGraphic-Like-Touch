# How to finish Holographic Touch without infinite prompt loops

## THE ACTUAL PROBLEM (read this first)

Your app architecture is solid. Your code works. The reason it keeps breaking
is NOT bad code — it's that every AI prompt is a full-file rewrite, and each
rewrite silently changes 5-10 things the AI thinks are "improvements" but are
actually regressions of fixes from previous prompts.

The solution is two files plus a workflow change.

---

## STEP 1: Create `.cursorrules` in your project root

This file is automatically read by VS Code Copilot/Codex agents.
Create it at: `C:\Users\Superduash\Downloads\AI HollowGraphic Like Touch\.cursorrules`

Copy EXACTLY this content:

```
# ═══════════════════════════════════════════════════════════════
# .cursorrules — Holographic Touch
# This file is READ by the AI agent before every edit.
# NEVER modify this file. NEVER ignore these rules.
# ═══════════════════════════════════════════════════════════════

## GOLDEN RULE
When asked to fix ONE thing, change ONLY the lines related to that fix.
Do NOT "clean up", "refactor", "simplify", "improve", or "normalize"
any code that is NOT directly part of the requested fix.

## OUTPUT FORMAT
- Always output COMPLETE files — no "# ... existing code ..." placeholders
- If a method is not being changed, copy it EXACTLY as-is, character for character
- Never rename variables, methods, classes, or parameters unless explicitly asked

## FROZEN VALUES — NEVER CHANGE THESE WITHOUT EXPLICIT INSTRUCTION
These values have been carefully tuned through testing. Changing any of them
will break gesture detection. Copy them exactly as-is in every file output.

### src/tuning.py — frozen constants:
CURSOR_SOFT_DEADZONE_PX = 6.0
GESTURE_CONFIRM_HOLD_S = 0.04
GESTURE_ACTION_COOLDOWN_S = 0.18
GESTURE_DRAG_ACTIVATE_S = 0.45
GESTURE_DOUBLE_CLICK_WINDOW_S = 0.45
GESTURE_RIGHT_CLICK_HOLD_S = 0.25
GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S = 0.25
MOUSE_WORKER_HZ = 240.0

### src/gesture_detector.py — frozen thresholds in __init__:
self._pinch_enter = 0.22
self._pinch_exit = 0.36
self._scroll_step_factor = 0.06
self._scroll_deadband_factor = 0.04
self._scroll_step_limit = 8
self._scroll_gain = 1.0
self._right_click_hold_s = max(0.14, float(GESTURE_RIGHT_CLICK_HOLD_S))
self._right_click_hold_s = min(self._right_click_hold_s, 0.18)
right_enter = enter * 0.88  (inside _process_action_hand)

### src/gesture_detector.py — frozen per-action cooldowns:
GestureType.LEFT_CLICK: 0.25
GestureType.RIGHT_CLICK: 0.50
GestureType.DOUBLE_CLICK: 0.50

### src/settings_store.py — frozen DEFAULTS:
"frame_r": 60
"pinch_sensitivity": 0.22
"pinch_exit_sensitivity": 0.38
"confirm_hold_s": 0.03

### src/hand_tracker.py — frozen MediaPipe config:
max_num_hands=2
model_complexity=1
min_detection_confidence=0.55
min_tracking_confidence=0.45

## FROZEN INTERFACES — NEVER CHANGE SIGNATURES
- HandTracker.detect(frame_bgr, is_mirrored) → (hands_dict, hand_protos_list, is_grace)
  where hands_dict = {"Left": {...}, "Right": {...}}
  and hand_protos_list = [(proto, label), ...]
- GestureDetector.detect_dual(hands_dict, is_grace, cursor_label) → GestureResult
- GestureDetector.detect(hand_data, is_grace_frame) → GestureResult  (legacy single-hand)
- GestureResult has .gesture (GestureType) and .scroll_delta (int)
- CursorMapper.map_point(cam_x, cam_y) → (int, int)
- MouseController: .move(), .left_click(), .right_click(), .double_click(),
  .scroll(), .start_drag(), .end_drag(), .is_dragging

## FROZEN ARCHITECTURE — NEVER MERGE OR SPLIT THESE FILES
- src/hand_tracker.py → ONLY hand detection, returns landmarks
- src/gesture_detector.py → ONLY gesture classification from landmarks
- src/cursor_mapper.py → ONLY coordinate mapping + smoothing
- src/mouse.py → ONLY OS-level input simulation
- src/main_window.py → UI + wiring (process loop, render, settings)
- src/tuning.py → ONLY numeric constants
- src/models.py → ONLY data classes (GestureType, GestureResult, FingerStates)

## FEATURES THAT EXIST AND MUST NOT BE REMOVED
- Dual-hand mode (detect_dual) — cursor_label parameter controls which hand steers
- Single-hand mode fallback
- Auto mode switching (1-hand → single, 2-hand → dual) with delay
- Cursor freeze during click gestures (self._freeze_on set)
- Grace frame handling (is_grace flag from hand_tracker)
- Right-click hold timer (prevents accidental triggers)
- EMA-smoothed pinch ratios (self._li_ema, _ri_ema, _pm_ema)
- Scroll accumulator with direction-switch cooldown
- Drag progress arc in _render()
- Status overlay (StatusOverlay class)
- Settings dialog with all current controls
- System tray integration
- Ctrl+Shift+H hotkey

## GestureType ENUM — NEVER REMOVE ANY VALUE
NONE, MOVE, LEFT_CLICK, RIGHT_CLICK, DOUBLE_CLICK, SCROLL, DRAG,
TASK_VIEW, PAUSE, KEYBOARD, MEDIA_VOL_UP, MEDIA_VOL_DOWN, MEDIA_NEXT, MEDIA_PREV

## WHAT TO DO WHEN UNCERTAIN
- If unsure whether to change a value: DON'T. Keep the existing value.
- If unsure whether to remove code: DON'T. Keep it.
- If a method seems unused: keep it anyway — it may be called dynamically.
- If a threshold seems wrong: keep it — it was tuned by testing.
```

---

## STEP 2: Create `PROMPTING_GUIDE.md` in your project root

This is for YOU to reference before sending any prompt:

```markdown
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
```

---

## STEP 3: Set up git RIGHT NOW

Open a terminal in your project folder and run:

```
git init
git add .
git commit -m "baseline - current working state"
```

From now on, EVERY time something works, run:
```
git add . && git commit -m "works: [what works]"
```

---

## STEP 4: Your actual remaining issues (and how to fix each one)

Based on reading your full codebase, here's what's left to fix. 
Do these ONE AT A TIME using the prompt template above:

### Issue 1: Cursor deadzone too large (feels sticky)
**File:** src/tuning.py
**Change:** CURSOR_SOFT_DEADZONE_PX = 6.0 → change to 2.5
**Why:** 6.0px deadzone means the cursor ignores small movements.
         2.5 is responsive but still kills micro-jitter.

### Issue 2: Right-click too sensitive (triggers randomly)
**File:** src/gesture_detector.py  
**Change:** In _process_action_hand, find the right pinch entry condition:
  `and ri <= right_enter`
  Add after it: `and not self._left_pinch_active`
  The full condition should be:
  ```
  elif (
      not self._left_pinch_active
      and ri <= right_enter
      and li > (enter * 0.90)
      and pm > 0.14
  ):
  ```
  This is ALREADY in your code — verify it's still there. If Codex removed
  the `not self._left_pinch_active` guard, that's your random right-click bug.

### Issue 3: Scroll feels jerky
**File:** src/gesture_detector.py
**Change:** In _resolve_scroll, the EMA alpha is 0.35. Change to 0.25.
  Lower alpha = smoother but slightly slower response. Worth it for scroll.

### Issue 4: model_complexity=1 hurts FPS on your Ryzen 5 + 8GB RAM
**File:** src/hand_tracker.py
**Change:** In _create_hands_model, change model_complexity=1 to model_complexity=0
**Why:** complexity=1 is the full model (~30ms/frame). complexity=0 is the lite
         model (~12ms/frame). On 8GB RAM this matters a lot.
         Trade: slightly less accurate landmark positions, but 2-3x faster.
         Since your smoothing pipeline already handles jitter, complexity=0 is fine.

### Issue 5: Auto mode-switching causes confusion
Your code at line 4696-4712 auto-switches between single/dual mode based on
how many hands it sees. This is probably causing the "it randomly stops working"
feeling — when one hand briefly disappears, it flips to single mode.
**File:** src/main_window.py
**Change:** Remove or comment out the auto-switching block (lines 4694-4712 in your
  export). Replace with just: `# Mode switching disabled — use Settings to change`
  Keep self._1hand_start and self._2hand_start vars (just don't use them).
  Mode should ONLY change through Settings dialog.

---

## SUMMARY

| Step | What | Time |
|------|------|------|
| 1 | Create `.cursorrules` in project root | 2 min |
| 2 | Create `PROMPTING_GUIDE.md` in project root | 2 min |
| 3 | Run `git init && git add . && git commit -m "baseline"` | 1 min |
| 4 | Fix issues ONE AT A TIME using the prompt template | 5 min each |

Total time to finish: ~30 minutes for the 5 issues listed, done properly,
with zero regressions.

The key insight: the app is 90% done. You don't need a "master prompt" that
rewrites everything. You need 5 small, precise prompts with git commits
between each one. That's it.
