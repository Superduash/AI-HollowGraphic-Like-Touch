import math
import time

from .models import FingerStates, GestureResult, GestureType


class GestureEngine:
    def __init__(self) -> None:
        self._candidate = GestureType.NONE
        self._candidate_frames = 0
        self._confirmed = GestureType.NONE
        self._dragging = False

        self._confirm_required = 4

        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0
        self._right_pose_frames = 0
        self._left_click_fired = False
        self._right_click_fired = False

        self._last_left = 0.0
        self._last_right = 0.0
        self._last_task_view = 0.0
        self._task_view_frames = 0
        self._task_view_anchor = (0, 0)
        self._last_media_track = 0.0

        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        self._pinch_enter = 0.20
        self._pinch_exit = 0.28
        self._right_pinch_enter_factor = 0.86
        self._right_click_pose_frames = 2
        self._right_click_pinch_frames = 2
        self._scroll_motion_threshold = 3.0
        self._task_view_cooldown = 1.0
        self._task_view_confirm_frames = 6
        self._click_cooldown = 0.25

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
        # Thumb: orientation-independent (same as repo main app)
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
        # Require all fingers extended AND a wide finger spread to prevent
        # Task View triggering from partial/rotated hands.
        if not (fs.thumb and fs.index and fs.middle and fs.ring and fs.pinky):
            return False

        try:
            wrist_y = xy[0][1]
            # Fingertips should be above the wrist.
            if not (xy[8][1] < wrist_y and xy[12][1] < wrist_y and xy[16][1] < wrist_y and xy[20][1] < wrist_y):
                return False

            spread = self._distance(xy[8], xy[20])  # index tip to pinky tip
            thumb_sep = self._distance(xy[4], xy[5])  # thumb tip to index MCP

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
            self._candidate_frames = 0
            self._dragging = False

            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_start = 0.0
            self._left_pinch_frames = 0
            self._right_pinch_frames = 0
            self._right_pose_frames = 0
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

        # Hand scale used for robust open-palm checks too.
        hand_scale = max(40.0, self._distance(xy[5], xy[17]))

        # Open palm: Task View.
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
            else:
                if self._distance(xy[0], self._task_view_anchor) > 25.0:
                    self._task_view_anchor = xy[0]
                    self._task_view_frames = 0

            self._task_view_frames += 1
            if self._task_view_frames >= self._task_view_confirm_frames and now - self._last_task_view >= self._task_view_cooldown:
                self._last_task_view = now
                self._task_view_frames = 0
                return self._confirm(GestureType.TASK_VIEW, 0, edge_trigger=True)

            # Hold open palm without triggering anything.
            return self._confirm(GestureType.PAUSE, 0)
        else:
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
        else:
            if self._left_pinch_active:
                if left_dist > exit_:
                    self._left_pinch_active = False
            else:
                if left_dist < enter:
                    self._left_pinch_active = True

        right_click_pose = (not fs.index) and (not fs.ring) and (not fs.pinky)
        if right_click_pose:
            self._right_pose_frames += 1
        else:
            self._right_pose_frames = 0

        if not fs.middle:
            self._right_pinch_active = False
        else:
            if self._right_pinch_active:
                if right_dist > exit_ or not right_click_pose:
                    self._right_pinch_active = False
            else:
                if right_click_pose and right_dist < right_enter:
                    self._right_pinch_active = True

        # Left hand dominance logic
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
                        else:
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
                        return self._confirm(GestureType.MEDIA_PREV, 0, edge_trigger=True)
                    else:
                        return self._confirm(GestureType.MEDIA_NEXT, 0, edge_trigger=True)
                return self._confirm(GestureType.PAUSE, 0)

            self._prev_scroll_y = None
            return self._confirm(GestureType.PAUSE, 0)


        # Right click: thumb + middle pinch.
        if self._right_pinch_active and not self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._right_pinch_frames += 1
            if (
                not self._right_click_fired
                and self._right_pose_frames >= self._right_click_pose_frames
                and self._right_pinch_frames >= self._right_click_pinch_frames
                and now - self._last_right >= self._click_cooldown
            ):
                self._right_click_fired = True
                self._last_right = now
                return self._confirm(GestureType.RIGHT_CLICK, 0, edge_trigger=True)
            return self._confirm(GestureType.MOVE, 0)
        if not self._right_pinch_active:
            self._right_pinch_frames = 0
            self._right_click_fired = False

        # Left click/drag: thumb + index pinch.
        if self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._left_pinch_frames += 1
            if (
                not self._left_click_fired
                and self._left_pinch_frames >= 1
                and now - self._last_left >= self._click_cooldown
            ):
                self._left_click_fired = True
                self._last_left = now
                self._left_pinch_start = now
                return self._confirm(GestureType.LEFT_CLICK, 0, edge_trigger=True)

            if self._left_pinch_start == 0.0:
                self._left_pinch_start = now

            if now - self._left_pinch_start >= 0.30:
                self._dragging = True
                return self._confirm(GestureType.DRAG, 0, edge_trigger=True)

            return self._confirm(GestureType.MOVE, 0)

        # Pinch released.
        self._left_pinch_frames = 0
        self._left_click_fired = False
        self._left_pinch_start = 0.0
        self._dragging = False

        # Scroll: peace sign + vertical motion.
        if fs.index and fs.middle and not fs.ring and not fs.pinky:
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
        
        # Keyboard toggle: Three fingers up.
        if (not fs.thumb) and fs.index and fs.middle and fs.ring and not fs.pinky:
            return self._confirm(GestureType.KEYBOARD, 0, edge_trigger=True)

        # Move: index finger only.
        if fs.index and not fs.middle and not fs.ring and not fs.pinky:
            return self._confirm(GestureType.MOVE, 0)

        return self._confirm(GestureType.PAUSE, 0)

    def _confirm(self, raw: GestureType, scroll_delta: int, edge_trigger: bool = False) -> GestureResult:
        if raw == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = raw
            self._candidate_frames = 1

        if raw in {GestureType.PAUSE, GestureType.SCROLL, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN}:
            self._confirmed = raw
        elif edge_trigger:
            self._confirmed = raw
        else:
            if self._confirmed == GestureType.NONE and raw != GestureType.NONE:
                self._confirmed = raw
            elif self._candidate_frames >= self._confirm_required:
                self._confirmed = raw

        if self._confirmed in {GestureType.SCROLL, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN}:
            return GestureResult(self._confirmed, scroll_delta)
        return GestureResult(self._confirmed, 0)
