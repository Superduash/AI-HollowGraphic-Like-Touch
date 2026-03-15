"""Gesture detector implementing pinch + finger-shape gestures.

Gestures (as requested):
- Index finger only extended: MOVE
- Thumb+index pinch: LEFT_CLICK (edge-trigger)
- Thumb+index pinch hold: DRAG (while held)
- Thumb+middle pinch: RIGHT_CLICK (edge-trigger)
- Peace sign (index+middle extended): SCROLL (vertical motion)
- Open palm: TASK_VIEW (edge-trigger)
- Closed fist: PAUSE

Designed to be stable and responsive: hysteresis for pinches + confirmation
for mode-like gestures to avoid rapid switching frame-to-frame.
"""

import time

from config import CLICK_COOLDOWN, DRAG_HOLD_TIME, SCROLL_SENSITIVITY
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_finger_states

_WRIST = 0
_THUMB_TIP = 4
_INDEX_MCP = 5
_INDEX_TIP = 8
_MIDDLE_TIP = 12
_PINKY_MCP = 17


class GestureResult:
    """Output of gesture detection for one frame."""

    __slots__ = ("gesture", "scroll_delta")

    def __init__(self, gesture: GestureType = GestureType.NONE, scroll_delta: int = 0) -> None:
        self.gesture = gesture
        self.scroll_delta = scroll_delta


class GestureDetector:
    """Stable gesture detector for pinch + finger-shape interactions."""

    def __init__(self) -> None:
        self._confirm_frames_required: int = 3
        self._candidate_gesture: GestureType = GestureType.NONE
        self._candidate_frames: int = 0
        self._confirmed_gesture: GestureType = GestureType.NONE

        self._is_dragging = False

        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0
        self._right_pose_frames = 0
        self._left_click_fired = False
        self._right_click_fired = False

        self._last_left_click = 0.0
        self._last_right_click = 0.0
        self._last_task_view = 0.0

        self._task_view_frames = 0

        self._scroll_active = False
        self._prev_scroll_y: float | None = None
        self._smooth_scroll: float = 0.0

        # Scale-invariant thresholds (fraction of hand scale).
        # Slightly more sensitive than before for easier real-world pinching.
        self._pinch_enter = 0.23
        self._pinch_exit = 0.30
        self._right_pinch_enter_factor = 0.86
        self._right_click_pose_frames = 2
        self._right_click_pinch_frames = 2
        self._scroll_motion_threshold = 3.0
        self._task_view_cooldown = 1.0
        self._task_view_confirm_frames = 6

    def _is_open_palm(self, xy: list[tuple[int, int]], fingers, hand_scale: float) -> bool:
        # Require all fingers extended and a wide finger spread to prevent
        # accidental Task View when the hand is rotated or only partially open.
        if not (fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky):
            return False

        try:
            wrist_y = xy[_WRIST][1]
            if not (xy[_INDEX_TIP][1] < wrist_y and xy[_MIDDLE_TIP][1] < wrist_y and xy[16][1] < wrist_y and xy[20][1] < wrist_y):
                return False
            spread = self._dist(xy[_INDEX_TIP], xy[20])
            thumb_sep = self._dist(xy[_THUMB_TIP], xy[_INDEX_MCP])
            if spread < hand_scale * 0.85:
                return False
            if thumb_sep < hand_scale * 0.35:
                return False
            return True
        except Exception:
            return False

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    def set_confirm_frames(self, frames: int) -> None:
        self._confirm_frames_required = max(1, int(frames))

    def detect(self, hand_data) -> GestureResult:
        if not hand_data:
            self._reset_temporal()
            return self._confirm_result(GestureType.PAUSE)

        landmarks_xy, z_values = self._extract_hand_data(hand_data)
        if not landmarks_xy or len(landmarks_xy) < 21:
            self._reset_temporal()
            return self._confirm_result(GestureType.PAUSE)

        # Ignore z: requested gestures are 2D geometry + finger-shape based.
        now = time.monotonic()
        fingers = get_finger_states(landmarks_xy)
        hand_scale = self._hand_scale(landmarks_xy)

        # Open palm: Task View (edge-trigger action).
        if self._is_open_palm(landmarks_xy, fingers, hand_scale):
            self._reset_non_pause_modes()
            self._task_view_frames += 1
            if self._task_view_frames >= self._task_view_confirm_frames and now - self._last_task_view >= self._task_view_cooldown:
                self._last_task_view = now
                self._task_view_frames = 0
                return self._confirm_result(GestureType.TASK_VIEW)
            return self._confirm_result(GestureType.PAUSE)
        else:
            self._task_view_frames = 0

        thumb = landmarks_xy[_THUMB_TIP]
        index_tip = landmarks_xy[_INDEX_TIP]
        middle_tip = landmarks_xy[_MIDDLE_TIP]

        left_dist = self._dist(thumb, index_tip)
        right_dist = self._dist(thumb, middle_tip)

        # Clamp thresholds to be robust across camera resolutions.
        left_enter = max(12.0, min(42.0, hand_scale * self._pinch_enter))
        left_exit = max(left_enter + 2.0, min(58.0, hand_scale * self._pinch_exit))
        right_enter = max(10.0, left_enter * self._right_pinch_enter_factor)
        right_exit = left_exit

        # Update pinch states with hysteresis.
        if self._left_pinch_active:
            if left_dist > left_exit:
                self._left_pinch_active = False
        else:
            if left_dist < left_enter:
                self._left_pinch_active = True

        right_click_pose = (not fingers.index) and (not fingers.ring) and (not fingers.pinky)
        if right_click_pose:
            self._right_pose_frames += 1
        else:
            self._right_pose_frames = 0

        if self._right_pinch_active:
            if right_dist > right_exit or not right_click_pose:
                self._right_pinch_active = False
        else:
            if right_click_pose and right_dist < right_enter:
                self._right_pinch_active = True

        # Right click: middle+thumb pinch (edge-trigger).
        if self._right_pinch_active and not self._left_pinch_active:
            self._scroll_active = False
            self._prev_scroll_y = None
            self._right_pinch_frames += 1
            if (
                not self._right_click_fired
                and self._right_pose_frames >= self._right_click_pose_frames
                and self._right_pinch_frames >= self._right_click_pinch_frames
                and now - self._last_right_click >= CLICK_COOLDOWN
            ):
                self._right_click_fired = True
                self._last_right_click = now
                return self._confirm_result(GestureType.RIGHT_CLICK)
            return self._confirm_result(GestureType.MOVE)
        if not self._right_pinch_active:
            self._right_pinch_frames = 0
            self._right_click_fired = False

        # Left click/drag: index+thumb pinch.
        if self._left_pinch_active:
            self._scroll_active = False
            self._prev_scroll_y = None
            self._left_pinch_frames += 1
            if not self._left_click_fired and self._left_pinch_frames >= 1 and now - self._last_left_click >= CLICK_COOLDOWN:
                self._left_click_fired = True
                self._last_left_click = now
                self._left_pinch_start = now
                return self._confirm_result(GestureType.LEFT_CLICK)

            if self._left_pinch_start == 0.0:
                self._left_pinch_start = now

            if now - self._left_pinch_start >= DRAG_HOLD_TIME:
                self._is_dragging = True
                return self._confirm_result(GestureType.DRAG)

            return self._confirm_result(GestureType.MOVE)

        # Pinch released.
        if not self._left_pinch_active:
            self._left_pinch_frames = 0
            self._left_click_fired = False
            self._left_pinch_start = 0.0
            self._is_dragging = False

        # Scroll mode: peace sign.
        if fingers.index and fingers.middle and not fingers.ring and not fingers.pinky:
            y = 0.5 * (landmarks_xy[_INDEX_TIP][1] + landmarks_xy[_MIDDLE_TIP][1])
            if self._prev_scroll_y is None:
                self._prev_scroll_y = y
                self._scroll_active = True
                return self._confirm_result(GestureType.SCROLL, 0)

            dy = y - self._prev_scroll_y
            self._prev_scroll_y = y
            self._scroll_active = True

            if abs(dy) < self._scroll_motion_threshold:
                return self._confirm_result(GestureType.SCROLL, 0)

            raw = -dy * SCROLL_SENSITIVITY
            self._smooth_scroll = 0.6 * self._smooth_scroll + 0.4 * raw
            amount = int(self._smooth_scroll)
            return self._confirm_result(GestureType.SCROLL, amount)

        self._scroll_active = False
        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        # Move: index finger only.
        if fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            return self._confirm_result(GestureType.MOVE)

        return self._confirm_result(GestureType.PAUSE)

    def _extract_hand_data(self, hand_data):
        if isinstance(hand_data, dict):
            return hand_data.get("xy"), hand_data.get("z")
        # Backward compatibility with list[(x,y)] payloads.
        return hand_data, None

    def _reset_temporal(self) -> None:
        self._is_dragging = False

        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0
        self._right_pose_frames = 0
        self._left_click_fired = False
        self._right_click_fired = False

        self._scroll_active = False
        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

    def _reset_non_pause_modes(self) -> None:
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0
        self._right_pose_frames = 0
        self._left_click_fired = False
        self._right_click_fired = False
        self._is_dragging = False
        self._scroll_active = False
        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

    @staticmethod
    def _dist(a: tuple[int, int], b: tuple[int, int]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return (dx * dx + dy * dy) ** 0.5

    def _hand_scale(self, xy: list[tuple[int, int]]) -> float:
        try:
            return max(40.0, self._dist(xy[_INDEX_MCP], xy[_PINKY_MCP]))
        except Exception:
            # Fallback: use bounding box size.
            xs = [p[0] for p in xy]
            ys = [p[1] for p in xy]
            return max(40.0, float(max(max(xs) - min(xs), max(ys) - min(ys))))

    def _confirm_result(self, raw_gesture: GestureType, scroll_delta: int = 0) -> GestureResult:
        if raw_gesture == self._candidate_gesture:
            self._candidate_frames += 1
        else:
            self._candidate_gesture = raw_gesture
            self._candidate_frames = 1

        # Immediate modes: PAUSE/SCROLL should feel instant.
        if raw_gesture in {GestureType.PAUSE, GestureType.SCROLL}:
            self._confirmed_gesture = raw_gesture
        # Edge-trigger actions should not be blocked by confirmation.
        elif raw_gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DOUBLE_CLICK, GestureType.TASK_VIEW}:
            self._confirmed_gesture = raw_gesture
        else:
            # Avoid initial "dead frames" when entering from NONE.
            if self._confirmed_gesture == GestureType.NONE and raw_gesture != GestureType.NONE:
                self._confirmed_gesture = raw_gesture
            elif self._candidate_frames >= self._confirm_frames_required:
                self._confirmed_gesture = raw_gesture

        if self._confirmed_gesture == GestureType.SCROLL:
            return GestureResult(self._confirmed_gesture, scroll_delta=scroll_delta)
        return GestureResult(self._confirmed_gesture, scroll_delta=0)
