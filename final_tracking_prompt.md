# FINAL PROMPT — Tracking, Smoothness, and Movement Priority
#
# Apply this AFTER all previous prompts (0-5).
# This fixes: skeleton shake, cursor zigzag, cursor pausing during finger contact,
# movement priority over clicking, margin-to-screen-edge mapping, and dual-hand
# cursor point selection.
#
# git add . && git commit -m "before: final tracking prompt"
# Then paste the prompt below into Codex.
# After: test, then git add . && git commit -m "fixed: tracking smoothness final"

════════════════════════════════════════════════════════════════
THE PROMPT — paste everything between the ``` marks into Codex
════════════════════════════════════════════════════════════════

```
Read .cursorrules first. Follow every rule in it.

TASK: Fix cursor tracking smoothness, skeleton shake, movement priority, and margin-to-edge mapping. 
Changes across 4 files. Each change is precisely described — do NOT change anything else.

=== FILE 1: src/hand_tracker.py ===
Output the COMPLETE file with these changes ONLY:

CHANGE A — Fingertip-specific stronger smoothing to kill index finger shake:
The current landmark smoothing applies the SAME blend factor to all 21 landmarks.
Fingertips (landmarks 4,8,12,16,20) jitter 3-5x more than palm landmarks because
they're at the extremity of the hand. This jitter on landmark 8 directly causes
cursor zigzag/U-V patterns.

In the detect method, find the smoothing block:
                prev_xy = self._prev_xy_by_label.get(label)
                if prev_xy is not None and len(prev_xy) == len(xy):
                    # Adaptive EMA: stronger smoothing to reduce shake while preserving fingertip response.
                    blend = 0.55 if conf >= 0.78 else (0.48 if conf >= 0.60 else 0.40)
                    smoothed_xy: list[tuple[int, int]] = []
                    for i, (cx, cy) in enumerate(xy):
                        px, py = prev_xy[i]
                        sx_i = int(px + (cx - px) * blend)
                        sy_i = int(py + (cy - py) * blend)
                        smoothed_xy.append((sx_i, sy_i))
                    xy = smoothed_xy

Replace with:
                prev_xy = self._prev_xy_by_label.get(label)
                if prev_xy is not None and len(prev_xy) == len(xy):
                    # Fingertip indices jitter much more than palm/wrist — use 
                    # weaker blend (stronger smoothing) on tips to kill shake.
                    _tip_indices = {4, 8, 12, 16, 20}
                    base_blend = 0.55 if conf >= 0.78 else (0.48 if conf >= 0.60 else 0.40)
                    tip_blend = base_blend * 0.55  # Tips get ~half the responsiveness = much less jitter
                    smoothed_xy: list[tuple[int, int]] = []
                    for i, (cx, cy) in enumerate(xy):
                        px, py = prev_xy[i]
                        b = tip_blend if i in _tip_indices else base_blend
                        sx_i = int(px + (cx - px) * b)
                        sy_i = int(py + (cy - py) * b)
                        smoothed_xy.append((sx_i, sy_i))
                    xy = smoothed_xy

This makes palm/wrist landmarks responsive (0.55 blend) while fingertips get 
heavy smoothing (0.30 blend), eliminating the index finger shake that causes 
cursor zigzag.

DO NOT change any other code in this file. Keep model_complexity=0, 
min_detection_confidence=0.55, min_tracking_confidence=0.45, 
_edge_grace_frames=10, and all other values exactly as they are.
Output the COMPLETE file.


=== FILE 2: src/cursor_mapper.py ===
Output the COMPLETE file with these changes ONLY:

CHANGE A — Increase outer slack so margin edge maps to screen edge:
In __init__, find:
        self._outer_slack_ratio = 0.04
Change to:
        self._outer_slack_ratio = 0.10
Reason: 0.04 maps only 4% of camera space past the control box to the screen
edges. At 120px margin on 480p, this is ~19 pixels — not enough to reliably
reach screen corners. 0.10 gives 48 pixels of overshoot, which maps the full
screen edge zone comfortably.

CHANGE B — Reduce max_jump clamp to prevent cursor pausing:
In map_point, find:
        max_jump = scr_diag * 0.14
Change to:
        max_jump = scr_diag * 0.25
Reason: When fingers touch (during pinch approach), MediaPipe landmarks 
teleport slightly. The 0.14 clamp catches these as "jumps" and limits them,
which creates visible cursor pausing as the EMA has to catch up over multiple
frames. 0.25 allows larger movements through instantly — actual teleports 
(hand appearing on opposite side of camera) are >0.3 of screen diagonal, 
so 0.25 still catches those.

CHANGE C — Remove the edge alpha reduction that slows cursor near screen edges:
In map_point, find and DELETE these 3 lines entirely:
        margin_px = 15
        if (raw_x <= self._screen_x + margin_px) or (raw_x >= self._screen_x + self.scr_w - margin_px) or \
           (raw_y <= self._screen_y + margin_px) or (raw_y >= self._screen_y + self.scr_h - margin_px):
            alpha *= 0.75
Reason: This reduces smoothing speed by 25% when cursor is near screen edges,
making cursor feel "sticky" at the edges. The user specifically wants cursor
to reach edges easily. The outer_slack_ratio already handles edge mapping.

DO NOT change any EMA alpha values, deadzone, prediction strength, or any 
other method. Keep set_smoothening, set_frame_margin, _virtual_screen_bounds,
control_region, and reset exactly as they are.
Output the COMPLETE file.


=== FILE 3: src/gesture_detector.py ===
Output the COMPLETE file with these changes ONLY:

CHANGE A — Suppress click detection during active cursor movement:
When the hand is actively moving (large landmark displacement between frames),
the user is MOVING the cursor, not trying to click. Finger proximity during
fast movement is incidental contact, not intentional pinch.

In _process_action_hand, right AFTER the hand_scale computation block (after
the line: self._hand_scale = max(24.0, scale)), ADD:

        # Movement priority: if hand moved significantly, suppress click entry.
        # This prevents accidental clicks during fast cursor movement when 
        # thumb brushes against index/middle finger.
        _movement_suppress = False
        if self._li_ema is not None:
            # Compare current pinch ratios to previous — if hand geometry
            # is changing rapidly, likely moving not pinching
            li_raw_now, ri_raw_now, pm_raw_now = self._pinch_ratios(xy, self._hand_scale)
            _wrist_x, _wrist_y = float(xy[0][0]), float(xy[0][1])
            _tip8_x, _tip8_y = float(xy[8][0]), float(xy[8][1])
            # If index tip is far from thumb AND hand is big (close to camera),
            # trust the pinch detection. Otherwise, if pinch ratios are near
            # the threshold boundary, apply movement suppression.
            if li_raw_now > (enter * 0.7) and li_raw_now < (exit_ * 1.1):
                # In the ambiguous zone — check if wrist is moving fast
                if hasattr(self, '_prev_wrist_pos') and self._prev_wrist_pos is not None:
                    _pw = self._prev_wrist_pos
                    _wrist_move = ((_wrist_x - _pw[0])**2 + (_wrist_y - _pw[1])**2)**0.5
                    if _wrist_move > self._hand_scale * 0.08:
                        _movement_suppress = True
            self._prev_wrist_pos = (_wrist_x, _wrist_y)
        else:
            self._prev_wrist_pos = (float(xy[0][0]), float(xy[0][1]))

Wait — this needs the enter/exit_ variables which are defined later. Instead, 
place this block AFTER the line:
        exit_ = float(self._pinch_exit)

And BEFORE the left pinch detection block.

Then, in the left pinch ENTRY condition, change:
        elif li <= enter:
            self._left_pinch_active = True
            self._left_click_emitted_this_hold = False
To:
        elif li <= enter and not _movement_suppress:
            self._left_pinch_active = True
            self._left_click_emitted_this_hold = False

And in the right pinch ENTRY condition (the elif block that starts right-click detection),
add _movement_suppress to the guard. Change:
        elif (
            not self._left_pinch_active
            and not scroll_pose
            and ri <= right_enter
            and li > (enter * 1.2)
            and pm > 0.22
        ):
To:
        elif (
            not self._left_pinch_active
            and not scroll_pose
            and not _movement_suppress
            and ri <= right_enter
            and li > (enter * 1.2)
            and pm > 0.22
        ):

Also add to __init__, after the line self._z_tap_enabled = False:
        self._prev_wrist_pos: tuple[float, float] | None = None

And add to _reset_all:
        self._prev_wrist_pos = None

DO NOT change any threshold values, cooldown values, the _resolve_scroll method,
the _record_action method, or any return signatures.
Output the COMPLETE file.


=== FILE 4: src/main_window.py ===
Output the COMPLETE file with these changes ONLY:

CHANGE A — Fix _dual_cursor_point to use palm center as primary cursor point:
The current implementation uses index fingertip (landmark 8) when extended,
which means cursor position changes when fingers curl/extend. Palm center
(landmark 9 = middle finger MCP) is much more stable because it barely moves
when fingers open/close.

Find the _dual_cursor_point method. Replace the ENTIRE method body with:

    def _dual_cursor_point(self, hand_data: dict | None) -> tuple[int, int] | None:
        """Return cursor tracking point for the cursor hand in dual mode.
        
        Uses weighted blend of palm center (landmark 9) and index tip (landmark 8):
        - When index finger is extended: 70% index tip + 30% palm center
          (responsive to pointing direction)
        - When fingers are curled/closed: 100% palm center
          (stable, no jump when fingers touch)
        
        This eliminates cursor jumping when fingers contact each other during
        movement, while still allowing precise pointing when index is extended.
        """
        if hand_data is None:
            return None
        xy = hand_data.get("xy", [])
        if not xy or len(xy) < 13:
            return None

        wrist = xy[0]
        mcp9 = xy[9]  # Palm center — most stable point
        
        # Always have palm center as baseline
        palm_x, palm_y = float(mcp9[0]), float(mcp9[1])
        
        # Check if index finger is extended
        if len(xy) > 8:
            tip8 = xy[8]
            pip6 = xy[6]
            hand_scale = max(
                12.0,
                ((float(wrist[0]) - palm_x) ** 2 + (float(wrist[1]) - palm_y) ** 2) ** 0.5,
            )
            extend_margin = max(5.0, hand_scale * 0.06)
            tip_dist = ((float(tip8[0]) - float(wrist[0])) ** 2 + (float(tip8[1]) - float(wrist[1])) ** 2) ** 0.5
            pip_dist = ((float(pip6[0]) - float(wrist[0])) ** 2 + (float(pip6[1]) - float(wrist[1])) ** 2) ** 0.5
            
            if tip_dist > (pip_dist + extend_margin):
                # Index extended — blend toward fingertip for precision
                return int(0.7 * float(tip8[0]) + 0.3 * palm_x), int(0.7 * float(tip8[1]) + 0.3 * palm_y)
        
        # Fallback: pure palm center (most stable when fingers are closed/touching)
        return int(palm_x), int(palm_y)

CHANGE B — Also add pinch pre-freeze in dual-hand mode:
Currently dual mode only freezes on gesture in self._freeze_on. But like 
single mode, it should also freeze when pinch is PHYSICALLY active to prevent
the cursor point from shifting as fingers approach thumb.

In _process_loop, find the dual-hand cursor section:
                if self._cursor_mode == "dual_hand":
                    # Dual-hand: cursor hand is configurable (default right).
                    cursor_hand_label = "Right" if self._dual_right_cursor else "Left"
                    cursor_hand = hands_dict.get(cursor_hand_label)
                    if gesture in self._freeze_on:
                        # Freeze cursor during clicks
                        _has_cursor = self._frozen_sx >= 0

Change the freeze condition to also check pinch state (matching single-hand logic):
                if self._cursor_mode == "dual_hand":
                    # Dual-hand: cursor hand is configurable (default right).
                    cursor_hand_label = "Right" if self._dual_right_cursor else "Left"
                    cursor_hand = hands_dict.get(cursor_hand_label)
                    _pinch_active_dual = self.gestures._left_pinch_active or self.gestures._right_pinch_active
                    if gesture in self._freeze_on or _pinch_active_dual:
                        # Freeze cursor during clicks and active pinches
                        _has_cursor = self._frozen_sx >= 0

DO NOT change any UI code, stylesheet, settings dialog, overlay, or any 
other method. Keep all existing logic exactly as-is except these two changes.
Output the COMPLETE file.


=== ALSO UPDATE: .cursorrules ===
Add these lines under ## FROZEN VALUES:

# src/hand_tracker.py (fingertip smoothing):
_tip_indices = {4, 8, 12, 16, 20}
tip_blend = base_blend * 0.55

# src/cursor_mapper.py:
self._outer_slack_ratio = 0.10
max_jump = scr_diag * 0.25
(NO edge alpha reduction — those 3 lines were deleted)

# src/gesture_detector.py:
_movement_suppress logic (prevents clicks during fast hand movement)
self._prev_wrist_pos tracking

# src/main_window.py:
_dual_cursor_point uses 70/30 blend of index tip + palm center
Dual-hand cursor freezes on _pinch_active_dual (matches single-hand behavior)

Add under ## FEATURES THAT MUST NOT BE REMOVED:
- Fingertip-specific smoothing in hand_tracker (tip_blend = base_blend * 0.55)
- Movement suppression in gesture_detector (_movement_suppress)
- Palm+fingertip blend in _dual_cursor_point (0.7 tip + 0.3 palm)
- Dual-hand pinch pre-freeze (_pinch_active_dual)

=== ALSO UPDATE: PROMPTING_GUIDE.md ===
Add to the "Rules for writing prompts" section:
8. Never change the fingertip smoothing multiplier (tip_blend = base_blend * 0.55)
9. Never change the outer_slack_ratio (0.10) or max_jump (scr_diag * 0.25)  
10. Never remove the _movement_suppress logic from gesture_detector
11. Never change _dual_cursor_point blend ratio (0.7 tip + 0.3 palm)
```

════════════════════════════════════════════════════════════════
WHAT EACH FIX DOES — summary for testing
════════════════════════════════════════════════════════════════

SKELETON SHAKE FIX (hand_tracker.py):
  Fingertips get 55% of the base blend → much heavier smoothing on tips 
  while palm/wrist stay responsive. Index finger shake becomes invisible.

CURSOR ZIGZAG FIX (hand_tracker.py + cursor_mapper.py):
  Smoother index landmark + larger max_jump allowance + no edge slowdown
  = cursor follows hand without U/V patterns or pausing.

CURSOR PAUSES DURING FINGER CONTACT (cursor_mapper.py + gesture_detector.py):
  max_jump increased from 0.14 to 0.25 → stops clamping normal movements.
  Movement suppression → prevents accidental click ENTRY during fast movement.
  Palm-center blend → cursor point barely moves when fingers touch.

MOVEMENT PRIORITY (gesture_detector.py):
  When wrist is moving fast AND pinch ratio is in the ambiguous zone,
  click entry is suppressed. Clicking only activates when hand is 
  relatively stationary or pinch is clearly deliberate.

MARGIN → SCREEN EDGE (cursor_mapper.py):
  outer_slack_ratio 0.10 means 10% of camera beyond the control box
  still maps to screen edges. Edge alpha reduction removed.

DUAL-HAND CURSOR POINT (main_window.py):
  70% index tip + 30% palm center when pointing. 100% palm center when
  fingers are closed. No more cursor jumps when switching finger poses.
  Pinch pre-freeze added to dual mode (was only in single mode).

════════════════════════════════════════════════════════════════
TEST AFTER APPLYING:
════════════════════════════════════════════════════════════════
□ Hold hand still, palm open → cursor doesn't shake/zigzag
□ Hold hand still, palm closed (fist) → cursor doesn't shake
□ Move hand slowly left-right → smooth line, no U/V pattern
□ Move hand fast → cursor follows without pausing
□ Touch thumb to index while moving → cursor does NOT pause or click
□ Deliberately pinch (stationary hand) → left click fires
□ Move to screen corners → cursor reaches all 4 corners
□ Move past control box edge → cursor reaches screen edge
□ Dual mode: right hand skeleton stable, left hand gestures work
□ Single mode: same hand does both, no random clicks during movement
□ Scroll with peace sign → no cursor movement, no clicks triggered

git add . && git commit -m "fixed: tracking smoothness final"
