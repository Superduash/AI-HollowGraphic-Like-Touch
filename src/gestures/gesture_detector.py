"""Stable state-machine gesture detector for hand interactions."""

import time

from config import CLICK_COOLDOWN, DRAG_HOLD_TIME, SCROLL_SENSITIVITY
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_finger_states, point_distance

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
    """Gesture detector with confirmation, locking, hysteresis, priority, and hand dominance."""

    def __init__(self) -> None:
        self._confirm_duration: float = 0.12
        self._candidate_gesture: GestureType = GestureType.PAUSE
        self._candidate_start: float = 0.0
        self._active_gesture: GestureType = GestureType.PAUSE

        self._lock_ms: float = 0.2
        self._locked_until: float = 0.0

        self._pinch_enter_px = 20.0
        self._pinch_exit_px = 28.0

        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_click_pending = False
        self._right_click_pending = False
        self._is_dragging = False

        self._click_cooldown = 0.3
        self._drag_hold_time = max(0.3, float(DRAG_HOLD_TIME))
        self._last_left_click = 0.0
        self._last_right_click = 0.0

        self._scroll_anchor_y: float | None = None
        self._prev_scroll_y: float | None = None
        
        self._media_track_cooldown = 0.8
        self._last_media_track = 0.0

        self._task_view_cooldown = 1.0
        self._task_view_confirm_duration = 0.25
        self._last_task_view = 0.0
        self._task_view_start = 0.0
        self._task_view_anchor = (0, 0)

    def _is_open_palm(self, xy: list[tuple[int, int]], fingers, hand_scale: float) -> bool:
        if not (fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky):
            return False

        try:
            wrist_y = xy[_WRIST][1]
            if not (xy[_INDEX_TIP][1] < wrist_y and xy[_MIDDLE_TIP][1] < wrist_y and xy[16][1] < wrist_y and xy[20][1] < wrist_y):
                return False
            spread = point_distance(xy[_INDEX_TIP], xy[20])
            thumb_sep = point_distance(xy[_THUMB_TIP], xy[_INDEX_MCP])
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

    def set_confirm_duration(self, duration: float) -> None:
        self._confirm_duration = max(0.0, float(duration))

    def detect(self, hand_data) -> GestureResult:
        if not hand_data:
            self._reset_temporal()
            return self._commit_gesture(GestureType.PAUSE, time.monotonic(), 0)

        landmarks_xy, _, label = self._extract_hand_data(hand_data)
        if not landmarks_xy or len(landmarks_xy) < 21:
            self._reset_temporal()
            return self._commit_gesture(GestureType.PAUSE, time.monotonic(), 0)

        now = time.monotonic()
        fingers = get_finger_states(landmarks_xy)
        scroll_delta = 0

        hand_scale = self._hand_scale(landmarks_xy)
        
        # TASK VIEW: Required to hold perfectly still (within 25px) for 0.25s
        if self._is_open_palm(landmarks_xy, fingers, hand_scale):
            if self._task_view_start == 0.0:
                self._task_view_start = now
                self._task_view_anchor = landmarks_xy[_WRIST]
            else:
                if point_distance(landmarks_xy[_WRIST], self._task_view_anchor) > 25.0:
                    self._task_view_start = now
                    self._task_view_anchor = landmarks_xy[_WRIST]
                elif now - self._task_view_start >= self._task_view_confirm_duration and now - self._last_task_view >= self._task_view_cooldown:
                    self._last_task_view = now
                    self._task_view_start = 0.0
                    self._active_gesture = GestureType.TASK_VIEW
                    self._locked_until = now + self._lock_ms
                    return GestureResult(GestureType.TASK_VIEW, 0)
            return self._commit_gesture(GestureType.PAUSE, now, 0)
        else:
            self._task_view_start = 0.0

        thumb = landmarks_xy[_THUMB_TIP]
        index_tip = landmarks_xy[_INDEX_TIP]
        middle_tip = landmarks_xy[_MIDDLE_TIP]

        left_dist = point_distance(thumb, index_tip)
        right_dist = point_distance(thumb, middle_tip)

        left_entered = False
        if self._left_pinch_active:
            if left_dist >= self._pinch_exit_px:
                self._left_pinch_active = False
                self._left_click_pending = False
                self._left_pinch_start = 0.0
                self._is_dragging = False
        else:
            if left_dist <= self._pinch_enter_px:
                self._left_pinch_active = True
                left_entered = True
                self._left_click_pending = True
                self._left_pinch_start = now
                self._is_dragging = False

        right_click_pose = fingers.middle and (not fingers.index) and (not fingers.ring) and (not fingers.pinky)
        right_entered = False
        if self._right_pinch_active:
            if right_dist >= self._pinch_exit_px or not right_click_pose:
                self._right_pinch_active = False
                self._right_click_pending = False
        else:
            if right_click_pose and right_dist <= self._pinch_enter_px:
                self._right_pinch_active = True
                right_entered = True
                self._right_click_pending = True

        if left_entered and now - self._last_left_click < self._click_cooldown:
            self._left_click_pending = False
        if right_entered and now - self._last_right_click < self._click_cooldown:
            self._right_click_pending = False

        in_scroll_pose = fingers.index and fingers.middle and (not fingers.ring) and (not fingers.pinky)
        
        # HAND DOMINANCE LOGIC
        if label == "Left":
            # Left Hand maps to Media Controls
            intent = GestureType.PAUSE
            
            # Left Pinch + Move Up/Down -> Volume Up/Down
            if self._left_pinch_active:
                y = landmarks_xy[_THUMB_TIP][1]
                if self._scroll_anchor_y is None:
                    self._scroll_anchor_y = y
                else:
                    rel = y - self._scroll_anchor_y
                    if abs(rel) > 15.0:
                        sign = 1 if rel > 0 else -1
                        scroll_delta = int(abs(rel) - 15.0)
                        intent = GestureType.MEDIA_VOL_DOWN if sign > 0 else GestureType.MEDIA_VOL_UP
                        self._scroll_anchor_y = y
            # Left Scroll Pose (Peace Sign) -> Next/Prev Track
            elif in_scroll_pose:
                y = 0.5 * (landmarks_xy[_INDEX_TIP][1] + landmarks_xy[_MIDDLE_TIP][1])
                if self._scroll_anchor_y is None:
                    self._scroll_anchor_y = y
                else:
                    rel = y - self._scroll_anchor_y
                    if abs(rel) > 30.0 and now - self._last_media_track >= self._media_track_cooldown:
                        self._last_media_track = now
                        intent = GestureType.MEDIA_PREV if rel > 0 else GestureType.MEDIA_NEXT
                        self._scroll_anchor_y = y
            else:
                self._scroll_anchor_y = None
                
            return self._commit_gesture(intent, now, scroll_delta)
            
        else:
            # RIGHT HAND (Normal Standard Controls)
            if in_scroll_pose and (not self._left_pinch_active) and (not self._right_pinch_active):
                y = 0.5 * (landmarks_xy[_INDEX_TIP][1] + landmarks_xy[_MIDDLE_TIP][1])
                if self._scroll_anchor_y is None:
                    self._scroll_anchor_y = y
                    self._prev_scroll_y = y
                else:
                    rel = y - self._scroll_anchor_y
                    if abs(rel) > 15.0:
                        sign = 1 if rel > 0 else -1
                        scroll_delta = int(-sign * ((abs(rel) - 15.0) * SCROLL_SENSITIVITY * 2.0))
                        self._scroll_anchor_y = y
            else:
                self._scroll_anchor_y = None
                self._prev_scroll_y = None

            intent = GestureType.PAUSE
            keyboard_pose = (not fingers.thumb) and fingers.index and fingers.middle and fingers.ring and (not fingers.pinky)
            
            if self._left_pinch_active and self._left_pinch_start > 0.0 and (now - self._left_pinch_start) >= self._drag_hold_time:
                intent = GestureType.DRAG
                if not self._is_dragging:
                    self._is_dragging = True
                self._left_click_pending = False
            elif self._left_pinch_active and self._left_click_pending and now - self._last_left_click >= self._click_cooldown:
                intent = GestureType.LEFT_CLICK
            elif self._right_pinch_active and self._right_click_pending and now - self._last_right_click >= self._click_cooldown:
                intent = GestureType.RIGHT_CLICK
            elif in_scroll_pose and (self._scroll_anchor_y is not None):
                intent = GestureType.SCROLL
            elif keyboard_pose and not self._left_pinch_active and not self._right_pinch_active:
                intent = GestureType.KEYBOARD
            elif fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
                intent = GestureType.MOVE
            else:
                intent = GestureType.PAUSE
                self._is_dragging = False

            return self._commit_gesture(intent, now, scroll_delta)

    def _commit_gesture(self, intent: GestureType, now: float, scroll_delta: int) -> GestureResult:
        if now < self._locked_until:
            if self._active_gesture in (GestureType.SCROLL, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN):
                return GestureResult(self._active_gesture, scroll_delta)
            return GestureResult(self._active_gesture, 0)

        if intent == self._candidate_gesture:
            if now - self._candidate_start >= self._confirm_duration and intent != self._active_gesture:
                self._active_gesture = intent
                self._locked_until = now + self._lock_ms
                if intent == GestureType.LEFT_CLICK:
                    self._left_click_pending = False
                    self._last_left_click = now
                elif intent == GestureType.RIGHT_CLICK:
                    self._right_click_pending = False
                    self._last_right_click = now
        else:
            self._candidate_gesture = intent
            self._candidate_start = now

        if self._active_gesture in (GestureType.SCROLL, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN):
            return GestureResult(self._active_gesture, scroll_delta)
        return GestureResult(self._active_gesture, 0)

    def _extract_hand_data(self, hand_data):
        if isinstance(hand_data, dict):
            return hand_data.get("xy"), hand_data.get("z"), hand_data.get("label", "Right")
        return hand_data, None, "Right"

    def _reset_temporal(self) -> None:
        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_click_pending = False
        self._right_click_pending = False
        self._is_dragging = False
        self._scroll_anchor_y = None
        self._prev_scroll_y = None
        self._candidate_gesture = GestureType.PAUSE
        self._candidate_start = 0.0
        self._task_view_start = 0.0
        self._task_view_anchor = (0, 0)
        self._active_gesture = GestureType.PAUSE
        self._locked_until = 0.0

    def _hand_scale(self, xy: list[tuple[int, int]]) -> float:
        try:
            return max(40.0, point_distance(xy[_INDEX_MCP], xy[_PINKY_MCP]))
        except Exception:
            return 40.0
