from __future__ import annotations

import math
import time

from .models import FingerStates, GestureResult, GestureType
from .tuning import (
    GESTURE_ACTION_COOLDOWN_S,
    GESTURE_CONFIRM_HOLD_S,
    GESTURE_DOUBLE_CLICK_WINDOW_S,
    GESTURE_DRAG_ACTIVATE_S,
    GESTURE_KEYBOARD_AFTER_PINCH_S,
    GESTURE_LOCK_S,
    GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S,
    GESTURE_SCROLL_GAIN,
    GESTURE_Z_TAP_ENTER,
    GESTURE_Z_TAP_EXIT,
)


class GestureDetector:
    def __init__(self) -> None:
        self._state = GestureType.PAUSE
        self._candidate = GestureType.PAUSE
        self._candidate_since = 0.0

        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_since: float | None = None
        self._last_pinch_release_time = 0.0

        self._scroll_prev_y: float | None = None
        self._scroll_velocity_ema = 0.0
        self._scroll_direction = 0
        self._scroll_last_switch_time = 0.0
        self._left_media_anchor_y: float | None = None

        self._action_cooldown_s = GESTURE_ACTION_COOLDOWN_S
        self._gesture_lock_s = GESTURE_LOCK_S
        self._locked_until = 0.0
        self._drag_activate_s = GESTURE_DRAG_ACTIVATE_S

        # Compatibility with existing settings bindings.
        self._pinch_enter = 0.18
        self._pinch_exit = 0.32
        self._confirm_hold_s = 0.08
        self._media_cooldown_s = 0.5
        self._last_media_action_time = 0.0
        self._media_edge_state = GestureType.PAUSE
        self._hand_scale = 24.0

        self._last_click_time = 0.0
        self._last_right_click_time = 0.0
        self._last_media_next_time = 0.0
        self._last_media_prev_time = 0.0
        self._last_double_click_time = 0.0
        self._left_click_release_time = 0.0
        self._task_view_since: float | None = None

        self._scroll_step_factor = 0.12
        self._scroll_deadband_factor = 0.06
        self._media_step_factor = 0.11
        self._media_deadband_factor = 0.05
        self._double_click_window_s = GESTURE_DOUBLE_CLICK_WINDOW_S
        self._scroll_gain = int(GESTURE_SCROLL_GAIN)
        self._z_tap_enter = float(GESTURE_Z_TAP_ENTER)
        self._z_tap_exit = float(GESTURE_Z_TAP_EXIT)
        self._z_tap_active = False
        self._z_tap_enabled = False
        self._task_view_hold_s = 0.40
        self._keyboard_after_pinch_s = float(GESTURE_KEYBOARD_AFTER_PINCH_S)
        self._scroll_dir_switch_cooldown_s = float(GESTURE_SCROLL_DIR_SWITCH_COOLDOWN_S)
        self._scroll_step_limit = 4

    @property
    def dragging(self) -> bool:
        return self._dragging

    @staticmethod
    def _distance(a, b) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def _finger_states(landmarks_xy) -> FingerStates:
        thumb_tip = landmarks_xy[4]
        thumb_ip = landmarks_xy[3]
        index_mcp = landmarks_xy[5]

        dx_tip = thumb_tip[0] - index_mcp[0]
        dy_tip = thumb_tip[1] - index_mcp[1]
        dx_ip = thumb_ip[0] - index_mcp[0]
        dy_ip = thumb_ip[1] - index_mcp[1]
        thumb = (dx_tip * dx_tip + dy_tip * dy_tip) > (dx_ip * dx_ip + dy_ip * dy_ip)

        index = landmarks_xy[8][1] < landmarks_xy[6][1]
        middle = landmarks_xy[12][1] < landmarks_xy[10][1]
        ring = landmarks_xy[16][1] < landmarks_xy[14][1]
        pinky = landmarks_xy[20][1] < landmarks_xy[18][1]
        return FingerStates(thumb, index, middle, ring, pinky)

    @staticmethod
    def finger_count(hand_data: dict | None) -> int:
        if not hand_data:
            return 0
        fs = GestureDetector._finger_states(hand_data["xy"])
        return int(fs.thumb) + int(fs.index) + int(fs.middle) + int(fs.ring) + int(fs.pinky)

    def _update_pinch_states(self, xy, fs: FingerStates, hand_scale: float) -> None:
        pinch_enter_factor = max(0.08, float(self._pinch_enter))
        pinch_exit_factor = max(pinch_enter_factor + 0.05, float(self._pinch_exit))
        self._pinch_enter = pinch_enter_factor
        self._pinch_exit = pinch_exit_factor

        pinch_enter = hand_scale * pinch_enter_factor
        pinch_exit = hand_scale * pinch_exit_factor

        left_dist = self._distance(xy[4], xy[8])
        right_dist = self._distance(xy[4], xy[12])

        left_click_pose = left_dist <= pinch_enter and right_dist > pinch_exit
        right_click_pose = right_dist <= pinch_enter and left_dist > pinch_exit

        if self._left_pinch_active:
            if left_dist > pinch_exit:
                self._left_pinch_active = False
        elif left_click_pose:
            self._left_pinch_active = True

        if self._right_pinch_active:
            if right_dist > pinch_exit:
                self._right_pinch_active = False
        elif right_click_pose:
            self._right_pinch_active = True

    def _stable_state(self, raw_state: GestureType, now: float) -> GestureType:
        if raw_state == GestureType.PAUSE:
            self._candidate = GestureType.PAUSE
            self._candidate_since = now
            return GestureType.PAUSE

        if raw_state != self._candidate:
            self._candidate = raw_state
            self._candidate_since = now
            return self._state

        if now - self._candidate_since >= self._confirm_hold_s:
            return self._candidate
        return self._state

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

    def _resolve_media_volume(self, current_y: float, hand_scale: float) -> int:
        if self._left_media_anchor_y is None:
            self._left_media_anchor_y = current_y
            return 0

        delta = self._left_media_anchor_y - current_y
        deadband = hand_scale * self._media_deadband_factor
        if abs(delta) <= deadband:
            return 0

        step = max(1.0, hand_scale * self._media_step_factor)
        steps = int(delta / step)
        if steps == 0:
            return 0

        self._left_media_anchor_y -= steps * step
        return steps

    def detect(self, hand_data) -> GestureResult:
        now = time.monotonic()

        if not hand_data:
            self._state = GestureType.PAUSE
            self._candidate = GestureType.PAUSE
            self._candidate_since = now
            self._dragging = False
            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_since = None
            self._scroll_prev_y = None
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0
            self._left_media_anchor_y = None
            self._z_tap_active = False
            self._task_view_since = None
            self._media_edge_state = GestureType.PAUSE
            return GestureResult(GestureType.PAUSE, 0)

        xy = hand_data["xy"]
        fs = self._finger_states(xy)
        hand_label = str(hand_data.get("label", "Right"))

        # Confidence gate — if hand detection is weak, return PAUSE immediately.
        confidence = float(hand_data.get("confidence", 0.0))
        if confidence < 0.6:
            self._state = GestureType.PAUSE
            return GestureResult(GestureType.PAUSE, 0)

        wrist = xy[0]
        middle_mcp = xy[9]
        self._hand_scale = max(24.0, self._distance(wrist, middle_mcp))

        print(f"[GESTURE] Hand={hand_label} State={self._state} Scale={self._hand_scale:.3f}")

        prev_left_pinch_active = self._left_pinch_active
        self._update_pinch_states(xy, fs, self._hand_scale)
        if prev_left_pinch_active and not self._left_pinch_active:
            self._left_click_release_time = now
        pinch_guard_active = (
            self._left_pinch_active
            or self._right_pinch_active
            or (now - self._last_pinch_release_time < self._keyboard_after_pinch_s)
        )

        if not self._left_pinch_active and not self._right_pinch_active:
            if self._left_pinch_since is not None:
                self._last_pinch_release_time = now

        if self._left_pinch_active:
            if self._left_pinch_since is None:
                self._left_pinch_since = now
        else:
            self._left_pinch_since = None

        move_pose = fs.index and (not fs.middle) and (not fs.ring) and (not fs.pinky)
        scroll_pose = fs.index and fs.middle and (not fs.ring) and (not fs.pinky)
        task_view_pose = fs.index and fs.middle and fs.ring and fs.pinky and fs.thumb
        keyboard_pose = fs.thumb and fs.index and fs.pinky and (not fs.middle) and (not fs.ring)

        if hand_label == "Left":
            self._dragging = False
            self._scroll_prev_y = None
            self._scroll_velocity_ema = 0.0

            confidence = float(hand_data.get("confidence", 0.0))
            if confidence < 0.6:
                self._left_media_anchor_y = None
                self._state = GestureType.PAUSE
                return GestureResult(GestureType.PAUSE, 0)

            left_dist = self._distance(xy[4], xy[8])
            right_dist = self._distance(xy[4], xy[12])
            strong_pinch_enter = self._hand_scale * max(0.06, self._pinch_enter * 0.75)
            strong_left_pinch = left_dist <= strong_pinch_enter and right_dist > (self._hand_scale * self._pinch_exit)
            strong_right_pinch = right_dist <= strong_pinch_enter and left_dist > (self._hand_scale * self._pinch_exit)

            raw_media = GestureType.PAUSE
            if scroll_pose and (not self._left_pinch_active) and (not self._right_pinch_active):
                vol_delta = self._resolve_media_volume(current_y=float(xy[8][1]), hand_scale=self._hand_scale)
                if vol_delta > 0:
                    raw_media = GestureType.MEDIA_VOL_UP
                elif vol_delta < 0:
                    raw_media = GestureType.MEDIA_VOL_DOWN
                else:
                    raw_media = GestureType.PAUSE
            else:
                self._left_media_anchor_y = None
                if self._left_pinch_active and (not self._right_pinch_active) and strong_left_pinch:
                    raw_media = GestureType.MEDIA_NEXT
                elif self._right_pinch_active and (not self._left_pinch_active) and strong_right_pinch:
                    raw_media = GestureType.MEDIA_PREV

            if raw_media in {GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN}:
                stable_media = raw_media
            else:
                stable_media = self._stable_state(raw_media, now)

            if stable_media == GestureType.MEDIA_NEXT:
                edge = self._media_edge_state != GestureType.MEDIA_NEXT
                if edge and now - self._last_media_next_time >= self._action_cooldown_s and now - self._last_media_action_time >= self._media_cooldown_s:
                    self._last_media_next_time = now
                    self._last_media_action_time = now
                    self._media_edge_state = GestureType.MEDIA_NEXT
                    self._state = GestureType.MEDIA_NEXT
                    return GestureResult(GestureType.MEDIA_NEXT, 1)
                self._media_edge_state = GestureType.MEDIA_NEXT
                self._state = GestureType.PAUSE
                return GestureResult(GestureType.PAUSE, 0)

            if stable_media == GestureType.MEDIA_PREV:
                edge = self._media_edge_state != GestureType.MEDIA_PREV
                if edge and now - self._last_media_prev_time >= self._action_cooldown_s and now - self._last_media_action_time >= self._media_cooldown_s:
                    self._last_media_prev_time = now
                    self._last_media_action_time = now
                    self._media_edge_state = GestureType.MEDIA_PREV
                    self._state = GestureType.MEDIA_PREV
                    return GestureResult(GestureType.MEDIA_PREV, 1)
                self._media_edge_state = GestureType.MEDIA_PREV
                self._state = GestureType.PAUSE
                return GestureResult(GestureType.PAUSE, 0)

            if stable_media == GestureType.MEDIA_VOL_UP:
                if now - self._last_media_next_time < self._action_cooldown_s:
                    self._state = GestureType.PAUSE
                    return GestureResult(GestureType.PAUSE, 0)
                self._last_media_next_time = now
                self._last_media_action_time = now
                self._media_edge_state = GestureType.PAUSE
                self._state = GestureType.MEDIA_VOL_UP
                return GestureResult(GestureType.MEDIA_VOL_UP, 1)

            if stable_media == GestureType.MEDIA_VOL_DOWN:
                if now - self._last_media_prev_time < self._action_cooldown_s:
                    self._state = GestureType.PAUSE
                    return GestureResult(GestureType.PAUSE, 0)
                self._last_media_prev_time = now
                self._last_media_action_time = now
                self._media_edge_state = GestureType.PAUSE
                self._state = GestureType.MEDIA_VOL_DOWN
                return GestureResult(GestureType.MEDIA_VOL_DOWN, 1)

            self._media_edge_state = GestureType.PAUSE
            self._state = GestureType.PAUSE
            return GestureResult(GestureType.PAUSE, 0)

        self._left_media_anchor_y = None

        if task_view_pose and not self._left_pinch_active and not self._right_pinch_active:
            if self._task_view_since is None:
                self._task_view_since = now
        else:
            self._task_view_since = None

        raw_state = GestureType.PAUSE
        if (
            self._task_view_since is not None
            and task_view_pose
            and (now - self._task_view_since >= self._task_view_hold_s)
            and not self._left_pinch_active
            and not self._right_pinch_active
        ):
            raw_state = GestureType.TASK_VIEW
        elif keyboard_pose and not pinch_guard_active:
            raw_state = GestureType.KEYBOARD
        elif self._left_pinch_active and self._left_pinch_since is not None and (now - self._left_pinch_since >= self._drag_activate_s):
            raw_state = GestureType.DRAG
        elif self._left_pinch_active and not self._right_pinch_active:
            raw_state = GestureType.LEFT_CLICK
        elif self._right_pinch_active and not self._left_pinch_active:
            raw_state = GestureType.RIGHT_CLICK
        elif scroll_pose and not self._left_pinch_active and not self._right_pinch_active:
            raw_state = GestureType.SCROLL
        elif move_pose:
            raw_state = GestureType.MOVE

        stable_state = self._stable_state(raw_state, now)

        if stable_state != GestureType.SCROLL and raw_state != GestureType.SCROLL:
            self._scroll_prev_y = None
            self._scroll_velocity_ema = 0.0
            self._scroll_direction = 0

        if self._state == GestureType.LEFT_CLICK and stable_state != GestureType.LEFT_CLICK:
            self._left_click_release_time = now

        if (
            now < self._locked_until
            and self._state in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DOUBLE_CLICK}
            and stable_state not in {GestureType.LEFT_CLICK, GestureType.DRAG}
        ):
            return GestureResult(GestureType.MOVE, 0)

        if stable_state == GestureType.LEFT_CLICK:
            if now - self._last_click_time >= self._action_cooldown_s:
                if 0.0 < (now - self._left_click_release_time) <= self._double_click_window_s:
                    self._last_double_click_time = now
                    self._last_click_time = now
                    self._locked_until = now + self._gesture_lock_s
                    self._state = GestureType.DOUBLE_CLICK
                    return GestureResult(GestureType.DOUBLE_CLICK, 0)
                self._last_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.LEFT_CLICK
                return GestureResult(GestureType.LEFT_CLICK, 0)
            self._state = GestureType.MOVE
            return GestureResult(GestureType.MOVE, 0)

        if stable_state == GestureType.RIGHT_CLICK:
            if now - self._last_right_click_time >= self._action_cooldown_s:
                self._last_right_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.RIGHT_CLICK
                return GestureResult(GestureType.RIGHT_CLICK, 0)
            self._state = GestureType.MOVE
            return GestureResult(GestureType.MOVE, 0)

        if stable_state == GestureType.TASK_VIEW:
            self._state = GestureType.TASK_VIEW
            self._task_view_since = None
            return GestureResult(GestureType.TASK_VIEW, 0)

        if stable_state == GestureType.KEYBOARD:
            if pinch_guard_active:
                self._state = GestureType.MOVE
                return GestureResult(GestureType.MOVE, 0)
            self._state = GestureType.KEYBOARD
            return GestureResult(GestureType.KEYBOARD, 0)

        if stable_state == GestureType.DRAG:
            self._dragging = True
            self._state = GestureType.DRAG
            return GestureResult(GestureType.DRAG, 0)

        self._dragging = False

        if stable_state == GestureType.SCROLL:
            scroll_delta = self._resolve_scroll(current_y=float(xy[8][1]), hand_scale=self._hand_scale)
            self._state = GestureType.SCROLL
            return GestureResult(GestureType.SCROLL, scroll_delta)

        if stable_state == GestureType.MOVE:
            if self._z_tap_triggered(hand_data, fs, now):
                self._last_click_time = now
                self._locked_until = now + self._gesture_lock_s
                self._state = GestureType.LEFT_CLICK
                return GestureResult(GestureType.LEFT_CLICK, 0)
            self._state = GestureType.MOVE
            return GestureResult(GestureType.MOVE, 0)

        self._state = GestureType.PAUSE
        return GestureResult(GestureType.PAUSE, 0)
