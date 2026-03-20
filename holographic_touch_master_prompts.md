# Holographic Touch — 3 Master Prompts for Complete Revamp

## What These Prompts Do (apply in order 1 → 2 → 3)

| Prompt | Scope | Files Created/Modified |
|--------|-------|----------------------|
| **1** | Dual-hand engine + eye tracker + gesture rewrite | `src/eye_tracker.py` (NEW), `src/hand_tracker.py`, `src/gesture_detector.py`, `src/tuning.py`, `src/models.py`, `src/settings_store.py` |
| **2** | Main window rewire — process loop, cursor dispatch, settings, UI | `src/main_window.py` |
| **3** | Final polish — UI styles, verification tests, cleanup | `src/main_window.py` (styles), `src/constants.py`, `src/face_tracker.py` (keep as legacy), `requirements.txt` |

---

## PROMPT 1 — Dual-Hand Engine + Eye Tracker + Gesture Rewrite

```
You are refactoring the Holographic Touch gesture mouse app. This is a PySide6 + OpenCV + MediaPipe project.

GOAL: Implement dual-hand tracking (left hand = cursor, right hand = clicks/scroll) as the DEFAULT mode, plus an experimental iris-based eye tracker as an optional mode in settings.

=== IMPORTANT RULES ===
- Do NOT break any existing imports or class interfaces
- Do NOT remove any existing GestureType enum values
- ALL files must be complete — no "... existing code ..." placeholders
- Every method must have a return statement on all paths
- No print() calls except startup messages (one per module max)

=== FILE 1: Create src/eye_tracker.py (NEW FILE) ===

Create this file from scratch. It uses MediaPipe FaceMesh with refine_landmarks=True to track iris positions. The detect() method returns (cam_x, cam_y) in camera pixel coordinates with a configurable GAIN multiplier to amplify small eye movements.

```python
"""Iris-based cursor tracker using MediaPipe Face Mesh (experimental).

Uses refine_landmarks=True to access iris landmarks 468/473.
GAIN amplifies tiny eye movements so user doesn't need to move their whole head.
"""
from __future__ import annotations

import cv2

try:
    import mediapipe as mp
    _OK = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
except Exception:
    mp = None
    _OK = False


class EyeTracker:
    LEFT_IRIS = 468
    RIGHT_IRIS = 473

    def __init__(self, gain: float = 1.8) -> None:
        self._mesh = None
        self._eye_x = -1.0
        self._eye_y = -1.0
        self._init = False
        self.available = False
        self._last_results = None
        self._gain = max(1.0, min(3.0, gain))

        if not _OK or mp is None:
            return
        try:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.4,
            )
            self.available = True
            print("[EYE] Iris tracker ready (experimental)")
        except Exception:
            pass

    def detect(self, frame_bgr) -> tuple[int, int] | None:
        if not self.available or self._mesh is None:
            return None
        try:
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self._mesh.process(rgb)
            self._last_results = res

            if not res.multi_face_landmarks:
                self._init = False
                return None

            face = res.multi_face_landmarks[0]
            l_iris = face.landmark[self.LEFT_IRIS]
            r_iris = face.landmark[self.RIGHT_IRIS]

            # Average both irises for stability
            rx = ((l_iris.x + r_iris.x) / 2.0) * w
            ry = ((l_iris.y + r_iris.y) / 2.0) * h

            # Apply gain: amplify movement from center
            cx, cy = w / 2.0, h / 2.0
            rx = cx + (rx - cx) * self._gain
            ry = cy + (ry - cy) * self._gain

            if not self._init:
                self._eye_x, self._eye_y = rx, ry
                self._init = True
            else:
                # 1.2px deadzone kills webcam micro-jitter
                if abs(rx - self._eye_x) >= 1.2:
                    self._eye_x = rx
                if abs(ry - self._eye_y) >= 1.2:
                    self._eye_y = ry

            return int(self._eye_x), int(self._eye_y)
        except Exception:
            return None

    def draw(self, frame_rgb) -> None:
        if not self.available or self._last_results is None:
            return
        try:
            res = self._last_results
            if not res.multi_face_landmarks:
                return
            face = res.multi_face_landmarks[0]
            h, w = frame_rgb.shape[:2]
            for iris_idx in (self.LEFT_IRIS, self.RIGHT_IRIS):
                pt = face.landmark[iris_idx]
                cv2.circle(frame_rgb, (int(pt.x * w), int(pt.y * h)), 4, (0, 255, 255), -1)
        except Exception:
            pass

    def close(self) -> None:
        if self._mesh is not None:
            try:
                self._mesh.close()
            except Exception:
                pass
```

=== FILE 2: Replace src/hand_tracker.py COMPLETELY ===

The new HandTracker uses max_num_hands=2 and returns a dictionary keyed by "Left"/"Right" containing hand_data for each detected hand, plus a list of (proto, label) tuples for drawing.

The return signature changes from:
  (hand_data, hand_proto, is_grace) 
to:
  (hands_dict, hand_protos_list, is_grace)

Where:
- hands_dict = {"Left": {xy, label, confidence, ...}, "Right": {...}} or {}
- hand_protos_list = [(mediapipe_proto, "Left"), (mediapipe_proto, "Right")] or []
- is_grace = bool

```python
from __future__ import annotations

import os
from collections import deque

import cv2

try:
    import mediapipe as mp
except Exception:
    mp = None

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from .utils import _ensure_mediapipe_solutions


class HandTracker:
    @staticmethod
    def _map_label(raw_label: str, is_mirrored: bool) -> str:
        raw = str(raw_label)
        if raw not in ("Left", "Right"):
            return raw
        if is_mirrored:
            return "Right" if raw == "Left" else "Left"
        return raw

    def __init__(self) -> None:
        self._process_size: tuple[int, int] | None = None
        self._last_rgb_frame = None
        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands
        self._draw_utils = mp.solutions.drawing_utils
        self._draw_styles = mp.solutions.drawing_styles

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.55,
            min_tracking_confidence=0.35,
        )

        self._frames_no_hand = 0
        self._grace_frames = 3
        self._last_valid_result: tuple[dict, list, bool] | None = None

    def set_processing_size(self, size: tuple[int, int] | None) -> None:
        if size is None:
            self._process_size = None
            return
        w, h = size
        self._process_size = (max(64, int(w)), max(64, int(h)))

    def detect(self, frame_bgr, is_mirrored: bool = False):
        """Returns (hands_dict, hand_protos_list, is_grace_frame)."""
        src_h, src_w = frame_bgr.shape[:2]

        detect_frame = frame_bgr
        if self._process_size is not None:
            detect_frame = cv2.resize(frame_bgr, self._process_size, 
                                       interpolation=cv2.INTER_LINEAR)

        dh, dw = detect_frame.shape[:2]
        rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        self._last_rgb_frame = rgb
        result = self._hands.process(rgb)

        hands_dict = {}
        protos = []

        if result.multi_hand_landmarks and result.multi_handedness:
            sx = float(src_w) / max(1, dw)
            sy = float(src_h) / max(1, dh)

            for idx, hand in enumerate(result.multi_hand_landmarks):
                if idx >= len(result.multi_handedness):
                    break
                raw_label = result.multi_handedness[idx].classification[0].label
                label = self._map_label(raw_label, is_mirrored)
                conf = float(result.multi_handedness[idx].classification[0].score)

                if conf < 0.40:
                    continue

                xy = [(int(lm.x * dw * sx), int(lm.y * dh * sy)) 
                      for lm in hand.landmark]
                z = [float(lm.z) for lm in hand.landmark]

                # If we already have this label, keep the higher-confidence one
                if label in hands_dict:
                    if conf <= hands_dict[label]["confidence"]:
                        continue

                hands_dict[label] = {
                    "xy": xy,
                    "z": z,
                    "label": label,
                    "confidence": conf,
                    "frame_size": (dw, dh),
                }
                protos.append((hand, label))

        if hands_dict:
            self._frames_no_hand = 0
            self._last_valid_result = (hands_dict, protos, False)
            return hands_dict, protos, False
        else:
            self._frames_no_hand += 1
            if (self._frames_no_hand < self._grace_frames 
                    and self._last_valid_result is not None):
                cached_dict, cached_protos, _ = self._last_valid_result
                return cached_dict, cached_protos, True
            self._last_valid_result = None
            return {}, [], False

    def draw(self, frame_rgb, hand_protos, label: str = "Right") -> None:
        """Draw hand landmarks. Accepts either:
        - A list of (proto, label) tuples (new dual-hand format)
        - A single proto object (legacy single-hand format)
        """
        if hand_protos is None:
            return

        # Handle legacy single-proto call: draw(rgb, proto, label_str)
        if not isinstance(hand_protos, list):
            pairs = [(hand_protos, label)]
        else:
            pairs = hand_protos

        for proto, lbl in pairs:
            if proto is None:
                continue
            color = (0, 255, 120) if lbl == "Right" else (255, 180, 50)
            try:
                conn_spec = self._draw_utils.DrawingSpec(
                    color=color, thickness=2, circle_radius=2)
                lmk_spec = self._draw_styles.get_default_hand_landmarks_style()
                self._draw_utils.draw_landmarks(
                    frame_rgb, proto, self._mp_hands.HAND_CONNECTIONS,
                    lmk_spec, conn_spec)
            except Exception:
                pass

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
        except Exception:
            pass
```

=== FILE 3: Replace src/gesture_detector.py COMPLETELY ===

The new GestureDetector.detect() accepts EITHER:
- A dict with "Left"/"Right" keys (dual-hand mode) via detect_dual(hands_dict)  
- A single hand_data dict (legacy) via detect(hand_data)

In DUAL-HAND mode (default):
- LEFT HAND index finger tip (landmark 8) = cursor position (handled in main_window)
- RIGHT HAND: thumb+index pinch = left click, thumb+middle pinch = right click, peace sign = scroll, hold pinch = drag
- The gesture detector ONLY processes the RIGHT hand for gestures

In LEGACY/SINGLE-HAND mode:
- Same hand does both cursor and gestures (backward compatible)

Replace the ENTIRE file with:

```python
from __future__ import annotations

import math
import time

try:
    from .fast_math import pinch_dist_2d, ema_step
except Exception:
    def pinch_dist_2d(x1, y1, x2, y2):
        dx = x1 - x2; dy = y1 - y2
        return math.sqrt(dx * dx + dy * dy)
    def ema_step(prev, target, alpha):
        return prev + alpha * (target - prev)

from .models import GestureResult, GestureType
from .tuning import (
    GESTURE_ACTION_COOLDOWN_S,
    GESTURE_CONFIRM_HOLD_S,
    GESTURE_DOUBLE_CLICK_WINDOW_S,
    GESTURE_DRAG_ACTIVATE_S,
    GESTURE_RIGHT_CLICK_HOLD_S,
    GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S,
)


class GestureDetector:
    def __init__(self) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._stable_start_t = 0.0

        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since: float | None = None
        self._right_pinch_start_t: float | None = None

        self._scroll_prev_y: float | None = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0
        self._scroll_last_switch_time = 0.0

        self._action_cooldown_s = float(GESTURE_ACTION_COOLDOWN_S)
        self._drag_activate_s = float(GESTURE_DRAG_ACTIVATE_S)

        self._pinch_enter = 0.22
        self._pinch_exit = 0.36
        self._confirm_hold_s = float(GESTURE_CONFIRM_HOLD_S)
        self._hand_scale = 24.0

        self._last_click_time = 0.0
        self._last_right_click_time = 0.0
        self._left_click_release_time = -float('inf')

        self._scroll_step_factor = 0.08
        self._scroll_deadband_factor = 0.06
        self._double_click_window_s = float(GESTURE_DOUBLE_CLICK_WINDOW_S)
        self._scroll_dir_switch_cooldown_s = float(GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S)
        self._scroll_step_limit = 8
        self._scroll_gain = 1.0
        self._right_click_hold_s = max(0.15, float(GESTURE_RIGHT_CLICK_HOLD_S))

        self._per_action_cooldown = {
            GestureType.LEFT_CLICK: 0.25,
            GestureType.RIGHT_CLICK: 0.50,
            GestureType.DOUBLE_CLICK: 0.50,
            GestureType.SCROLL: 0.0,
            GestureType.DRAG: 0.0,
            GestureType.MOVE: 0.0,
        }
        self._last_action_time: dict[GestureType, float] = {}

        # Z-tap (kept for settings compat, disabled by default)
        self._z_tap_enabled = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    def reset_cooldowns(self) -> None:
        self._last_action_time.clear()

    def _make_result(self, gesture: GestureType, scroll_delta: int = 0) -> GestureResult:
        return GestureResult(gesture, scroll_delta)

    def _pinch_ratios(self, xy, hand_scale: float) -> tuple[float, float, float]:
        hs = max(1.0, hand_scale)
        p4 = xy[4]; p8 = xy[8]; p12 = xy[12]
        li = pinch_dist_2d(float(p4[0]), float(p4[1]), float(p8[0]), float(p8[1])) / hs
        ri = pinch_dist_2d(float(p4[0]), float(p4[1]), float(p12[0]), float(p12[1])) / hs
        pm = pinch_dist_2d(float(p8[0]), float(p8[1]), float(p12[0]), float(p12[1])) / hs
        return li, ri, pm

    def _check_action_cooldown(self, gesture: GestureType, now: float) -> bool:
        cooldown = self._per_action_cooldown.get(gesture, self._action_cooldown_s)
        last = self._last_action_time.get(gesture, 0.0)
        return (now - last) >= cooldown

    def _record_action(self, gesture: GestureType, now: float) -> None:
        self._last_action_time[gesture] = now

    def _resolve_scroll(self, current_y: float, hand_scale: float) -> int:
        if self._scroll_prev_y is None:
            self._scroll_prev_y = current_y
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            self._scroll_accumulator = 0.0
            return 0

        dy = float(self._scroll_prev_y) - current_y
        self._scroll_prev_y = current_y

        self._scroll_velocity_ema = ema_step(self._scroll_velocity_ema, dy, 0.25)
        v = self._scroll_velocity_ema

        deadband = max(1.0, hand_scale * self._scroll_deadband_factor)
        if abs(v) <= deadband:
            self._scroll_accumulator *= 0.5
            return 0

        step = max(1.0, hand_scale * self._scroll_step_factor)
        self._scroll_accumulator += v / step

        steps = int(self._scroll_accumulator)
        if steps == 0:
            return 0
        self._scroll_accumulator -= steps
        steps = max(-self._scroll_step_limit, min(self._scroll_step_limit, steps))

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

    def _clear_scroll(self) -> None:
        self._scroll_prev_y = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0

    # =====================================================================
    # DUAL-HAND MODE (default) — left hand = cursor, right hand = actions
    # =====================================================================
    def detect_dual(self, hands_dict: dict, is_grace: bool = False) -> GestureResult:
        """Process gestures from dual-hand input.
        
        LEFT hand: cursor tracking (handled in main_window, not here)
        RIGHT hand: click/scroll/drag gestures
        
        If only LEFT hand visible: return MOVE (cursor follows left index)
        If only RIGHT hand visible: process gestures, cursor uses right index
        If neither: PAUSE
        """
        now = time.monotonic()
        right_hand = hands_dict.get("Right")
        left_hand = hands_dict.get("Left")

        # No hands at all
        if not right_hand and not left_hand:
            self._reset_all(now)
            return self._make_result(GestureType.PAUSE, 0)

        # Only left hand (cursor hand) — just MOVE, no actions
        if not right_hand and left_hand:
            self._state = GestureType.MOVE
            self._dragging = False
            return self._make_result(GestureType.MOVE, 0)

        # Right hand is present — process gestures
        return self._process_action_hand(right_hand, now, is_grace)

    # =====================================================================
    # SINGLE-HAND MODE (legacy compat) — one hand does cursor + actions
    # =====================================================================
    def detect(self, hand_data: dict | None, is_grace_frame: bool = False) -> GestureResult:
        """Legacy single-hand detect. Same hand does cursor + gestures."""
        now = time.monotonic()
        if hand_data is None:
            self._reset_all(now)
            return self._make_result(GestureType.PAUSE, 0)

        return self._process_action_hand(hand_data, now, is_grace_frame)

    # =====================================================================
    # SHARED ACTION ENGINE — processes one hand for click/scroll/drag
    # =====================================================================
    def _process_action_hand(self, hand_data: dict, now: float, 
                              is_grace: bool = False) -> GestureResult:
        xy = hand_data.get("xy")
        if not xy or len(xy) < 21:
            return self._make_result(GestureType.PAUSE, 0)

        confidence = float(hand_data.get("confidence", 0.0))
        if confidence < 0.20:
            return self._make_result(GestureType.PAUSE, 0)

        # Compute hand scale
        try:
            wrist = xy[0]; mcp9 = xy[9]
            self._hand_scale = max(24.0, pinch_dist_2d(
                float(wrist[0]), float(wrist[1]),
                float(mcp9[0]), float(mcp9[1])))
        except (IndexError, TypeError):
            return self._make_result(GestureType.PAUSE, 0)

        li, ri, pm = self._pinch_ratios(xy, self._hand_scale)
        enter = float(self._pinch_enter)
        exit_ = float(self._pinch_exit)

        # --- Left pinch (thumb+index) = click/drag ---
        prev_left = self._left_pinch_active
        if self._left_pinch_active:
            if li > exit_:
                self._left_pinch_active = False
                self._left_click_release_time = now
        elif li <= enter:
            self._left_pinch_active = True

        # --- Right pinch (thumb+middle) = right-click ---
        # Requires: index finger clearly open (li > exit_), 
        # middle+thumb close, held for _right_click_hold_s
        right_enter = enter * 0.50
        if self._right_pinch_active:
            if ri > exit_:
                self._right_pinch_active = False
                self._right_pinch_start_t = None
        elif ri <= right_enter and li > exit_ and pm > 0.15:
            if self._right_pinch_start_t is None:
                self._right_pinch_start_t = now
            elif now - self._right_pinch_start_t >= self._right_click_hold_s:
                self._right_pinch_active = True
        else:
            self._right_pinch_start_t = None

        # --- Peace sign (index+middle spread) = scroll ---
        peace_pose = (pm >= 0.06 and pm <= 0.65 and li > exit_ and ri > exit_)

        # --- Track pinch duration for drag ---
        if self._left_pinch_active:
            if self._left_pinch_since is None:
                self._left_pinch_since = now
        else:
            self._left_pinch_since = None

        # --- Route to raw state ---
        raw_state = GestureType.MOVE

        if self._left_pinch_active and self._left_pinch_since is not None:
            held = now - self._left_pinch_since
            if held >= self._drag_activate_s:
                raw_state = GestureType.DRAG
            else:
                raw_state = GestureType.LEFT_CLICK
        elif self._right_pinch_active:
            raw_state = GestureType.RIGHT_CLICK
        elif peace_pose:
            raw_state = GestureType.SCROLL

        # --- Stability filter ---
        if raw_state != self._candidate:
            self._candidate = raw_state
            self._stable_start_t = now

        hold_elapsed = max(0.0, now - self._stable_start_t)
        if is_grace:
            stable_state = self._state if self._state not in {
                GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK} else GestureType.MOVE
        elif hold_elapsed >= self._confirm_hold_s:
            stable_state = self._candidate
        else:
            stable_state = self._state

        # --- Clear scroll when not scrolling ---
        if stable_state != GestureType.SCROLL and self._state != GestureType.SCROLL:
            self._clear_scroll()

        # --- Emit actions ---
        if stable_state == GestureType.LEFT_CLICK:
            if self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                # Double-click detection
                if (self._left_click_release_time > 0.0 
                    and 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s
                    and self._check_action_cooldown(GestureType.DOUBLE_CLICK, now)):
                    self._state = GestureType.DOUBLE_CLICK
                    self._record_action(GestureType.DOUBLE_CLICK, now)
                    self._record_action(GestureType.LEFT_CLICK, now)
                    self._dragging = False
                    return self._make_result(GestureType.DOUBLE_CLICK, 0)

                self._state = GestureType.LEFT_CLICK
                self._record_action(GestureType.LEFT_CLICK, now)
                self._dragging = False
                return self._make_result(GestureType.LEFT_CLICK, 0)
            self._state = GestureType.MOVE
            return self._make_result(GestureType.MOVE, 0)

        if stable_state == GestureType.RIGHT_CLICK:
            if self._check_action_cooldown(GestureType.RIGHT_CLICK, now):
                self._state = GestureType.RIGHT_CLICK
                self._record_action(GestureType.RIGHT_CLICK, now)
                self._dragging = False
                return self._make_result(GestureType.RIGHT_CLICK, 0)
            self._state = GestureType.MOVE
            return self._make_result(GestureType.MOVE, 0)

        if stable_state == GestureType.DRAG:
            self._dragging = True
            self._state = GestureType.DRAG
            return self._make_result(GestureType.DRAG, 0)

        if stable_state == GestureType.SCROLL:
            delta = self._resolve_scroll(float(xy[8][1]), self._hand_scale)
            self._state = GestureType.SCROLL
            self._dragging = False
            return self._make_result(GestureType.SCROLL, delta)

        self._state = GestureType.MOVE
        self._dragging = False
        return self._make_result(GestureType.MOVE, 0)

    def _reset_all(self, now: float) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._stable_start_t = now
        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since = None
        self._right_pinch_start_t = None
        self._clear_scroll()
```

=== FILE 4: Update src/tuning.py ===

Change these values:
- GESTURE_RIGHT_CLICK_HOLD_S = 0.18  (was 0.10, prevents accidental right-clicks)
- GESTURE_DRAG_ACTIVATE_S = 0.45     (was 0.38, prevents accidental drags)
- GESTURE_CONFIRM_HOLD_S = 0.04      (was 0.03, slightly more stable)
- GESTURE_DOUBLE_CLICK_WINDOW_S = 0.45  (was 0.38, more forgiving)

=== FILE 5: Update src/settings_store.py ===

Add these new keys to DEFAULTS dict:
    "cursor_mode": "dual_hand",       # "dual_hand" | "single_hand" | "eye_tracking"
    "eye_tracking_gain": 1.8,
    "hand_only_mode": True,           # Change default from False to True

=== FILE 6: Update src/models.py ===

No changes needed — all existing GestureType values must remain unchanged.

=== VERIFICATION CHECKLIST ===
After applying, confirm:
1. HandTracker.detect() returns (dict, list, bool) — NOT (single_dict, proto, bool)
2. GestureDetector has both detect() and detect_dual() methods
3. EyeTracker exists at src/eye_tracker.py
4. No circular imports
5. All import paths resolve
```

---

## PROMPT 2 — Main Window Rewire

```
You are updating src/main_window.py for the Holographic Touch gesture mouse app.

The HandTracker and GestureDetector have been rewritten (Prompt 1 was already applied):
- HandTracker.detect() now returns (hands_dict, hand_protos_list, is_grace)
  where hands_dict = {"Left": {...}, "Right": {...}} and hand_protos_list = [(proto, label), ...]
- GestureDetector has detect_dual(hands_dict) for dual-hand and detect(hand_data) for single-hand
- EyeTracker is a new class at src/eye_tracker.py

=== IMPORTANT RULES ===
- Do NOT rewrite the entire file — only change the specific sections listed below
- Keep ALL existing UI layout code, styles, tray, hotkey, overlay — do NOT touch those
- Every change is surgical and described with FIND → REPLACE blocks
- Output the COMPLETE file content for main_window.py

=== CHANGE 1: Update imports ===

Add at the top imports section, after the existing imports:
```python
from .eye_tracker import EyeTracker
```

The import for FaceTracker should remain — it's still used as legacy fallback.

=== CHANGE 2: Update MainWindow.__init__ ===

Find where self.face_tracker is created:
```python
        try:
            self.face_tracker: FaceTracker | None = FaceTracker()
        except Exception:
            self.face_tracker = None
```

After that block, ADD:
```python
        # Eye tracker (experimental — enabled in settings)
        self.eye_tracker: EyeTracker | None = None
        self._cursor_mode: str = str(settings.get("cursor_mode", "dual_hand"))
        if self._cursor_mode == "eye_tracking":
            try:
                gain = float(settings.get("eye_tracking_gain", 1.8))
                self.eye_tracker = EyeTracker(gain=gain)
            except Exception:
                self.eye_tracker = None
```

Find where self._hand_only_mode is set:
```python
        self._hand_only_mode: bool = _as_bool(
            settings.get("hand_only_mode", False), False)
```

Change to:
```python
        self._hand_only_mode: bool = self._cursor_mode != "eye_tracking"
```

This makes dual_hand and single_hand both use hand-based cursor, only eye_tracking uses eyes.

=== CHANGE 3: Rewrite _process_loop cursor dispatch ===

Find the _process_loop method. Replace the ENTIRE body from "while self.running:" through the end of the method with:

```python
    def _process_loop(self) -> None:
        last_overlay = GestureType.NONE
        last_action = GestureType.NONE
        last_task_view_action = 0.0
        last_hand_time = time.monotonic()

        _boost_runtime_priority()

        while self.running:
            if time.monotonic() - last_hand_time > 5.0:
                time.sleep(0.005)

            try:
                frame = self.camera.latest()
                if frame is None:
                    continue

                if self._mirror_camera:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                self.mapper.set_camera_size(w, h)

                # ── FACE / EYE TRACKER ─────────────────────────────
                face_pos: tuple[int, int] | None = None
                eye_pos: tuple[int, int] | None = None

                if self._cursor_mode == "eye_tracking" and self.eye_tracker is not None:
                    eye_pos = self.eye_tracker.detect(frame)
                elif self.face_tracker is not None and self.face_tracker.available:
                    face_pos = self.face_tracker.detect(frame)

                self._nose_pos = face_pos
                if face_pos is None and eye_pos is None:
                    self._face_lost_frames += 1
                    if self._face_lost_frames > 3:
                        self._scroll_nose_y = None
                else:
                    self._face_lost_frames = 0
                _face_tracked = (face_pos is not None) or (eye_pos is not None)

                # ── HAND TRACKER ───────────────────────────────────
                tracker = self.tracker
                if tracker is None:
                    continue

                hands_dict, hand_protos, is_grace = tracker.detect(
                    frame, is_mirrored=self._mirror_camera)

                rgb_cached = getattr(tracker, '_last_rgb_frame', None)

                if hands_dict:
                    last_hand_time = time.monotonic()
                    # Compute hand scale from whichever hand is available
                    for _hd in hands_dict.values():
                        _xy = _hd.get("xy", [])
                        if len(_xy) >= 10:
                            _w = _xy[0]; _m = _xy[9]
                            scale = ((_w[0]-_m[0])**2 + (_w[1]-_m[1])**2)**0.5
                            self.mapper.set_hand_scale(scale)
                            break
                    self._camera_error_text = ""
                else:
                    self._camera_error_text = self.camera.last_error

                # ── GESTURE DETECTION ──────────────────────────────
                if self._cursor_mode == "dual_hand":
                    result = self.gestures.detect_dual(hands_dict, is_grace)
                else:
                    # Single-hand or eye-tracking: use right hand for gestures
                    action_hand = hands_dict.get("Right") or hands_dict.get("Left")
                    result = self.gestures.detect(action_hand, is_grace)

                if result is None:
                    result = GestureResult(GestureType.PAUSE, 0)

                gesture = result.gesture
                gesture_changed = gesture != last_action

                # Confidence gate
                _action_hand = hands_dict.get("Right") or hands_dict.get("Left")
                if _action_hand and float(_action_hand.get("confidence", 0)) < 0.55:
                    if gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                                   GestureType.DOUBLE_CLICK}:
                        gesture = GestureType.MOVE
                        result = GestureResult(GestureType.MOVE, 0)
                        gesture_changed = gesture != last_action

                # ── CURSOR POSITION ────────────────────────────────
                _has_cursor = False
                sx, sy = self._frozen_sx, self._frozen_sy

                if self._cursor_mode == "eye_tracking":
                    # Eye tracking mode: eyes drive cursor
                    if eye_pos is not None:
                        sx, sy = self.mapper.map_point(eye_pos[0], eye_pos[1])
                        _has_cursor = True
                    elif face_pos is not None:
                        sx, sy = self.mapper.map_point(face_pos[0], face_pos[1])
                        _has_cursor = True
                    else:
                        _has_cursor = self._frozen_sx >= 0

                elif self._cursor_mode == "dual_hand":
                    # Dual-hand: LEFT hand index finger = cursor
                    left_hand = hands_dict.get("Left")
                    if gesture in self._freeze_on:
                        # Freeze cursor during clicks
                        _has_cursor = self._frozen_sx >= 0
                    elif left_hand and len(left_hand.get("xy", [])) > 8:
                        tip = left_hand["xy"][8]
                        sx, sy = self.mapper.map_point(int(tip[0]), int(tip[1]))
                        _has_cursor = True
                    elif hands_dict.get("Right") and len(hands_dict["Right"].get("xy", [])) > 8:
                        # Fallback: if only right hand, use right index for cursor
                        tip = hands_dict["Right"]["xy"][8]
                        sx, sy = self.mapper.map_point(int(tip[0]), int(tip[1]))
                        _has_cursor = True
                    else:
                        _has_cursor = self._frozen_sx >= 0

                else:
                    # Single-hand legacy: index finger = cursor
                    _any_hand = hands_dict.get("Right") or hands_dict.get("Left")
                    if gesture in self._freeze_on:
                        _has_cursor = self._frozen_sx >= 0
                    elif _any_hand and len(_any_hand.get("xy", [])) > 8:
                        tip = _any_hand["xy"][8]
                        sx, sy = self.mapper.map_point(int(tip[0]), int(tip[1]))
                        _has_cursor = True
                    else:
                        _has_cursor = self._frozen_sx >= 0

                if _has_cursor:
                    self._frozen_sx, self._frozen_sy = sx, sy

                # ── DISPATCH ACTIONS ───────────────────────────────
                _allow_action = not is_grace

                if self.mouse_enabled and _has_cursor and gesture in self._CURSOR_GESTURES:
                    if gesture != GestureType.SCROLL:
                        self.mouse.move(sx, sy)

                    if gesture == GestureType.MOVE:
                        pass
                    elif gesture == GestureType.LEFT_CLICK and gesture_changed and _allow_action:
                        self.mouse.left_click()
                    elif gesture == GestureType.DOUBLE_CLICK and gesture_changed and _allow_action:
                        self.mouse.double_click()
                    elif gesture == GestureType.RIGHT_CLICK and gesture_changed and _allow_action:
                        self.mouse.right_click()
                    elif gesture == GestureType.SCROLL and _allow_action:
                        self.mouse.scroll(int(result.scroll_delta * self._scroll_multiplier))
                    elif gesture == GestureType.DRAG:
                        if not self._drag_active:
                            self.mouse.start_drag()
                            self._drag_active = True

                    if gesture != GestureType.DRAG and self.mouse.is_dragging:
                        self.mouse.end_drag()
                        self._drag_active = False
                else:
                    if self.mouse.is_dragging:
                        self.mouse.end_drag()
                        self._drag_active = False

                if not self.mouse_enabled and self.mouse.is_dragging:
                    self.mouse.end_drag()
                    self._drag_active = False

                # ── UPDATE UI STATE ────────────────────────────────
                if gesture != last_overlay:
                    overlay = _OVERLAY_LABELS.get(gesture, "")
                    last_overlay = gesture
                else:
                    overlay = self._overlay_text

                if gesture != last_action:
                    ts = time.strftime("%H:%M:%S")
                    self._gesture_history.appendleft((gesture, ts))

                last_action = gesture

                now = time.monotonic()
                dt = now - self._fps_prev
                self._fps_prev = now
                if dt > 0:
                    fps_i = 1.0 / dt
                    self.fps = fps_i if self.fps == 0 else 0.9 * self.fps + 0.1 * fps_i

                # Finger count
                _finger_count = 0
                _count_hand = hands_dict.get("Right") or hands_dict.get("Left")
                if _count_hand:
                    try:
                        _xy = _count_hand.get("xy", [])
                        if len(_xy) >= 21:
                            _w = _xy[0]
                            for _t, _p in zip([4,8,12,16,20], [2,6,10,14,18]):
                                _td = ((_xy[_t][0]-_w[0])**2+(_xy[_t][1]-_w[1])**2)**0.5
                                _pd = ((_xy[_p][0]-_w[0])**2+(_xy[_p][1]-_w[1])**2)**0.5
                                if _td > _pd:
                                    _finger_count += 1
                    except Exception:
                        pass

                with self._lock:
                    self._frame = frame
                    self._rgb_frame = rgb_cached
                    self._gesture = gesture
                    self._overlay_text = overlay
                    self._hand_proto = hand_protos  # Now a list of (proto, label)
                    self._hand_data = _count_hand
                    self._fingers = _finger_count
                    self._face_tracked = _face_tracked

            except Exception:
                continue
```

=== CHANGE 4: Update _render to handle new hand_protos format ===

In _render(), find where hand skeleton is drawn:
```python
        if hand_proto is not None and tracker is not None:
            label = hand_data["label"] if hand_data else "Right"
            tracker.draw(rgb, hand_proto, label)
```

Replace with:
```python
        if hand_proto is not None and tracker is not None:
            # hand_proto is now a list of (proto, label) tuples
            if isinstance(hand_proto, list):
                tracker.draw(rgb, hand_proto)
            else:
                label = hand_data["label"] if hand_data else "Right"
                tracker.draw(rgb, hand_proto, label)
```

Also in _render(), add eye tracker drawing. After the face_tracker.draw() call, add:
```python
        if self._cursor_mode == "eye_tracking" and self.eye_tracker is not None:
            self.eye_tracker.draw(rgb)
```

=== CHANGE 5: Update _render badge text ===

Find:
```python
        if gesture == GestureType.MOVE and not self._hand_only_mode:
            _badge_text = "TRACKING" if self._face_tracked else "ACQUIRING"
```

Replace with:
```python
        if gesture == GestureType.MOVE:
            if self._cursor_mode == "dual_hand":
                _badge_text = "DUAL HAND"
            elif self._cursor_mode == "eye_tracking":
                _badge_text = "IRIS TRACK" if self._face_tracked else "ACQUIRING"
            else:
                _badge_text = "TRACKING" if self._face_tracked else "ACQUIRING"
```

=== CHANGE 6: Update Settings Dialog — add cursor mode selector ===

In the SettingsDialog, in the Gestures tab, find the hand_only_chk checkbox and REPLACE it with a cursor mode combo box:

Remove:
```python
        self.hand_only_chk = QCheckBox(...)
        self.hand_only_chk.setChecked(...)
        self.hand_only_chk.setToolTip(...)
        gesture_layout.addWidget(self.hand_only_chk)
```

Replace with:
```python
        cursor_mode_label = QLabel("Cursor Control Mode")
        cursor_mode_label.setObjectName("section")
        self.cursor_mode_combo = QComboBox()
        self.cursor_mode_combo.addItem("Dual Hand (Left=Cursor, Right=Actions)", "dual_hand")
        self.cursor_mode_combo.addItem("Single Hand (same hand)", "single_hand")
        self.cursor_mode_combo.addItem("Eye Tracking (experimental)", "eye_tracking")
        current_mode = str(settings.get("cursor_mode", "dual_hand"))
        idx = self.cursor_mode_combo.findData(current_mode)
        if idx >= 0:
            self.cursor_mode_combo.setCurrentIndex(idx)
        gesture_layout.addWidget(cursor_mode_label)
        gesture_layout.addWidget(self.cursor_mode_combo)
```

Add the signal connection:
```python
        self.cursor_mode_combo.currentIndexChanged.connect(self._on_cursor_mode_changed)
```

Add the handler method to SettingsDialog:
```python
    def _on_cursor_mode_changed(self, idx: int) -> None:
        mode = self.cursor_mode_combo.itemData(idx)
        if mode:
            settings.set("cursor_mode", str(mode))
            QMessageBox.information(self, "Restart Required", 
                "Cursor mode change requires restarting the camera.")
```

Remove the _on_hand_only_changed handler and its signal connection.

=== CHANGE 7: Update guide rows ===

Update guide_rows for dual-hand mode in _build_ui and _update_guide_rows:

```python
        guide_rows_dual = [
            ("move",        "Move cursor",   "Left hand index finger"),
            ("left_click",  "Left click",    "Right: Thumb+Index pinch"),
            ("double_click","Double click",  "Right: Quick double pinch"),
            ("drag",        "Drag",          "Right: Hold pinch"),
            ("right_click", "Right click",   "Right: Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Right: Peace sign up/down"),
        ]
```

=== CHANGE 8: Update _quit_app and closeEvent ===

Add eye_tracker cleanup alongside face_tracker:
```python
        try:
            if self.eye_tracker is not None:
                self.eye_tracker.close()
        except Exception:
            pass
```

=== VERIFICATION CHECKLIST ===
1. _process_loop handles hands_dict (a dict of dicts), not a single hand_data
2. Cursor follows LEFT hand index finger in dual_hand mode
3. RIGHT hand gestures fire clicks/scroll/drag
4. Eye tracking mode uses iris positions for cursor
5. Settings dialog has cursor mode dropdown instead of checkbox
6. No print() spam in the processing loop
7. Drag is properly started/ended
8. _render handles both list and single-proto formats
```

---

## PROMPT 3 — Final Polish, UI Styles, Verification

```
You are doing the FINAL polish pass on the Holographic Touch app.
Prompts 1 and 2 have been applied. The dual-hand system and eye tracker are wired up.

This prompt handles: UI style refresh, guide text updates, mode indicator, 
startup defaults, and a manual test script.

=== IMPORTANT RULES ===
- Only modify the specific sections listed
- Keep all functionality from Prompts 1 and 2 intact
- No new features — only polish and verify

=== CHANGE 1: Update main window stylesheet ===

In MainWindow._build_ui(), find the self.setStyleSheet(...) call and update
the #badge style to handle the new DUAL HAND badge width:

Find:
```
            #badge {
```

Replace the entire #badge block with:
```css
            #badge {
                border-radius: 12px; padding: 6px 18px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0;
                min-width: 100px; max-width: 220px;
                font-size: 13px; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
                text-align: center;
            }
```

=== CHANGE 2: Update mode indicator in status panel ===

In _build_ui, find self.mode_lbl and update its initial text:

```python
        _mode_labels = {
            "dual_hand": "Mode: Dual Hand (L=Cursor R=Actions)",
            "single_hand": "Mode: Single Hand",
            "eye_tracking": "Mode: Eye Tracking (experimental)",
        }
        self.mode_lbl = QLabel(_mode_labels.get(self._cursor_mode, "Mode: Dual Hand"))
        self.mode_lbl.setObjectName("secondary")
        self.mode_lbl.setWordWrap(True)
```

=== CHANGE 3: Update _update_guide_rows to support all 3 modes ===

```python
    def _update_guide_rows(self) -> None:
        guide_rows_dual = [
            ("move",        "Move cursor",   "Left hand index finger"),
            ("left_click",  "Left click",    "Right: Thumb+Index pinch"),
            ("double_click","Double click",  "Right: Quick double pinch"),
            ("drag",        "Drag",          "Right: Hold pinch"),
            ("right_click", "Right click",   "Right: Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Right: Peace sign up/down"),
        ]
        guide_rows_single = [
            ("move",        "Move cursor",   "Index finger up"),
            ("left_click",  "Left click",    "Thumb+Index pinch"),
            ("double_click","Double click",  "Quick double pinch"),
            ("drag",        "Drag",          "Hold pinch"),
            ("right_click", "Right click",   "Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Peace sign up/down"),
        ]
        guide_rows_eye = [
            ("move",        "Move cursor",   "Look around (iris tracking)"),
            ("left_click",  "Left click",    "Right: Thumb+Index pinch"),
            ("double_click","Double click",  "Right: Quick double pinch"),
            ("drag",        "Drag",          "Right: Hold pinch"),
            ("right_click", "Right click",   "Right: Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Right: Peace sign up/down"),
        ]

        if self._cursor_mode == "dual_hand":
            rows = guide_rows_dual
        elif self._cursor_mode == "eye_tracking":
            rows = guide_rows_eye
        else:
            rows = guide_rows_single

        for idx, (il, tl, dl) in enumerate(self._guide_row_widgets):
            if idx < len(rows):
                icon_key, action_desc, gesture_desc = rows[idx]
                il.setPixmap(self.icons[icon_key].pixmap(QSize(18, 18)))
                tl.setText(gesture_desc)
                dl.setText(action_desc)

        _mode_labels = {
            "dual_hand": "Mode: Dual Hand (L=Cursor R=Actions)",
            "single_hand": "Mode: Single Hand",
            "eye_tracking": "Mode: Eye Tracking (experimental)",
        }
        if hasattr(self, "mode_lbl"):
            self.mode_lbl.setText(
                _mode_labels.get(self._cursor_mode, "Mode: Dual Hand"))
```

=== CHANGE 4: Update constants.py ===

The overlay labels should include a clean MOVE label:

In src/constants.py, ensure GestureType.MOVE maps to "MOVE" (no change needed if already correct).

=== CHANGE 5: Update _render hand display for dual-hand ===

In _render(), update the hand status label to show both hands:

Find:
```python
        if not self._hand_only_mode:
```

Replace with:
```python
        if self._cursor_mode == "eye_tracking":
            self.hand_lbl.setText(
                f"Eyes: {'Tracking' if _face_on else 'Lost'}  |  "
                f"Hand: {'Detected' if hand_proto else 'None'}")
        elif self._cursor_mode == "dual_hand":
            # Show both hands status
            _left_ok = False
            _right_ok = False
            if isinstance(hand_proto, list):
                for _, lbl in hand_proto:
                    if lbl == "Left": _left_ok = True
                    if lbl == "Right": _right_ok = True
            self.hand_lbl.setText(
                f"L: {'●' if _left_ok else '○'}  R: {'●' if _right_ok else '○'}")
        else:
```

=== CHANGE 6: Create manual test checklist file ===

Create a file tests/MANUAL_TEST_CHECKLIST.md:

```markdown
# Holographic Touch — Manual Test Checklist

Run through each item. All must pass before release.

## Startup
- [ ] App launches without errors
- [ ] Camera detects and starts
- [ ] No console spam (only startup messages)
- [ ] FPS counter shows 20+ FPS

## Dual-Hand Mode (default)
- [ ] Show LEFT hand: cursor follows left index finger smoothly
- [ ] Show RIGHT hand: cursor follows right index (fallback)
- [ ] Show BOTH hands: cursor follows LEFT, gestures use RIGHT
- [ ] Move left hand across camera view: cursor reaches all screen edges
- [ ] Cursor is smooth — no jitter, no pausing, no teleporting

## Left Click (Right hand: thumb+index pinch)
- [ ] Pinch right thumb+index: single left click fires
- [ ] Release and pinch again: another click (no spam)
- [ ] Click registers on UI elements (try clicking buttons, links)

## Double Click
- [ ] Quick pinch-release-pinch within 0.45s: double click fires
- [ ] Slow pinch-release-pinch (>0.5s): two single clicks, not double

## Right Click
- [ ] Right hand: pinch thumb+middle while index is extended
- [ ] Must hold 0.18s before triggering (no accidental fires)
- [ ] Context menu appears at cursor position

## Scroll
- [ ] Right hand: peace sign (index+middle extended)
- [ ] Move hand UP: page scrolls UP
- [ ] Move hand DOWN: page scrolls DOWN  
- [ ] Scroll is smooth — no jerking
- [ ] Stop hand: scroll stops

## Drag
- [ ] Right hand: hold thumb+index pinch for 0.45s
- [ ] Drag activates — move left hand to drag
- [ ] Release pinch: drag ends cleanly
- [ ] No stuck drags

## Eye Tracking (experimental)
- [ ] Change to eye tracking mode in Settings → Gestures
- [ ] Restart camera
- [ ] Cursor follows eye/head movement
- [ ] Right hand gestures still work for clicks/scroll

## UI
- [ ] Badge shows "DUAL HAND" in dual mode, "IRIS TRACK" in eye mode
- [ ] Hand status shows L: ● R: ● when both hands visible
- [ ] Settings dialog opens and closes without crash
- [ ] Cursor mode dropdown works in settings
- [ ] Window resizes without layout breaking
- [ ] All text readable, no clipping

## Stability
- [ ] Wave hand in/out of view: no crashes, no ghost clicks
- [ ] Cover camera: app handles gracefully
- [ ] Run for 5 minutes: no memory leak, no FPS degradation
- [ ] Enable Mouse → Minimize → Overlay appears → works
```

=== VERIFICATION ===
After this prompt, the app should be:
1. Dual-hand mode works as default — left cursor, right actions
2. Eye tracking available as experimental option
3. Single-hand mode still works (legacy)
4. All gestures functional: click, double-click, right-click, scroll, drag
5. Cursor is smooth and responsive
6. UI is polished and adapts to all modes
7. No console spam
8. Manual test checklist passes 100%
```

---

## Application Order

1. **Apply Prompt 1** → creates eye_tracker.py, rewrites hand_tracker.py and gesture_detector.py, updates tuning + settings
2. **Apply Prompt 2** → rewrites main_window.py process loop, cursor dispatch, settings dialog  
3. **Apply Prompt 3** → final UI polish, guide updates, test checklist

After all 3 prompts: start the app, open Settings → Gestures, confirm "Dual Hand" is selected, start camera, and test with both hands.
