from __future__ import annotations

import math
import time

from .models import FingerStates, GestureResult, GestureType


class GestureDetector:
    def __init__(self) -> None:
        self._candidate = GestureType.NONE
        self._candidate_since = 0.0
        self._confirmed = GestureType.NONE
        self._prev_confirmed = GestureType.NONE  # for drag-release lockout
        self._drag_release_time = 0.0             # timestamp of last DRAG→non-DRAG

        self._dragging = False
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0

        self._last_left = 0.0
        self._last_right = 0.0
        self._last_task_view = 0.0
        self._last_media_track = 0.0

        self._task_view_frames = 0
        self._task_view_anchor = (0, 0)
        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        self._left_click_fired = False
        self._right_click_fired = False
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0

        self._pinch_enter = 0.20
        self._pinch_exit = 0.28
        self._right_pinch_enter_factor = 0.86
        self._scroll_motion_threshold = 3.0
        self._task_view_cooldown = 1.0
        self._task_view_confirm_frames = 6
        self._click_cooldown = 0.25
        self._confirm_hold_s = 0.22               # was 0.15
        self._drag_confirm_frames = 8              # NEW – consecutive left-pinch frames before drag
        self._right_pinch_min_frames = 4           # NEW – was 2
        self._drag_release_lockout_s = 0.15        # NEW – 150 ms post-drag lockout

        self.debug = False                         # NEW – print gesture transitions

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
        tt = landmarks_xy[4]
        ti = landmarks_xy[3]
        im = landmarks_xy[5]
        dx1, dy1 = tt[0] - im[0], tt[1] - im[1]
        dx2, dy2 = ti[0] - im[0], ti[1] - im[1]
        thumb = (dx1 * dx1 + dy1 * dy1) > (dx2 * dx2 + dy2 * dy2)
        index = landmarks_xy[8][1] < landmarks_xy[6][1]
        middle = landmarks_xy[12][1] < landmarks_xy[10][1]
        ring = landmarks_xy[16][1] < landmarks_xy[14][1]
        pinky = landmarks_xy[20][1] < landmarks_xy[18][1]
        return FingerStates(thumb, index, middle, ring, pinky)

    def _is_open_palm(self, xy, fs: FingerStates, hand_scale: float) -> bool:
        if not (fs.thumb and fs.index and fs.middle and fs.ring and fs.pinky):
            return False

        try:
            wrist_y = xy[0][1]
            if not (xy[8][1] < wrist_y and xy[12][1] < wrist_y and xy[16][1] < wrist_y and xy[20][1] < wrist_y):
                return False

            spread = self._distance(xy[8], xy[20])
            thumb_sep = self._distance(xy[4], xy[5])
            if spread < hand_scale * 0.85:
                return False
            if thumb_sep < hand_scale * 0.35:
                return False
            return True
        except Exception:
            return False

    def detect(self, hand_data) -> GestureResult:
        if not hand_data:
            self._confirmed = GestureType.NONE
            self._candidate = GestureType.NONE
            self._candidate_since = 0.0
            self._dragging = False

            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_start = 0.0
            self._left_pinch_frames = 0
            self._right_pinch_frames = 0
            self._left_click_fired = False
            self._right_click_fired = False

            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._task_view_frames = 0
            return GestureResult(GestureType.PAUSE)

        xy = hand_data["xy"]
        label = hand_data.get("label", "Right")
        now = time.monotonic()
        fs = self._finger_states(xy)
        hand_scale = max(40.0, self._distance(xy[5], xy[17]))

        if self._is_open_palm(xy, fs, hand_scale):
            self._dragging = False
            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_start = 0.0
            self._left_pinch_frames = 0
            self._right_pinch_frames = 0
            self._left_click_fired = False
            self._right_click_fired = False
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0

            if self._task_view_frames == 0:
                self._task_view_anchor = xy[0]
            elif self._distance(xy[0], self._task_view_anchor) > 25.0:
                self._task_view_anchor = xy[0]
                self._task_view_frames = 0

            self._task_view_frames += 1
            if self._task_view_frames >= self._task_view_confirm_frames and now - self._last_task_view >= self._task_view_cooldown:
                self._last_task_view = now
                self._task_view_frames = 0
                return self._confirm(GestureType.TASK_VIEW, 0)

            return self._confirm(GestureType.PAUSE, 0)

        self._task_view_frames = 0

        thumb = xy[4]
        index_tip = xy[8]
        middle_tip = xy[12]

        enter = max(12.0, min(42.0, hand_scale * self._pinch_enter))
        exit_ = max(enter + 2.0, min(58.0, hand_scale * self._pinch_exit))
        right_enter = max(10.0, enter * self._right_pinch_enter_factor)

        left_dist = self._distance(thumb, index_tip)
        right_dist = self._distance(thumb, middle_tip)

        if not fs.index:
            self._left_pinch_active = False
        elif self._left_pinch_active:
            if left_dist > exit_:
                self._left_pinch_active = False
        elif left_dist < enter:
            self._left_pinch_active = True

        # Right-click relaxed rule: middle finger down is required,
        # index state is ignored.
        right_click_pose = fs.middle and (not fs.ring) and (not fs.pinky)
        if not fs.middle:
            self._right_pinch_active = False
        elif self._right_pinch_active:
            if right_dist > exit_ or not right_click_pose:
                self._right_pinch_active = False
        elif right_click_pose and right_dist < right_enter:
            self._right_pinch_active = True

        # Left hand controls only media volume and track skip.
        if label == "Left":
            if self._left_pinch_active:
                self._left_pinch_frames += 1
                if self._left_pinch_frames >= 2:
                    y = xy[4][1]
                    if self._prev_scroll_y is None:
                        self._prev_scroll_y = y
                        return self._confirm(GestureType.PAUSE, 0)
                    dy = y - self._prev_scroll_y
                    if abs(dy) > self._scroll_motion_threshold:
                        self._prev_scroll_y = y
                        raw = int(abs(dy) - self._scroll_motion_threshold)
                        if dy < 0:
                            return self._confirm(GestureType.MEDIA_VOL_UP, raw)
                        return self._confirm(GestureType.MEDIA_VOL_DOWN, raw)
                return self._confirm(GestureType.PAUSE, 0)

            if fs.index and fs.middle and not fs.ring and not fs.pinky:
                y = 0.5 * (xy[8][1] + xy[12][1])
                if self._prev_scroll_y is None:
                    self._prev_scroll_y = y
                    return self._confirm(GestureType.PAUSE, 0)
                dy = y - self._prev_scroll_y
                if abs(dy) > 30.0 and now - self._last_media_track >= 0.8:
                    self._prev_scroll_y = y
                    self._last_media_track = now
                    if dy < 0:
                        return self._confirm(GestureType.MEDIA_PREV, 0)
                    return self._confirm(GestureType.MEDIA_NEXT, 0)
                return self._confirm(GestureType.PAUSE, 0)

            self._prev_scroll_y = None
            return self._confirm(GestureType.PAUSE, 0)

        if self._right_pinch_active and not self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._right_pinch_frames += 1
            if not self._right_click_fired and self._right_pinch_frames >= self._right_pinch_min_frames and now - self._last_right >= self._click_cooldown:
                self._right_click_fired = True
                self._last_right = now
                return self._confirm(GestureType.RIGHT_CLICK, 0)
            return self._confirm(GestureType.MOVE, 0)

        if not self._right_pinch_active:
            self._right_pinch_frames = 0
            self._right_click_fired = False

        if self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._left_pinch_frames += 1

            if not self._left_click_fired and now - self._last_left >= self._click_cooldown:
                self._left_click_fired = True
                self._last_left = now
                self._left_pinch_start = now
                return self._confirm(GestureType.LEFT_CLICK, 0)

            if self._left_pinch_start == 0.0:
                self._left_pinch_start = now

            if now - self._left_pinch_start >= 0.30 and self._left_pinch_frames >= self._drag_confirm_frames:
                self._dragging = True
                return self._confirm(GestureType.DRAG, 0)

            return self._confirm(GestureType.MOVE, 0)

        self._left_pinch_frames = 0
        self._left_click_fired = False
        self._left_pinch_start = 0.0
        self._dragging = False

        # Scroll: only when neither pinch is active
        if fs.index and fs.middle and not fs.ring and not fs.pinky:
            if not self._left_pinch_active and not self._right_pinch_active:
                y = 0.5 * (xy[8][1] + xy[12][1])
                if self._prev_scroll_y is None:
                    self._prev_scroll_y = y
                    return self._confirm(GestureType.SCROLL, 0)

                dy = y - self._prev_scroll_y
                self._prev_scroll_y = y
                if abs(dy) < self._scroll_motion_threshold:
                    return self._confirm(GestureType.SCROLL, 0)

                raw = -dy * 2.0
                self._smooth_scroll = 0.6 * self._smooth_scroll + 0.4 * raw
                return self._confirm(GestureType.SCROLL, int(self._smooth_scroll))

        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        # KEYBOARD: thumb + index + pinky up.
        if fs.thumb and fs.index and fs.pinky and not fs.middle and not fs.ring:
            return self._confirm(GestureType.KEYBOARD, 0)

        if fs.index and not fs.middle and not fs.ring and not fs.pinky:
            return self._confirm(GestureType.MOVE, 0)

        return self._confirm(GestureType.PAUSE, 0)

    def _confirm(self, raw: GestureType, scroll_delta: int) -> GestureResult:
        now = time.monotonic()
        if raw == self._candidate:
            held = now - self._candidate_since
        else:
            self._candidate = raw
            self._candidate_since = now
            held = 0.0

        # Drag-release lockout: after leaving DRAG, block new gestures for 150 ms
        if self._prev_confirmed == GestureType.DRAG and raw != GestureType.DRAG:
            if self._drag_release_time == 0.0:
                self._drag_release_time = now
            if now - self._drag_release_time < self._drag_release_lockout_s:
                return GestureResult(GestureType.MOVE, 0)
        else:
            self._drag_release_time = 0.0

        if raw in {GestureType.PAUSE, GestureType.MOVE}:
            self._set_confirmed(raw)
        elif held >= self._confirm_hold_s:
            self._set_confirmed(raw)
        elif raw in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DRAG}:
            return GestureResult(GestureType.MOVE, 0)
        else:
            return GestureResult(GestureType.PAUSE, 0)

        if self._confirmed in {GestureType.SCROLL, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN}:
            return GestureResult(self._confirmed, scroll_delta)
        return GestureResult(self._confirmed, 0)

    def _set_confirmed(self, gesture: GestureType) -> None:
        """Update _confirmed and track transitions for debug logging."""
        old = self._confirmed
        self._prev_confirmed = old
        self._confirmed = gesture
        if self.debug and old != gesture:
            print(f"[GESTURE] {old.name} \u2192 {gesture.name}")