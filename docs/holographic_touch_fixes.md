# Holographic Touch — Full Codebase Analysis & VS Code Agent Prompts

---

## PART 1 — 🔍 ANALYSIS: Root Causes of Every Major Issue

---

### CRITICAL BUG 1: Clicks Not Firing / Only Media Gestures Working

**Root cause traced in `gesture_detector.py` → `_check_action_cooldown()`:**

The edge-detection logic at line ~1668 blocks re-entry:
```python
if gesture == self._prev_gesture_state and gesture not in {
    GestureType.SCROLL, GestureType.DRAG, GestureType.MOVE, ...
}:
    return False
```
The problem: `_prev_gesture_state` is set to `LEFT_CLICK` when a click fires, but the pinch gesture persists across multiple frames. On the next frame, `gesture == self._prev_gesture_state` is True → blocked. The click fires once, then gets permanently locked out until the user fully releases and re-pinches. But the 4-frame debounce + stable_state confirm-hold means by the time the gesture is confirmed, `_prev_gesture_state` is already set.

**Double click is nearly impossible** because `_left_click_release_time` is set when `_state` leaves `LEFT_CLICK`, but the confirm-hold + debounce delays mean the time between release and re-pinch often exceeds `_double_click_window_s` (0.32s).

**Media gestures work** because vol_up/vol_down bypass both debounce and edge detection (they are in the continuous-gesture whitelist), and MEDIA_NEXT/PREV use their own `_media_edge_state` system that works independently.

### CRITICAL BUG 2: Right-Click Triggers Randomly

**Root cause in `_update_pinch_states()`:**

The anti-cross gating is too weak:
```python
right_click_pose = right_dist <= pinch_enter and left_dist > (pinch_enter * 0.85)
```
When the user pinches thumb+index (left click), finger jitter often brings thumb close enough to middle finger to also trigger `right_click_pose`. The 0.85 multiplier is not enough separation. Additionally, there's no requirement that middle finger be curled/extended — only distance-based.

### CRITICAL BUG 3: Cursor Pausing / Not Smooth

**Root cause (multi-layered):**

1. **`_process_loop` sleeps 50ms when no hand detected for 5 seconds** (line ~3510-3511): `time.sleep(0.05)` — when hand briefly drops, cursor freezes for 50ms chunks.

2. **Grace period creates stale data**: HandTracker returns the SAME `hand_data` for 8 frames after hand loss. The cursor mapper keeps receiving the same coordinates → cursor freezes at last known position.

3. **Mouse worker deadzone** (`mouse.py` line ~3917): `dx*dx + dy*dy >= deadzone_px * deadzone_px` with `deadzone_px=2` — small movements are suppressed entirely.

4. **Cursor mapper smoothing is too aggressive**: `_alpha_min = 0.07` means in slow movements, only 7% of the actual position change is applied per frame. At 30fps that's ~2 seconds to reach the target.

5. **`_drain_and_read` drops frames**: camera_thread grabs 2 extra frames before read. On a 30fps camera, this adds ~66ms latency.

### BUG 4: Console Spam

**Root cause:** Multiple print statements with insufficient cooldown:
- `hand_tracker.py:149` — `[HAND]` prints every 0.6s
- `gesture_detector.py:1599` — `[PINCH]` prints every 1.2s
- `gesture_detector.py:1811` — `[GESTURE]` prints every 1.2s
- `main_window.py:3551` — `HAND: ... GESTURE: ...` prints every 0.75s
- Combined: ~4-6 print lines per second continuously

### BUG 5: UI Layout / Scaling Issues

**Root causes:**
- `QSizePolicy.Policy.Ignored` on preview label — it can shrink to 0
- Side panel has `setMinimumWidth(380)` — on smaller screens this compresses the camera view
- `setWordWrap(True)` on gesture badge causes multi-line text instead of truncation
- History labels have no minimum width → text clips
- No responsive breakpoint logic — fixed 380px sidebar on all screen sizes
- Gesture guide grid `setColumnStretch(2, 1)` but columns 0 and 1 have no stretch → cramped icons
- `QScrollArea` around audit log has transparent background but the scrollbar is unstyled

### BUG 6: Scroll Not Smooth

**Root cause in `_resolve_scroll()`:**
- EMA alpha is 0.35 (too aggressive → jittery)
- `_scroll_step_factor = 0.12` produces integer steps that are either 0 or large jumps
- Direction-switch cooldown (0.12s) causes scroll to freeze when hand oscillates even slightly
- `scroll_step_limit = 4` caps maximum but doesn't help the quantization jitter at low speeds

### BUG 7: Handedness Logic Confusion

**Root cause in `hand_tracker.py:138`:**
```python
if is_mirrored:
    label = raw_label
else:
    label = "Right" if raw_label == "Left" else "Left"
```
MediaPipe assumes a selfie (mirrored) view. When `mirror_camera=True`, the frame is flipped with `cv2.flip(frame, 1)` BEFORE detection, and `is_mirrored=True` is passed. This is correct. BUT the label smoothing (majority-vote over 5 frames) can cause the label to flip-flop during the transition, especially when confidence is borderline.

### BUG 8: Performance Issues

- MediaPipe runs at `model_complexity=0` — good
- BUT `_drain_and_read` grabs 2 extra frames → wasted CPU
- `cv2.cvtColor` is called twice: once in hand_tracker for detection, once in _render for display
- The render timer runs at 16ms (60fps) but process loop has no frame rate control
- Camera thread and process thread both do `time.sleep()` which wastes time in OS scheduler

---

## PART 2 — 🛠 FIXES (Organized by VS Code Prompt)

See PART 3 below — each prompt contains the exact code changes.

---

## PART 3 — ⚡ VS CODE AGENT PROMPTS

---

### PROMPT 1: Fix Click Detection (Left Click, Double Click, Drag)

```
TASK: Fix left click, double click, and drag gestures in the Holographic Touch app.

FILE: src/gesture_detector.py

PROBLEM: Left click fires once then gets blocked because _check_action_cooldown() 
uses edge detection that prevents re-entry while _prev_gesture_state == LEFT_CLICK.
Double click is nearly impossible because the debounce + confirm hold delays exceed 
the double_click_window_s.

CHANGES:

1. In _check_action_cooldown(), change the edge detection to track transitions 
   using a separate _last_fired_gesture field instead of _prev_gesture_state:

Replace the entire _check_action_cooldown method:

    def _check_action_cooldown(self, gesture: GestureType, now: float) -> bool:
        cooldown = self._per_action_cooldown.get(gesture, self._action_cooldown_s)
        last = self._last_action_time.get(gesture, 0.0)
        if now - last < cooldown:
            return False
        # Edge detection: only fire if this is a NEW entry into this state
        if gesture == self._prev_gesture_state and gesture not in {
            GestureType.SCROLL, GestureType.DRAG, GestureType.MOVE,
            GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN,
        }:
            return False
        return True

WITH:

    def _check_action_cooldown(self, gesture: GestureType, now: float) -> bool:
        cooldown = self._per_action_cooldown.get(gesture, self._action_cooldown_s)
        last = self._last_action_time.get(gesture, 0.0)
        if now - last < cooldown:
            return False
        return True

2. Instead, enforce edge detection at the call site. In the detect() method's 
   RIGHT HAND section, change the LEFT_CLICK handling:

Replace:
        if stable_state == GestureType.LEFT_CLICK:
            if self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                if 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s:

WITH:
        if stable_state == GestureType.LEFT_CLICK:
            is_new_entry = (self._prev_gesture_state != GestureType.LEFT_CLICK 
                           and self._prev_gesture_state != GestureType.DRAG)
            if is_new_entry and self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                if 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s:

3. Same for RIGHT_CLICK:

Replace:
        if stable_state == GestureType.RIGHT_CLICK:
            if self._check_action_cooldown(GestureType.RIGHT_CLICK, now):

WITH:
        if stable_state == GestureType.RIGHT_CLICK:
            is_new_entry = self._prev_gesture_state != GestureType.RIGHT_CLICK
            if is_new_entry and self._check_action_cooldown(GestureType.RIGHT_CLICK, now):

4. Increase double_click_window_s to give more time:

In __init__, change:
        self._double_click_window_s = GESTURE_DOUBLE_CLICK_WINDOW_S

TO:
        self._double_click_window_s = 0.50

5. Reduce debounce frames for click gestures. Change _debounce_check:

Replace the entire method:

    def _debounce_check(self, raw_state: GestureType) -> GestureType:
        if raw_state == self._debounce_gesture:
            self._debounce_count += 1
        else:
            self._debounce_gesture = raw_state
            self._debounce_count = 1

        if raw_state == self._state and raw_state in {
            GestureType.MOVE, GestureType.SCROLL, GestureType.DRAG,
            GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN,
        }:
            return raw_state

        if self._debounce_count >= self._debounce_required:
            return raw_state

        return self._state

WITH:

    def _debounce_check(self, raw_state: GestureType) -> GestureType:
        if raw_state == self._debounce_gesture:
            self._debounce_count += 1
        else:
            self._debounce_gesture = raw_state
            self._debounce_count = 1

        # Continuous gestures pass through immediately once confirmed
        if raw_state == self._state and raw_state in {
            GestureType.MOVE, GestureType.SCROLL, GestureType.DRAG,
            GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN,
        }:
            return raw_state

        # Click gestures need only 2 frames for responsiveness
        click_gestures = {
            GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
            GestureType.DOUBLE_CLICK,
        }
        required = 2 if raw_state in click_gestures else self._debounce_required

        if self._debounce_count >= required:
            return raw_state

        return self._state

6. Reduce per-action cooldown for clicks:

Change in __init__:
        self._per_action_cooldown = {
            GestureType.LEFT_CLICK: 0.4,
            GestureType.RIGHT_CLICK: 0.4,
            GestureType.DOUBLE_CLICK: 0.4,

TO:
        self._per_action_cooldown = {
            GestureType.LEFT_CLICK: 0.30,
            GestureType.RIGHT_CLICK: 0.50,
            GestureType.DOUBLE_CLICK: 0.50,

VERIFY: After these changes, pinching thumb+index on right hand should produce
exactly ONE left click on pinch-in, and release+re-pinch within 0.5s should 
produce a double click. No click spam should occur.
```

---

### PROMPT 2: Fix Random Right-Click Triggers

```
TASK: Fix random right-click triggers in the Holographic Touch app.

FILE: src/gesture_detector.py

PROBLEM: Right-click (thumb+middle pinch) triggers when doing left-click 
(thumb+index pinch) because finger jitter brings thumb close to middle finger.
The anti-cross gating (0.85 multiplier) is too weak.

CHANGES:

1. In _update_pinch_states(), strengthen the anti-cross gating and add 
   finger-extension requirements:

Replace this section:
        # More tolerant anti-cross gating for real webcam jitter.
        left_click_pose = left_dist <= pinch_enter and right_dist > (pinch_enter * 0.85)
        right_click_pose = right_dist <= pinch_enter and left_dist > (pinch_enter * 0.85)

WITH:
        # Strict anti-cross gating: the OTHER finger pair must be clearly separated
        left_click_pose = left_dist <= pinch_enter and right_dist > (pinch_exit * 0.9)
        right_click_pose = right_dist <= pinch_enter and left_dist > (pinch_exit * 0.9)

2. Also add a method parameter and use finger states to validate right-click:

Change the _update_pinch_states signature from:
    def _update_pinch_states(self, xy, fs: FingerStates, hand_scale: float) -> None:

No change needed to signature — but ADD this additional check after the 
right_click_pose line:

After the line:
        right_click_pose = right_dist <= pinch_enter and left_dist > (pinch_exit * 0.9)

ADD:
        # Right-click requires middle finger to actually be extending toward thumb,
        # not just accidentally close. Index must be clearly extended (not also pinching).
        if right_click_pose and not fs.index:
            right_click_pose = False

3. Add hysteresis delay for right-click activation. In __init__, add:

After the line:
        self._right_pinch_active = False

ADD:
        self._right_pinch_pending_since: float | None = None
        self._right_pinch_confirm_s = 0.12  # 120ms hold before right-click activates

4. Change the right-pinch activation logic in _update_pinch_states:

Replace:
        if self._right_pinch_active:
            if right_dist > pinch_exit:
                self._right_pinch_active = False
        elif right_click_pose:
            self._right_pinch_active = True

WITH:
        now = time.monotonic()
        if self._right_pinch_active:
            if right_dist > pinch_exit:
                self._right_pinch_active = False
                self._right_pinch_pending_since = None
        elif right_click_pose:
            if self._right_pinch_pending_since is None:
                self._right_pinch_pending_since = now
            elif now - self._right_pinch_pending_since >= self._right_pinch_confirm_s:
                self._right_pinch_active = True
        else:
            self._right_pinch_pending_since = None

VERIFY: Right-click should only trigger when deliberately pinching thumb+middle 
while index finger is extended. Quick jitter during left-click should NOT trigger 
right-click.
```

---

### PROMPT 3: Fix Cursor Smoothness and Lag

```
TASK: Fix cursor movement — eliminate pausing, jitter, and lag.

FILES: src/cursor_mapper.py, src/camera_thread.py, src/mouse.py, 
       src/main_window.py, src/gesture_detector.py

PROBLEM: Cursor pauses randomly, feels laggy, and jitters. Multiple causes:
(A) Process loop sleeps 50ms when no hand for 5s
(B) Grace period feeds stale coordinates  
(C) Smoothing alpha_min=0.07 is too slow
(D) _drain_and_read drops frames adding latency
(E) Mouse worker deadzone blocks small movements

CHANGES:

=== FILE: src/main_window.py ===

1. In _process_loop(), change the idle sleep from 50ms to 5ms:

Replace:
            if time.monotonic() - last_hand_time > 5.0:
                time.sleep(0.05)

WITH:
            if time.monotonic() - last_hand_time > 5.0:
                time.sleep(0.005)

=== FILE: src/camera_thread.py ===

2. In _drain_and_read(), stop dropping frames — just read the latest:

Replace the entire _drain_and_read method:

    @staticmethod
    def _drain_and_read(cap: cv2.VideoCapture):
        # Best-effort stale-frame drop so processing sees the newest image.
        for _ in range(2):
            try:
                if not cap.grab():
                    break
            except Exception:
                break

        try:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                return ok, frame
        except Exception:
            pass

        return cap.read()

WITH:

    @staticmethod
    def _drain_and_read(cap: cv2.VideoCapture):
        # Single grab+retrieve for lowest latency
        try:
            if cap.grab():
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    return ok, frame
        except Exception:
            pass
        return cap.read()

=== FILE: src/cursor_mapper.py ===

3. Increase minimum smoothing alpha for faster response:

Replace:
        self._alpha_min = 0.07
        self._alpha_max = 0.60

WITH:
        self._alpha_min = 0.15
        self._alpha_max = 0.70

4. Make the deadzone filter more responsive too:

Replace:
        if speed <= dynamic_deadzone:
            self._flt_x = self._flt_x + 0.08 * (raw_x - self._flt_x)
            self._flt_y = self._flt_y + 0.08 * (raw_y - self._flt_y)
            return int(self._flt_x), int(self._flt_y)

WITH:
        if speed <= dynamic_deadzone:
            self._flt_x = self._flt_x + 0.15 * (raw_x - self._flt_x)
            self._flt_y = self._flt_y + 0.15 * (raw_y - self._flt_y)
            return int(self._flt_x), int(self._flt_y)

5. Also update set_smoothening to use wider alpha range:

Replace:
        self._alpha_min = 0.06 + t * 0.14
        self._alpha_max = 0.40 + t * 0.30

WITH:
        self._alpha_min = 0.12 + t * 0.13
        self._alpha_max = 0.50 + t * 0.25

=== FILE: src/mouse.py ===

6. Reduce mouse worker deadzone:

Replace:
        self._deadzone_px = 2

WITH:
        self._deadzone_px = 1

=== FILE: src/gesture_detector.py ===

7. Reduce grace period from 8 to 4 frames to stop stale coordinate feeding:

Replace (in __init__):
        self._grace_frames = 8

WITH:
        self._grace_frames = 4

=== FILE: src/hand_tracker.py ===

8. Same grace period reduction:

Replace:
        self._grace_frames = 8

WITH:
        self._grace_frames = 4

VERIFY: Move your index finger smoothly across the camera view. The cursor 
should follow in real-time with no visible pausing or stutter. Small movements 
should still register.
```

---

### PROMPT 4: Eliminate Console Spam

```
TASK: Remove excessive console logging that causes performance overhead.

FILES: src/gesture_detector.py, src/hand_tracker.py, src/main_window.py

PROBLEM: Multiple print statements fire every 0.6-1.2 seconds, producing 
4-6 lines/second continuously. This tanks performance and makes debugging 
impossible.

CHANGES:

=== FILE: src/gesture_detector.py ===

1. Increase pinch log cooldown and make it debug-only:

Replace:
        self._pinch_log_cooldown_s = 1.2

WITH:
        self._pinch_log_cooldown_s = 5.0

2. In _update_pinch_states(), guard the pinch debug print:

Replace:
        now = time.monotonic()
        if now - self._last_pinch_log_ts >= self._pinch_log_cooldown_s:
            print(
                f"[PINCH] left_dist={left_dist:.1f} right_dist={right_dist:.1f} scale={hand_scale:.1f} "
                f"left_ratio={pinch_ratio:.3f} right_ratio={right_pinch_ratio:.3f} "
                f"enter_thresh={self._pinch_enter:.3f} exit_thresh={self._pinch_exit:.3f}"
            )
            self._last_pinch_log_ts = now

WITH:
        # Pinch debug logging removed for production — uncomment for debugging
        # now_log = time.monotonic()
        # if now_log - self._last_pinch_log_ts >= self._pinch_log_cooldown_s:
        #     print(f"[PINCH] left={left_dist:.1f} right={right_dist:.1f} scale={hand_scale:.1f}")
        #     self._last_pinch_log_ts = now_log

3. Increase gesture log cooldown:

Replace:
        self._gesture_log_cooldown_s = 1.2

WITH:
        self._gesture_log_cooldown_s = 5.0

4. In detect(), suppress the state print to only fire on actual state changes:

Replace:
        if self._state != self._last_logged_state or (now - self._last_gesture_log_ts) >= self._gesture_log_cooldown_s:
            print(f"[GESTURE] Hand={hand_label} State={self._state} Scale={self._hand_scale:.3f}")
            self._last_logged_state = self._state
            self._last_gesture_log_ts = now

WITH:
        if self._state != self._last_logged_state:
            self._last_logged_state = self._state
            # print(f"[GESTURE] Hand={hand_label} State={self._state}")

=== FILE: src/hand_tracker.py ===

5. Suppress hand label logging:

Replace:
        now = cv2.getTickCount() / cv2.getTickFrequency()
        if label != self._last_logged_label or (now - self._last_log_ts) >= self._log_cooldown_s:
            print(f"[HAND] Raw={raw_label} Mirrored={is_mirrored} Final={label}")
            self._last_logged_label = label
            self._last_log_ts = now

WITH:
        self._last_logged_label = label
        # Hand label logging disabled for production

=== FILE: src/main_window.py ===

6. Suppress the main debug print in _process_loop:

Replace:
                if (
                    gesture != self._last_debug_label
                    or (now_dbg - self._last_debug_print_ts) >= 0.75
                ):
                    print("HAND:", label, "GESTURE:", result.gesture, "VALUE:", result.value)
                    self._last_debug_label = gesture
                    self._last_debug_print_ts = now_dbg

WITH:
                self._last_debug_label = gesture
                # Debug print disabled for production

VERIFY: Run the app and check the console — it should be nearly silent during 
normal operation. Only errors and startup messages should appear.
```

---

### PROMPT 5: Fix Scroll Smoothness

```
TASK: Make scroll gesture smooth and proportional instead of jerky integer steps.

FILE: src/gesture_detector.py

PROBLEM: Scroll uses integer quantization with high EMA alpha (0.35) causing 
alternating 0/1/-1 steps that feel jerky. Direction-switch cooldown causes 
freezing on slight hand oscillation.

CHANGES:

1. Replace the entire _resolve_scroll method:

Replace:

    def _resolve_scroll(self, current_y: float, hand_scale: float) -> int:
        if self._scroll_prev_y is None:
            self._scroll_prev_y = current_y
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            return 0

        dy = self._scroll_prev_y - current_y
        self._scroll_prev_y = current_y

        alpha = 0.35
        self._scroll_velocity_ema = (1.0 - alpha) * self._scroll_velocity_ema + alpha * dy
        v = self._scroll_velocity_ema

        deadband = hand_scale * self._scroll_deadband_factor
        if abs(v) <= deadband:
            return 0

        step = max(1.0, hand_scale * self._scroll_step_factor)
        steps = int(v / step)
        if steps == 0:
            return 0
        if steps > self._scroll_step_limit:
            steps = self._scroll_step_limit
        elif steps < -self._scroll_step_limit:
            steps = -self._scroll_step_limit

        direction = 1 if steps > 0 else -1
        if self._scroll_direction == 0:
            self._scroll_direction = direction
        elif direction != self._scroll_direction:
            if time.monotonic() - self._scroll_last_switch_time < self._scroll_dir_switch_cooldown_s:
                return 0
            self._scroll_direction = direction
            self._scroll_last_switch_time = time.monotonic()
            self._scroll_velocity_ema = 0.0
            return 0

        return int(steps * max(1, self._scroll_gain))

WITH:

    def _resolve_scroll(self, current_y: float, hand_scale: float) -> int:
        if self._scroll_prev_y is None:
            self._scroll_prev_y = current_y
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            self._scroll_accumulator = 0.0
            return 0

        dy = self._scroll_prev_y - current_y
        self._scroll_prev_y = current_y

        # Gentler EMA for smoother velocity tracking
        alpha = 0.25
        self._scroll_velocity_ema = (1.0 - alpha) * self._scroll_velocity_ema + alpha * dy
        v = self._scroll_velocity_ema

        deadband = hand_scale * self._scroll_deadband_factor
        if abs(v) <= deadband:
            # Bleed accumulator toward zero when in deadband
            self._scroll_accumulator *= 0.5
            return 0

        # Accumulate sub-pixel scroll and emit integer steps
        step = max(1.0, hand_scale * self._scroll_step_factor)
        self._scroll_accumulator += v / step

        steps = int(self._scroll_accumulator)
        if steps == 0:
            return 0

        self._scroll_accumulator -= steps

        if steps > self._scroll_step_limit:
            steps = self._scroll_step_limit
        elif steps < -self._scroll_step_limit:
            steps = -self._scroll_step_limit

        direction = 1 if steps > 0 else -1
        if self._scroll_direction == 0:
            self._scroll_direction = direction
        elif direction != self._scroll_direction:
            now = time.monotonic()
            if now - self._scroll_last_switch_time < self._scroll_dir_switch_cooldown_s:
                self._scroll_accumulator = 0.0
                return 0
            self._scroll_direction = direction
            self._scroll_last_switch_time = now
            self._scroll_velocity_ema = 0.0
            self._scroll_accumulator = 0.0
            return 0

        return int(steps * max(1, self._scroll_gain))

2. Add the accumulator initialization in __init__:

After the line:
        self._scroll_direction = 0

ADD:
        self._scroll_accumulator = 0.0

3. Also reset accumulator wherever scroll state is reset. In the detect() method,
find all places where _scroll_prev_y is set to None and also reset accumulator.

After every occurrence of:
            self._scroll_prev_y = None

ADD on the next line:
            self._scroll_accumulator = 0.0

And in the PAUSE/no-hand reset block, after:
                self._scroll_direction = 0
ADD:
                self._scroll_accumulator = 0.0

VERIFY: Hold peace sign (index + middle extended) and move hand up/down slowly.
Scrolling should be smooth and proportional to movement speed with no jerking.
```

---

### PROMPT 6: Fix UI Layout, Scaling, and Polish

```
TASK: Fix all UI layout issues — text clipping, poor scaling, broken alignment.

FILE: src/main_window.py

CHANGES:

1. Fix preview label sizing — change from Ignored to Expanding:

Replace:
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

WITH:
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setMinimumSize(320, 240)

2. Reduce side panel minimum width for better scaling:

Replace:
        side_wrap.setMinimumWidth(380)

WITH:
        side_wrap.setMinimumWidth(300)
        side_wrap.setMaximumWidth(420)

3. Fix gesture guide minimum width:

Replace:
        self.gesture_guide.setMinimumWidth(260)

WITH:
        self.gesture_guide.setMinimumWidth(240)

4. Disable word wrap on badge (it should truncate, not wrap):

Replace:
        self.gesture_lbl.setWordWrap(True)

WITH:
        self.gesture_lbl.setWordWrap(False)
        self.gesture_lbl.setMinimumWidth(120)

5. Fix the gesture guide grid to give proper column proportions:

After the line:
        gl.setColumnStretch(2, 1)

ADD:
        gl.setColumnStretch(0, 0)
        gl.setColumnStretch(1, 2)

6. Give history labels a minimum width and fixed height:

Replace:
            lbl.setObjectName("historyItem")
            lbl.setWordWrap(True)

WITH:
            lbl.setObjectName("historyItem")
            lbl.setWordWrap(False)
            lbl.setMinimumHeight(24)

7. Fix the body layout stretch so camera gets more space:

Replace:
        body_l.addWidget(cam_card, 1)
        body_l.addWidget(side_wrap)

WITH:
        body_l.addWidget(cam_card, 3)
        body_l.addWidget(side_wrap, 1)

8. Add minimum window size that works better:

Replace:
        self.setMinimumSize(1024, 680)

WITH:
        self.setMinimumSize(960, 640)

9. Fix the side layout to not have the extra stretch at bottom:

Replace:
        side.addWidget(status)
        side.addLayout(side_content, 1)
        side.addStretch(1)

WITH:
        side.addWidget(status)
        side.addLayout(side_content, 1)

10. Style the scrollbar in the audit log scroll area:

Replace:
        audit_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

WITH:
        audit_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #27272A; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #3F3F46; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

VERIFY: Resize the window to various sizes (small, medium, large). The camera 
preview should always be visible and properly sized. Side panel text should not 
clip. Gesture guide icons should be aligned with their labels.
```

---

### PROMPT 7: Polish UI Styles for Production Look

```
TASK: Polish the visual styling to look like a premium production app.

FILE: src/main_window.py

CHANGES: Update the main window stylesheet in _build_ui(). Find the 
self.setStyleSheet(...) call and replace the ENTIRE stylesheet string with:

        self.setStyleSheet(
            """
            * {
                font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
            }
            QMainWindow { background: #09090B; color: #F1F5F9; }
            
            #headerCard {
                background: rgba(15, 18, 25, 0.6);
                border: 1px solid rgba(39, 39, 42, 0.5);
                border-radius: 14px;
            }
            #floatingDock {
                background: rgba(15, 18, 25, 0.9);
                border: 1px solid rgba(34, 211, 238, 0.12);
                border-radius: 26px;
            }
            #sideCard {
                background: rgba(15, 18, 25, 0.4);
                border: 1px solid rgba(39, 39, 42, 0.3);
                border-radius: 12px;
                padding: 12px;
            }
            #sideCardWrap {
                background: transparent;
                border: none;
            }
            #cameraCard {
                background: transparent;
                border: none;
            }
            
            #title { 
                font-size: 18px; font-weight: 800; color: #F1F5F9; 
                letter-spacing: 1.5px; 
            }
            #cardTitle { 
                font-size: 12px; font-weight: 700; color: #64748B; 
                text-transform: uppercase; letter-spacing: 2px; 
                padding-bottom: 4px; 
            }
            
            #statusOffline { color: #F87171; font-size: 16px; }
            #statusOnline { color: #22D3EE; font-size: 16px; }
            
            #preview {
                background: #0F1117; 
                border-radius: 14px; 
                border: 1px solid #1E1E24;
                color: #27272A; 
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 3px;
            }
            #preview[active="true"] {
                border: 1px solid rgba(34, 211, 238, 0.25);
            }
            
            #gestureBold { 
                font-weight: 600; color: #E2E8F0; font-size: 13px;
            }
            #mutedAction { 
                color: #64748B; font-size: 12px; text-align: left; 
            }
            
            #primaryText { color: #E2E8F0; font-size: 13px; font-weight: 600;}
            #secondary { color: #94A3B8; font-size: 13px; font-weight: 500;}
            #muted { color: #475569; font-size: 13px; font-weight: 500;}
            
            #badge {
                border-radius: 10px; padding: 6px 16px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0; 
                max-width: 200px; font-size: 13px; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
            }
            #historyItem { 
                font-weight: 500; 
                font-family: "Cascadia Code", "Consolas", "SF Mono", monospace;
                font-size: 12px;
                color: #64748B;
            }
            
            QPushButton {
                border: none; 
                border-radius: 14px; 
                padding: 10px 22px;
                font-size: 13px;
                font-weight: 700; 
                background: #18181B;
                color: #E2E8F0;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { 
                background: #27272A; 
            }
            QPushButton:disabled { background: #0F0F12; color: #27272A; }
            
            #startBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #059669, stop:1 #34D399); 
                color: #022C22; 
            }
            #startBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #34D399, stop:1 #6EE7B7);
            }
            
            #stopBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #DC2626, stop:1 #F87171); 
                color: #1A0505; 
            }
            #stopBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #F87171, stop:1 #FCA5A5);
            }
            
            #mouseBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0891B2, stop:1 #22D3EE); 
                color: #021820; 
            }
            #mouseBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #22D3EE, stop:1 #67E8F9);
            }
            
            #settingsBtn { 
                background: transparent; padding: 0;
                border-radius: 22px;
            }
            #settingsBtn:hover { 
                background: rgba(34, 211, 238, 0.08); 
                border: 1px solid rgba(34, 211, 238, 0.2); 
            }
            
            QSlider::groove:horizontal {
                height: 4px; background: #1E1E24; border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0E7490, stop:1 #22D3EE);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #F1F5F9; border: 2px solid #22D3EE;
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #FFFFFF;
                border: 2px solid #67E8F9;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
            }
            """
        )

VERIFY: The app should have a cohesive dark theme with subtle cyan accents.
Buttons should have gradient fills. Cards should have subtle borders. 
Everything should feel "premium dark mode" like Linear or Vercel.
```

---

### PROMPT 8: Fix Settings Dialog Polish + Overlay Polish

```
TASK: Polish the Settings dialog and Status Overlay styling.

FILE: src/main_window.py

CHANGES:

=== Settings Dialog ===

1. In the SettingsDialog.__init__, update the stylesheet. Find the 
   self.setStyleSheet(...) call inside SettingsDialog and replace the 
   QSlider section to match the main window:

Find in the SettingsDialog stylesheet:
            QSlider::groove:horizontal { height: 6px; background: #27272A; border-radius: 3px; }

Replace the entire QSlider section (groove, sub-page, handle, handle:hover) with:
            QSlider::groove:horizontal { height: 4px; background: #1E1E24; border-radius: 2px; }
            QSlider::sub-page:horizontal { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0E7490, stop:1 #22D3EE); 
                border-radius: 2px; 
            }
            QSlider::handle:horizontal {
                background: #F1F5F9; border: 2px solid #22D3EE;
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #FFFFFF; border: 2px solid #67E8F9;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
            }

2. Fix QPushButton contrast in settings:

In the SettingsDialog stylesheet, replace:
            QPushButton {
                border: none; border-radius: 12px; padding: 10px 20px;
                color: #F1F5F9; font-weight: 800; font-size: 14px; background: #27272A;
            }
            QPushButton:hover { background: #18181B; border: 1px solid #00F0FF; }

WITH:
            QPushButton {
                border: none; border-radius: 12px; padding: 10px 20px;
                color: #021820; font-weight: 700; font-size: 13px; 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891B2, stop:1 #22D3EE);
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22D3EE, stop:1 #67E8F9);
            }

=== Status Overlay ===

3. In StatusOverlay.__init__, update the stylesheet to match. Find the 
   self.setStyleSheet(...) in StatusOverlay and change:

Replace:
            #overlayRoot { background: rgba(14, 17, 23, 0.92); border: 1px solid rgba(34, 211, 238, 0.15); border-radius: 16px; }

WITH:
            #overlayRoot { background: rgba(9, 9, 11, 0.95); border: 1px solid rgba(34, 211, 238, 0.1); border-radius: 16px; backdrop-filter: blur(20px); }

4. In StatusOverlay, update #badge:

Replace:
            #badge {
                border-radius: 12px; padding: 6px 12px; font-weight: 800;
                background: rgba(30, 37, 53, 0.8); color: #F1F5F9; text-transform: uppercase; letter-spacing: 1px;
            }

WITH:
            #badge {
                border-radius: 10px; padding: 6px 14px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0; 
                text-transform: uppercase; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
                font-size: 12px;
            }

VERIFY: Open settings dialog — sliders should have cyan gradient fill. 
Apply/Close buttons should have proper contrast. Overlay badge should match 
main window style.
```

---

### PROMPT 9: Stabilize Hand Detection and Prevent Ghost Gestures

```
TASK: Prevent gestures from triggering without a valid, confidently-detected hand.

FILES: src/gesture_detector.py, src/hand_tracker.py, src/main_window.py

PROBLEM: Ghost gestures fire when hand is partially visible, at frame edges, 
or during hand entry/exit. Grace period feeds stale data that can trigger 
unwanted actions.

CHANGES:

=== FILE: src/gesture_detector.py ===

1. Increase confidence threshold from 0.4 to 0.55:

Replace (two occurrences in detect() and in the Left hand section):
        if confidence < 0.4:

WITH:
        if confidence < 0.55:

2. When using grace-period stale data, only allow MOVE and PAUSE — no clicks:

In detect(), replace:
            self._frames_no_hand += 1
            if self._frames_no_hand < self._grace_frames and self._last_valid_hand_data is not None:
                # Use last known hand data to keep state stable
                hand_data = self._last_valid_hand_data

WITH:
            self._frames_no_hand += 1
            if self._frames_no_hand < self._grace_frames and self._last_valid_hand_data is not None:
                # Use last known hand data but only for continuous gestures
                hand_data = self._last_valid_hand_data
                # Force non-action state during grace period to prevent ghost clicks
                if self._state in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, 
                                   GestureType.DOUBLE_CLICK, GestureType.KEYBOARD,
                                   GestureType.TASK_VIEW}:
                    self._state = GestureType.MOVE

=== FILE: src/hand_tracker.py ===

3. Increase confidence threshold:

Replace:
        if confidence < 0.4:

WITH:
        if confidence < 0.55:

4. Also in detect(), don't return stale data if confidence was the reason 
for rejection. Replace:
            self._frames_no_hand += 1
            if self._frames_no_hand < self._grace_frames and self._last_valid_result is not None:
                return self._last_valid_result
            return None, None

(the one INSIDE the confidence < 0.4 block) WITH:
            # Low confidence — don't use grace period, return nothing
            return None, None

=== FILE: src/main_window.py ===

5. In _process_loop, add a guard: don't execute click/right-click actions 
unless hand_data confidence is above threshold.

After the line:
                result = self.gestures.detect(hand_data)

ADD:
                # Safety: verify confidence before allowing actions
                if hand_data and hand_data.get("confidence", 0) < 0.55:
                    if result.gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                                         GestureType.DOUBLE_CLICK}:
                        result = GestureResult(GestureType.MOVE, 0)

VERIFY: Wave hand in and out of camera view. No clicks, right-clicks, or 
keyboard launches should trigger during hand entry/exit. Only deliberate, 
stable gestures should fire.
```

---

### PROMPT 10: Performance Optimization — Frame Processing Pipeline

```
TASK: Optimize the frame processing pipeline for real-time performance.

FILES: src/main_window.py, src/camera_thread.py, src/tuning.py

CHANGES:

=== FILE: src/camera_thread.py ===

1. Remove the idle sleep in _loop that wastes time:

Replace:
            time.sleep(CAMERA_LOOP_IDLE_S)

WITH:
            # No sleep — rely on cap.read() blocking for frame pacing

2. In _loop, also reduce the failure sleep:

Replace:
                time.sleep(CAMERA_FAIL_SLEEP_S)

WITH:
                time.sleep(0.001)

=== FILE: src/tuning.py ===

3. Update tuning constants:

Replace:
CAMERA_LOOP_IDLE_S = 0.002
CAMERA_FAIL_SLEEP_S = 0.005

WITH:
CAMERA_LOOP_IDLE_S = 0.0
CAMERA_FAIL_SLEEP_S = 0.001

4. Increase mouse worker frequency:

Replace:
MOUSE_WORKER_HZ = 120.0

WITH:
MOUSE_WORKER_HZ = 240.0

=== FILE: src/main_window.py ===

5. In _process_loop, don't call cv2.setUseOptimized in the thread:

Replace:
        try:
            cv2.setUseOptimized(True)
        except Exception:
            pass

WITH:
        # cv2.setUseOptimized already set globally — no need per-thread

6. Reduce render timer to match a reasonable UI refresh rate (avoid over-rendering):

Replace:
        self.timer.start(16)

WITH:
        self.timer.start(20)  # ~50fps UI refresh is sufficient

7. In _render(), skip the expensive cv2.cvtColor if window is minimized:

The method already has this check at the end:
        if self.isMinimized() or frame is None:
            return

Move this check to BEFORE the cv2.cvtColor call. Find:
        if self.isMinimized() or frame is None:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

And make sure the minimized check is above the cvtColor. (It already is in 
the code, so no change needed here — just verify.)

VERIFY: Run the app — FPS counter should show 25-30+ fps. Cursor movement 
should feel immediate with no perceptible delay between hand movement and 
cursor movement.
```

---

### PROMPT 11: Fix Handedness Label Stability

```
TASK: Stabilize hand label detection to prevent Left/Right flip-flopping.

FILE: src/hand_tracker.py

PROBLEM: Label smoothing uses a 5-frame majority vote but this can still 
flip-flop, especially with borderline confidence. When it flips to "Left", 
the right-hand cursor stops and media controls activate.

CHANGES:

1. Increase label history buffer from 5 to 9 frames:

Replace:
        self._label_history: deque = deque(maxlen=5)

WITH:
        self._label_history: deque = deque(maxlen=9)

2. Require a stronger majority — 7 out of 9 instead of simple majority:

Replace:
        # Smooth label over last 5 frames to suppress single-frame noise.
        self._label_history.append(label)
        label = max(set(self._label_history), key=list(self._label_history).count)

WITH:
        # Smooth label over last 9 frames — require 7/9 majority to switch
        self._label_history.append(label)
        right_count = list(self._label_history).count("Right")
        left_count = list(self._label_history).count("Left")
        total = len(self._label_history)
        # Only switch if strong majority (7+ of 9 frames agree)
        threshold = max(5, int(total * 0.75))
        if right_count >= threshold:
            label = "Right"
        elif left_count >= threshold:
            label = "Left"
        else:
            # No strong majority — keep previous label
            label = self._last_logged_label if self._last_logged_label else "Right"

VERIFY: Use your right hand in view. The hand label should remain stable as 
"Right" and not briefly flip to "Left" causing cursor drops or media triggers.
```

---

### PROMPT 12: Fix Process Loop Edge Cases and Drag Reliability

```
TASK: Fix drag gesture reliability and process loop edge cases.

FILE: src/main_window.py

CHANGES:

1. In _process_loop, the drag action fires every frame while dragging 
(calling start_drag repeatedly). Fix it:

Replace:
                    elif gesture == GestureType.DRAG:
                        self.mouse.move(sx, sy)
                        self.mouse.start_drag()

WITH:
                    elif gesture == GestureType.DRAG:
                        if not self.mouse.is_dragging:
                            self.mouse.move(sx, sy)
                            self.mouse.start_drag()
                        else:
                            self.mouse.move(sx, sy)

2. Add error handling for the gesture detection call:

After:
                result = self.gestures.detect(hand_data)

ADD:
                if result is None:
                    result = GestureResult(GestureType.PAUSE, 0)

3. Ensure drag ends cleanly when mouse is disabled:

After the block:
                elif self.mouse.is_dragging:
                    self.mouse.end_drag()

ADD a new block:
                if not self.mouse_enabled and self.mouse.is_dragging:
                    self.mouse.end_drag()

VERIFY: Perform drag gesture (hold thumb+index pinch for 0.28s). Dragging 
should start smoothly, cursor should move while dragging, and releasing the 
pinch should end the drag cleanly. No stuck drags.
```

---

## Summary of All Prompts

| # | Target | Files Changed |
|---|--------|---------------|
| 1 | Fix click/double-click/drag detection | gesture_detector.py |
| 2 | Fix random right-click triggers | gesture_detector.py |
| 3 | Fix cursor smoothness and lag | cursor_mapper.py, camera_thread.py, mouse.py, main_window.py, gesture_detector.py, hand_tracker.py |
| 4 | Eliminate console spam | gesture_detector.py, hand_tracker.py, main_window.py |
| 5 | Fix scroll smoothness | gesture_detector.py |
| 6 | Fix UI layout and scaling | main_window.py |
| 7 | Polish UI styles for production | main_window.py |
| 8 | Polish settings dialog and overlay | main_window.py |
| 9 | Stabilize hand detection, prevent ghost gestures | gesture_detector.py, hand_tracker.py, main_window.py |
| 10 | Performance optimization | main_window.py, camera_thread.py, tuning.py |
| 11 | Fix handedness label stability | hand_tracker.py |
| 12 | Fix drag reliability and edge cases | main_window.py |

**Recommended application order:** 4 → 3 → 11 → 9 → 1 → 2 → 5 → 10 → 12 → 6 → 7 → 8

Start with console spam removal (4) so you can actually see errors. Then fix cursor (3) and detection stability (11, 9) so you can test gestures. Then fix the gestures themselves (1, 2, 5). Then performance (10) and drag (12). Finally UI polish (6, 7, 8).
