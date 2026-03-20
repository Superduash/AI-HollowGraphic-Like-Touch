from __future__ import annotations

import math
import time
import numpy as np

try:
    from .fast_math import pinch_dist_3d, pinch_dist_2d, ema_step, landmark_distances_np
except Exception:
    def pinch_dist_3d(x1, y1, z1, x2, y2, z2):
        dx = x1 - x2
        dy = y1 - y2
        dz = z1 - z2
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def pinch_dist_2d(x1, y1, x2, y2):
        dx = x1 - x2
        dy = y1 - y2
        return math.sqrt(dx * dx + dy * dy)

    def ema_step(prev, target, alpha):
        return prev + alpha * (target - prev)

    def landmark_distances_np(xy):
        pts = np.asarray(xy, dtype=np.float32)
        diff = pts[1:] - pts[:-1]
        dists = np.empty(21, dtype=np.float32)
        dists[0] = 0.0
        dists[1:] = np.sqrt((diff * diff).sum(axis=1))
        return dists

try:
    from .gesture_classifier import load_model, predict_gesture as _ml_predict
except Exception:
    def load_model() -> bool:
        return False

    def _ml_predict(xy, label="Right"):
        return None, 0.0
from .models import FingerStates, GestureResult, GestureType  # type: ignore
from .tuning import (  # type: ignore
    GESTURE_ACTION_COOLDOWN_S,
    GESTURE_CONFIRM_HOLD_S,
    GESTURE_DOUBLE_CLICK_WINDOW_S,
    GESTURE_DRAG_ACTIVATE_S,
    GESTURE_KEYBOARD_AFTER_PINCH_S,
    GESTURE_KEYBOARD_HOLD_S,
    GESTURE_LOCK_S,
    GESTURE_RIGHT_CLICK_HOLD_S,
    GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S,
    GESTURE_SCROLL_GAIN,
    GESTURE_Z_TAP_ENTER,
    GESTURE_Z_TAP_EXIT,
)

_ML_READY = load_model()


class GestureDetector:
    def __init__(self) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._stable_start_t = 0.0

        self._dragging = False
        self._drag_active = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since: float | None = None
        self._right_pinch_start_t: float | None = None

        self._scroll_prev_y: float | None = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0
        self._scroll_last_switch_time = 0.0
        self._left_media_anchor_y: float | None = None

        self._action_cooldown_s = float(GESTURE_ACTION_COOLDOWN_S)
        self._gesture_lock_s = float(GESTURE_LOCK_S)
        self._locked_until = 0.0
        self._drag_activate_s = float(GESTURE_DRAG_ACTIVATE_S)

        self._pinch_enter = 0.22
        self._pinch_exit = 0.36
        self._confirm_hold_s = float(GESTURE_CONFIRM_HOLD_S)
        self._media_cooldown_s = 0.5
        self._last_media_action_time = 0.0
        self._media_edge_state = GestureType.PAUSE
        self._hand_scale = 24.0

        self._last_click_time = 0.0
        self._last_right_click_time = 0.0
        self._last_media_next_time = 0.0
        self._last_media_prev_time = 0.0
        self._last_double_click_time = 0.0
        self._left_click_release_time = -float('inf')
        self._task_view_since: float | None = None
        self._keyboard_hold_start: float | None = None
        self._keyboard_fired = False

        self._scroll_step_factor = 0.08
        self._scroll_deadband_factor = 0.06
        self._media_step_factor = 0.11
        self._media_deadband_factor = 0.05
        self._double_click_window_s = float(GESTURE_DOUBLE_CLICK_WINDOW_S)
        self._scroll_gain = int(GESTURE_SCROLL_GAIN)
        self._z_tap_enter = float(GESTURE_Z_TAP_ENTER)
        self._z_tap_exit = float(GESTURE_Z_TAP_EXIT)
        self._z_tap_active = False
        self._z_tap_enabled = False
        self._last_move_time: float = 0.0
        self._task_view_hold_s = 0.40
        self._keyboard_after_pinch_s = float(GESTURE_KEYBOARD_AFTER_PINCH_S)
        self._keyboard_hold_s = float(GESTURE_KEYBOARD_HOLD_S)
        self._scroll_dir_switch_cooldown_s = float(GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S)
        self._scroll_step_limit = 8
        self._right_click_hold_s = float(GESTURE_RIGHT_CLICK_HOLD_S)

        self._per_action_cooldown = {
            GestureType.LEFT_CLICK: 0.25,  # FIX 7: was 0.30 — faster click recovery for rapid clicks
            GestureType.RIGHT_CLICK: 0.50,
            GestureType.DOUBLE_CLICK: 0.50,
            GestureType.MEDIA_NEXT: 0.8,
            GestureType.MEDIA_PREV: 0.8,
            GestureType.MEDIA_VOL_UP: 0.05,
            GestureType.MEDIA_VOL_DOWN: 0.05,
            GestureType.SCROLL: 0.0,
            GestureType.DRAG: 0.0,
            GestureType.MOVE: 0.0,
            GestureType.KEYBOARD: 0.5,
            GestureType.TASK_VIEW: 0.8,
        }
        self._last_action_time: dict[GestureType, float] = {}
        self._gesture_entry_set: set[GestureType] = set()
        self._use_ml = _ML_READY
        self._ml_confidence_threshold = 0.70
        if self._use_ml:
            print("[GESTURE] ML classifier loaded")

    @property
    def dragging(self) -> bool:
        return self._dragging

    @staticmethod
    def _distance(a, b) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return math.sqrt(dx * dx + dy * dy)

    def reset_cooldowns(self) -> None:
        self._last_action_time.clear()
        self._gesture_entry_set.clear()

    def _make_result(self, gesture: GestureType, scroll_delta: int = 0, confidence: float = 1.0) -> GestureResult:
        result = GestureResult(gesture, scroll_delta)
        try:
            setattr(result, "gesture_confidence", max(0.0, min(1.0, float(confidence))))
        except Exception:
            pass
        return result

    def _finger_states(self, landmarks_xy) -> FingerStates:
        wrist = landmarks_xy[0]

        thumb_tip = landmarks_xy[4]
        thumb_ip = landmarks_xy[3]
        thumb_mcp = landmarks_xy[2]
        pinky_base = landmarks_xy[17]
        dist_tip_to_pinky = self._distance(thumb_tip, pinky_base)
        dist_mcp_to_pinky = self._distance(thumb_mcp, pinky_base)
        thumb = dist_tip_to_pinky > (dist_mcp_to_pinky * 1.2)

        # Vectorized finger extension detection
        # Tip indices: index=8, middle=12, ring=16, pinky=20
        # MCP  indices: index=5, middle=9, ring=13, pinky=17
        tips = [4, 8, 12, 16, 20]
        mcps = [2, 5,  9, 13, 17]
        pts = np.asarray(landmarks_xy[:21], dtype='float32')
        tip_pts = pts[tips]
        mcp_pts = pts[mcps]
        # Finger is "up" (extended) if tip is higher than its MCP (lower y value)
        extended = tip_pts[:, 1] < mcp_pts[:, 1]

        return FingerStates(
            thumb=thumb,
            index=bool(extended[1]),
            middle=bool(extended[2]),
            ring=bool(extended[3]),
            pinky=bool(extended[4]),
        )

    # REMOVED: finger_count() — use _finger_states() instead (line 128)

    def _check_action_cooldown(self, gesture: GestureType, now: float) -> bool:
        cooldown = self._per_action_cooldown.get(gesture, self._action_cooldown_s)
        last = self._last_action_time.get(gesture, 0.0)
        if now - last < cooldown:
            return False
        # If we're still in the same gesture state, allow it (continuous fire during hold)
        # Only block if this is a NEW gesture attempt while the OLD one is still in cooldown
        if gesture in self._gesture_entry_set and self._state != gesture:
            return False
        return True

    def _record_action(self, gesture: GestureType, now: float) -> None:
        self._last_action_time[gesture] = now

    def _update_pinch_states(self, xy, fs: FingerStates, hand_scale: float, now: float) -> None:
        pinch_enter_ratio = max(0.08, float(self._pinch_enter))
        pinch_exit_ratio = max(pinch_enter_ratio + 0.05, float(self._pinch_exit))
        self._pinch_enter = pinch_enter_ratio
        self._pinch_exit = pinch_exit_ratio

        pinch_enter = hand_scale * pinch_enter_ratio
        pinch_exit = hand_scale * pinch_exit_ratio

        if len(xy[4]) >= 3:
            left_dist = pinch_dist_3d(xy[4][0], xy[4][1], xy[4][2],
                                       xy[8][0], xy[8][1], xy[8][2])
            right_dist = pinch_dist_3d(xy[4][0], xy[4][1], xy[4][2],
                                        xy[12][0], xy[12][1], xy[12][2])
        else:
            left_dist = pinch_dist_2d(xy[4][0], xy[4][1], xy[8][0], xy[8][1])
            right_dist = pinch_dist_2d(xy[4][0], xy[4][1], xy[12][0], xy[12][1])
        pinch_left_ratio = left_dist / max(1.0, hand_scale)

        left_click_pose = left_dist <= pinch_enter

        # FIX 6: Raise right-click anti-cross gate with index extension check
        # Prevents random right-click during left-click when thumb drifts
        index_tip_y = xy[8][1]
        index_mcp_y = xy[5][1]
        index_is_up = index_tip_y < index_mcp_y   # tip above MCP = extended (pixel space: y up)
        right_click_pose = (
            right_dist <= pinch_enter
            and left_dist > (pinch_exit * 1.1)
            and index_is_up  # index must be clearly extended (not pinching left)
        )

        if self._left_pinch_active:
            if left_dist > pinch_exit:
                self._left_pinch_active = False
        elif left_click_pose:
            self._left_pinch_active = True

        if right_click_pose:
            if self._right_pinch_start_t is None:
                self._right_pinch_start_t = now
            if now - self._right_pinch_start_t >= self._right_click_hold_s:  # type: ignore
                self._right_pinch_active = True
        else:
            self._right_pinch_start_t = None
            if right_dist > pinch_exit:
                self._right_pinch_active = False

    def _resolve_scroll(self, current_y: float, hand_scale: float) -> int:
        prev_y = self._scroll_prev_y
        if prev_y is None:
            self._scroll_prev_y = current_y
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            self._scroll_accumulator = 0.0
            return 0

        dy = float(prev_y) - current_y
        self._scroll_prev_y = current_y

        alpha = 0.20
        self._scroll_velocity_ema = ema_step(self._scroll_velocity_ema, dy, alpha)
        velocity = self._scroll_velocity_ema

        hand_scale = max(1.0, hand_scale)
        deadband = max(1.0, min(hand_scale * 0.5, hand_scale * self._scroll_deadband_factor))
        if abs(velocity) <= deadband:
            return 0

        direction = 1 if velocity > 0.0 else -1
        if self._scroll_direction == 0:
            self._scroll_direction = direction
            self._scroll_last_switch_time = time.monotonic()
        elif direction != self._scroll_direction:
            now = time.monotonic()
            if now - self._scroll_last_switch_time < self._scroll_dir_switch_cooldown_s:
                return 0
            self._scroll_direction = direction
            self._scroll_last_switch_time = now

        self._scroll_accumulator += abs(velocity * self._scroll_step_factor)
        emit_count = int(self._scroll_accumulator)
        if emit_count <= 0:
            return 0

        self._scroll_accumulator -= emit_count
        emit_count = max(1, min(self._scroll_step_limit, emit_count))
        return int(direction * emit_count * max(1, self._scroll_gain))

    def _resolve_media_volume(self, current_y: float, hand_scale: float) -> int:
        anchor_y = self._left_media_anchor_y
        if anchor_y is None:
            self._left_media_anchor_y = current_y
            return 0

        delta = float(anchor_y) - current_y
        deadband = hand_scale * self._media_deadband_factor
        if abs(delta) <= deadband:
            return 0

        step = max(1.0, hand_scale * self._media_step_factor)
        steps = int(delta / step)
        if steps == 0:
            return 0

        self._left_media_anchor_y = float(anchor_y) - (steps * step)
        return steps

    def _z_tap_triggered(self, hand_data, fs: FingerStates, now: float) -> bool:
        if not self._z_tap_enabled:
            self._z_tap_active = False
            return False

        z = hand_data.get("z")
        if not isinstance(z, list) or len(z) < 9:
            self._z_tap_active = False
            return False

        if not (fs.index and (not fs.middle) and (not fs.ring) and (not fs.pinky)):
            self._z_tap_active = False
            return False

        z_rel = float(z[8]) - float(z[5])
        if self._z_tap_active:
            if z_rel > self._z_tap_exit:
                self._z_tap_active = False
            return False

        if z_rel < self._z_tap_enter and (now - self._last_click_time >= self._action_cooldown_s):
            self._z_tap_active = True
            return True
        return False

    def _clear_transient_motion(self) -> None:
        self._scroll_prev_y = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_accumulator = 0.0
        self._left_media_anchor_y = None

    def detect(self, hand_data: dict | None, is_grace_frame: bool = False) -> GestureResult:
        now = time.monotonic()

        # ML fast path: if trained model exists and confidence is high, skip rules engine
        if self._use_ml and hand_data and not is_grace_frame:
            xy = hand_data.get("xy", [])
            label = hand_data.get("label", "Right")
            if len(xy) >= 21:
                ml_gesture_name, ml_conf = _ml_predict(xy, label)
                if ml_gesture_name is not None and ml_conf >= self._ml_confidence_threshold:
                    try:
                        gesture_type = GestureType(ml_gesture_name)
                        # Still run cooldown checks for click-type gestures
                        if gesture_type in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DOUBLE_CLICK}:
                            if not self._check_action_cooldown(gesture_type, now):
                                return self._make_result(GestureType.PAUSE, 0, ml_conf)
                            self._record_action(gesture_type, now)
                            self._state = gesture_type
                        return self._make_result(gesture_type, 0, ml_conf)
                    except ValueError:
                        pass   # Unknown gesture name — fall through to rules engine

        if hand_data is None:
            self._state = GestureType.PAUSE
            self._candidate = GestureType.PAUSE
            self._stable_start_t = now
            self._dragging = False
            self._drag_active = False
            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_since = None
            self._right_pinch_start_t = None
            self._keyboard_hold_start = None
            self._keyboard_fired = False
            self._gesture_entry_set.clear()
            self._clear_transient_motion()
            return self._make_result(GestureType.PAUSE, 0, 0.0)

        xy = hand_data.get("xy")
        if not xy or len(xy) < 21:
            return self._make_result(GestureType.PAUSE, 0, 0.0)
        
        try:
            wrist = xy[0]
            middle_mcp = xy[9]
            scale = pinch_dist_2d(float(wrist[0]), float(wrist[1]),
                                  float(middle_mcp[0]), float(middle_mcp[1]))
            self._hand_scale = max(24.0, scale)
        except (IndexError, TypeError):
            return self._make_result(GestureType.PAUSE, 0, 0.0)

        fs = self._finger_states(xy)
        confidence = float(hand_data.get("confidence", 0.0))
        if confidence < 0.20:
            return self._make_result(GestureType.PAUSE, 0, 0.0)

        self._update_pinch_states(xy, fs, self._hand_scale, now)

        if self._left_pinch_active:
            if self._left_pinch_since is None:
                self._left_pinch_since = now
        else:
            self._left_pinch_since = None
            # Clear gesture memory when pinch released
            self._gesture_entry_set.discard(GestureType.LEFT_CLICK)
            self._gesture_entry_set.discard(GestureType.DOUBLE_CLICK)
            self._gesture_entry_set.discard(GestureType.DRAG)

        pinch_guard_active = (
            self._left_pinch_active
            or self._right_pinch_active
            or (0.0 < (now - self._left_click_release_time) < self._keyboard_after_pinch_s)
        )

        move_pose = fs.index and (not fs.middle) and (not fs.ring) and (not fs.pinky)
        # FIX 5: Tighten scroll vs move separation with stricter landmark validation
        # Require ring+pinky to be clearly curled, not just "not up"
        scroll_pose = False
        if fs.index and fs.middle and (not fs.ring) and (not fs.pinky):
            # Extra validation: ring and pinky tips must be BELOW their PIPs (clearly curled)
            ring_tip_y = xy[16][1]
            ring_pip_y = xy[14][1]
            pinky_tip_y = xy[20][1]
            pinky_pip_y = xy[18][1]
            # In pixel space: tip y > pip y means tip is lower (below) = finger is curled
            ring_curled = ring_tip_y > ring_pip_y
            pinky_curled = pinky_tip_y > pinky_pip_y
            if ring_curled and pinky_curled:
                scroll_pose = True
        
        open_palm = fs.thumb and fs.index and fs.middle and fs.ring and fs.pinky

        # Keyboard gesture: pinky + index extended, thumb extended (three-finger salute)
        # Middle and ring must be CURLED to avoid false triggers with open palm / scroll.
        keyboard_pose = (
            fs.index
            and fs.pinky
            and fs.thumb
            and (not fs.middle)
            and (not fs.ring)
        )

        raw_state = GestureType.PAUSE
        media_delta = 0
        
        # Debug disabled
        _debug = False
        
        if _debug:
            print(f"[ROUTING] left_pinch={self._left_pinch_active}, right_pinch={self._right_pinch_active}, move_pose={move_pose}, scroll_pose={scroll_pose}")

        # Both hands share cursor/click/scroll logic.
        # Left hand additionally supports media controls via open_palm hold.

        if open_palm and not self._left_pinch_active and not self._right_pinch_active:
            if self._task_view_since is None:
                self._task_view_since = now
            if now - self._task_view_since >= self._task_view_hold_s:  # type: ignore
                raw_state = GestureType.TASK_VIEW
            else:
                raw_state = GestureType.PAUSE
        else:
            self._task_view_since = None

            if keyboard_pose and not pinch_guard_active:
                if self._keyboard_hold_start is None:
                    self._keyboard_hold_start = now
                hold_elapsed = now - self._keyboard_hold_start  # type: ignore
                if hold_elapsed >= self._keyboard_hold_s and not self._keyboard_fired:
                    raw_state = GestureType.KEYBOARD
                    self._keyboard_fired = True
                else:
                    raw_state = GestureType.PAUSE
            else:
                self._keyboard_hold_start = None
                self._keyboard_fired = False

                if self._left_pinch_active and self._left_pinch_since is not None and (now - self._left_pinch_since >= self._drag_activate_s):  # type: ignore
                    raw_state = GestureType.DRAG
                elif self._left_pinch_active and (not self._right_pinch_active):
                    raw_state = GestureType.LEFT_CLICK
                elif self._right_pinch_active and (not self._left_pinch_active):
                    raw_state = GestureType.RIGHT_CLICK
                elif scroll_pose and (not self._left_pinch_active) and (not self._right_pinch_active):
                    raw_state = GestureType.SCROLL
                elif move_pose:
                    self._last_move_time = now
                    raw_state = GestureType.MOVE
                else:
                    # Fast-motion pose dropout grace: if we were just in MOVE
                    # within the last 80 ms, stay in MOVE to absorb blurry frames.
                    move_grace_s = 0.08
                    last_move = getattr(self, "_last_move_time", 0.0)
                    if self._state == GestureType.MOVE and (now - last_move) < move_grace_s:
                        raw_state = GestureType.MOVE
                    else:
                        raw_state = GestureType.PAUSE

        if raw_state != self._candidate:
            self._candidate = raw_state
            self._stable_start_t = now

        hold_elapsed = max(0.0, now - self._stable_start_t)
        hold_target = max(0.001, float(self._confirm_hold_s))
        hold_confidence = max(0.0, min(1.0, hold_elapsed / hold_target))

        if is_grace_frame:
            self._stable_start_t = now
            # During grace period, only allow non-action gestures to prevent
            # ghost clicks from stale data.
            if self._state in {
                GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK, GestureType.KEYBOARD,
                GestureType.TASK_VIEW,
            }:
                self._state = GestureType.MOVE
            stable_state = self._state
            hold_confidence = 0.0
        else:
            if hold_elapsed >= hold_target:
                stable_state = self._candidate
            else:
                stable_state = self._state

        # Stamp left-click release on state exit, not on state entry.
        if self._state == GestureType.LEFT_CLICK and stable_state != GestureType.LEFT_CLICK:
            self._left_click_release_time = now

        if stable_state != self._state:
            self._gesture_entry_set.discard(self._state)

        if stable_state != GestureType.SCROLL and self._state != GestureType.SCROLL:
            self._clear_transient_motion()

        if stable_state != GestureType.DRAG:
            self._drag_active = False

        if stable_state == GestureType.LEFT_CLICK:
            if self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                if self._left_click_release_time > 0.0 and 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s and self._check_action_cooldown(GestureType.DOUBLE_CLICK, now):
                    self._last_double_click_time = now
                    self._last_click_time = now
                    self._locked_until = now + self._gesture_lock_s
                    self._state = GestureType.DOUBLE_CLICK
                    self._record_action(GestureType.DOUBLE_CLICK, now)
                    self._record_action(GestureType.LEFT_CLICK, now)
                    self._gesture_entry_set.add(GestureType.LEFT_CLICK)
                    self._gesture_entry_set.add(GestureType.DOUBLE_CLICK)
                    self._dragging = False
                    return self._make_result(GestureType.DOUBLE_CLICK, 0, 1.0)

                self._last_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.LEFT_CLICK
                self._record_action(GestureType.LEFT_CLICK, now)
                self._gesture_entry_set.add(GestureType.LEFT_CLICK)
                self._dragging = False
                return self._make_result(GestureType.LEFT_CLICK, 0, 1.0)

            self._state = GestureType.PAUSE
            self._dragging = False
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.RIGHT_CLICK:
            if self._check_action_cooldown(GestureType.RIGHT_CLICK, now):
                self._last_right_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.RIGHT_CLICK
                self._record_action(GestureType.RIGHT_CLICK, now)
                self._gesture_entry_set.add(GestureType.RIGHT_CLICK)
                self._dragging = False
                return self._make_result(GestureType.RIGHT_CLICK, 0, 1.0)

            self._state = GestureType.PAUSE
            self._dragging = False
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.DRAG:
            self._dragging = True
            self._drag_active = True
            self._state = GestureType.DRAG
            return self._make_result(GestureType.DRAG, 0, max(hold_confidence, 0.8))

        if stable_state == GestureType.SCROLL:
            delta = self._resolve_scroll(current_y=float(xy[8][1]), hand_scale=self._hand_scale)
            self._state = GestureType.SCROLL
            self._dragging = False
            return self._make_result(GestureType.SCROLL, delta, max(hold_confidence, 0.8))

        if stable_state == GestureType.KEYBOARD:
            self._state = GestureType.KEYBOARD
            self._gesture_entry_set.add(GestureType.KEYBOARD)
            self._dragging = False
            return self._make_result(GestureType.KEYBOARD, 0, 1.0)

        if stable_state == GestureType.TASK_VIEW:
            self._state = GestureType.TASK_VIEW
            self._gesture_entry_set.add(GestureType.TASK_VIEW)
            self._task_view_since = None
            self._dragging = False
            return self._make_result(GestureType.TASK_VIEW, 0, 1.0)

        if stable_state == GestureType.MEDIA_NEXT:
            edge = self._media_edge_state != GestureType.MEDIA_NEXT
            if edge and self._check_action_cooldown(GestureType.MEDIA_NEXT, now) and (now - self._last_media_action_time >= self._media_cooldown_s):
                self._last_media_next_time = now
                self._last_media_action_time = now
                self._record_action(GestureType.MEDIA_NEXT, now)
                self._gesture_entry_set.add(GestureType.MEDIA_NEXT)
                self._media_edge_state = GestureType.MEDIA_NEXT
                self._state = GestureType.MEDIA_NEXT
                return self._make_result(GestureType.MEDIA_NEXT, 1, 1.0)
            self._media_edge_state = GestureType.MEDIA_NEXT
            self._state = GestureType.PAUSE
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.MEDIA_PREV:
            edge = self._media_edge_state != GestureType.MEDIA_PREV
            if edge and self._check_action_cooldown(GestureType.MEDIA_PREV, now) and (now - self._last_media_action_time >= self._media_cooldown_s):
                self._last_media_prev_time = now
                self._last_media_action_time = now
                self._record_action(GestureType.MEDIA_PREV, now)
                self._gesture_entry_set.add(GestureType.MEDIA_PREV)
                self._media_edge_state = GestureType.MEDIA_PREV
                self._state = GestureType.MEDIA_PREV
                return self._make_result(GestureType.MEDIA_PREV, 1, 1.0)
            self._media_edge_state = GestureType.MEDIA_PREV
            self._state = GestureType.PAUSE
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.MEDIA_VOL_UP:
            if media_delta > 0 and self._check_action_cooldown(GestureType.MEDIA_VOL_UP, now):
                self._record_action(GestureType.MEDIA_VOL_UP, now)
                self._state = GestureType.MEDIA_VOL_UP
                self._media_edge_state = GestureType.PAUSE
                return self._make_result(GestureType.MEDIA_VOL_UP, abs(media_delta), 1.0)
            self._state = GestureType.PAUSE
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.MEDIA_VOL_DOWN:
            if media_delta < 0 and self._check_action_cooldown(GestureType.MEDIA_VOL_DOWN, now):
                self._record_action(GestureType.MEDIA_VOL_DOWN, now)
                self._state = GestureType.MEDIA_VOL_DOWN
                self._media_edge_state = GestureType.PAUSE
                return self._make_result(GestureType.MEDIA_VOL_DOWN, abs(media_delta), 1.0)
            self._state = GestureType.PAUSE
            return self._make_result(GestureType.PAUSE, 0, hold_confidence)

        if stable_state == GestureType.MOVE:
            if self._z_tap_triggered(hand_data, fs, now) and self._check_action_cooldown(GestureType.LEFT_CLICK, now):
                self._last_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.LEFT_CLICK
                self._record_action(GestureType.LEFT_CLICK, now)
                self._gesture_entry_set.add(GestureType.LEFT_CLICK)
                self._dragging = False
                return self._make_result(GestureType.LEFT_CLICK, 0, 1.0)

            self._state = GestureType.MOVE
            self._dragging = False
            self._media_edge_state = GestureType.PAUSE
            return self._make_result(GestureType.MOVE, 0, max(hold_confidence, 0.5))

        self._state = GestureType.PAUSE
        self._dragging = False
        self._media_edge_state = GestureType.PAUSE
        return self._make_result(GestureType.PAUSE, 0, hold_confidence)
