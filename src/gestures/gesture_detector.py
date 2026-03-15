"""Air-touch gesture detector with forward poke interaction model."""

import time

from config import CLICK_COOLDOWN, DRAG_HOLD_TIME, SCROLL_SENSITIVITY
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_finger_states

_INDEX = 8
_MIDDLE = 12


class GestureResult:
    """Output of gesture detection for one frame."""

    __slots__ = ("gesture", "scroll_delta")

    def __init__(self, gesture: GestureType = GestureType.NONE, scroll_delta: int = 0) -> None:
        self.gesture = gesture
        self.scroll_delta = scroll_delta


class GestureDetector:
    """Stable gesture detector for holographic air-touch interactions."""

    def __init__(self) -> None:
        self._confirm_frames_required: int = 4
        self._candidate_gesture: GestureType = GestureType.NONE
        self._candidate_frames: int = 0
        self._confirmed_gesture: GestureType = GestureType.NONE

        self._prev_index_z: float | None = None
        self._prev_middle_z: float | None = None
        self._prev_index_y: int | None = None

        self._forward_active = False
        self._forward_start = 0.0
        self._is_dragging = False
        self._last_click_time = 0.0

        self._tap_threshold = 0.055
        self._drag_threshold = 0.080
        self._scroll_forward_threshold = 0.020
        self._scroll_motion_threshold = 4

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    def set_confirm_frames(self, frames: int) -> None:
        self._confirm_frames_required = max(1, int(frames))

    def detect(self, hand_data) -> GestureResult:
        if not hand_data:
            self._reset_temporal()
            return self._confirm_result(GestureType.NONE)

        landmarks_xy, z_values = self._extract_hand_data(hand_data)
        if not landmarks_xy or len(landmarks_xy) < 21:
            self._reset_temporal()
            return self._confirm_result(GestureType.NONE)

        # Backward-compatible 2D behavior for older callers/tests.
        if z_values is None:
            return self._detect_legacy_2d(landmarks_xy)

        now = time.monotonic()
        fingers = get_finger_states(landmarks_xy)

        index_z = z_values[_INDEX] if z_values and len(z_values) > _INDEX else 0.0
        middle_z = z_values[_MIDDLE] if z_values and len(z_values) > _MIDDLE else 0.0

        dz_index = 0.0 if self._prev_index_z is None else self._prev_index_z - index_z
        dz_middle = 0.0 if self._prev_middle_z is None else self._prev_middle_z - middle_z

        raw_gesture = GestureType.NONE
        scroll_delta = 0

        # PAUSE: open palm freezes pointer updates.
        if fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky:
            raw_gesture = GestureType.PAUSE

        # Two-finger forward poke: right click.
        elif fingers.index and fingers.middle and not fingers.ring and not fingers.pinky:
            if dz_index > self._tap_threshold and dz_middle > self._tap_threshold and now - self._last_click_time > CLICK_COOLDOWN:
                self._last_click_time = now
                raw_gesture = GestureType.RIGHT_CLICK
            else:
                raw_gesture = GestureType.MOVE

        # Index-forward hold: drag; quick poke: left click.
        elif fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            if dz_index > self._drag_threshold:
                if not self._forward_active:
                    self._forward_active = True
                    self._forward_start = now
            elif dz_index < 0.0:
                self._forward_active = False

            if self._forward_active and now - self._forward_start >= DRAG_HOLD_TIME:
                self._is_dragging = True
                raw_gesture = GestureType.DRAG
            elif dz_index > self._tap_threshold and now - self._last_click_time > CLICK_COOLDOWN:
                self._last_click_time = now
                raw_gesture = GestureType.LEFT_CLICK
            else:
                raw_gesture = GestureType.MOVE

            # Forward-hover + vertical motion: scroll.
            if index_z < -self._scroll_forward_threshold and self._prev_index_y is not None:
                dy = landmarks_xy[_INDEX][1] - self._prev_index_y
                if abs(dy) >= self._scroll_motion_threshold:
                    raw_gesture = GestureType.SCROLL
                    scroll_delta = int(-dy * SCROLL_SENSITIVITY)

        else:
            if self._is_dragging:
                self._is_dragging = False
            self._forward_active = False
            raw_gesture = GestureType.NONE

        if raw_gesture != GestureType.DRAG and self._is_dragging and dz_index < 0.0:
            self._is_dragging = False
            raw_gesture = GestureType.NONE

        self._prev_index_z = index_z
        self._prev_middle_z = middle_z
        self._prev_index_y = landmarks_xy[_INDEX][1]

        return self._confirm_result(raw_gesture, scroll_delta)

    def _extract_hand_data(self, hand_data):
        if isinstance(hand_data, dict):
            return hand_data.get("xy"), hand_data.get("z")
        # Backward compatibility with list[(x,y)] payloads.
        return hand_data, None

    def _detect_legacy_2d(self, landmarks_xy) -> GestureResult:
        fingers = get_finger_states(landmarks_xy)

        # PAUSE: fist/closed hand.
        if not fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            return GestureResult(GestureType.PAUSE)

        # LEFT_CLICK: thumb-index pinch with short stability.
        tx, ty = landmarks_xy[4]
        ix, iy = landmarks_xy[8]
        pinch_dist = ((tx - ix) * (tx - ix) + (ty - iy) * (ty - iy)) ** 0.5
        if pinch_dist < 20:
            self._candidate_frames += 1
            if self._candidate_frames >= 2:
                return GestureResult(GestureType.LEFT_CLICK)
            return GestureResult(GestureType.MOVE)

        # MOVE: index up only.
        if fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            return GestureResult(GestureType.MOVE)

        # RIGHT_CLICK: index+middle up with stability.
        if fingers.index and fingers.middle and not fingers.ring and not fingers.pinky:
            self._candidate_frames += 1
            if self._candidate_frames >= 2:
                return GestureResult(GestureType.RIGHT_CLICK)
            return GestureResult(GestureType.MOVE)

        self._candidate_frames = 0
        return GestureResult(GestureType.NONE)

    def _reset_temporal(self) -> None:
        self._prev_index_z = None
        self._prev_middle_z = None
        self._prev_index_y = None
        self._forward_active = False
        self._is_dragging = False

    def _confirm_result(self, raw_gesture: GestureType, scroll_delta: int = 0) -> GestureResult:
        if raw_gesture == self._candidate_gesture:
            self._candidate_frames += 1
        else:
            self._candidate_gesture = raw_gesture
            self._candidate_frames = 1

        if self._candidate_frames > self._confirm_frames_required:
            self._confirmed_gesture = raw_gesture

        # Click actions should not be blocked by long persistence.
        if raw_gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DOUBLE_CLICK}:
            self._confirmed_gesture = raw_gesture

        if self._confirmed_gesture == GestureType.SCROLL:
            return GestureResult(self._confirmed_gesture, scroll_delta=scroll_delta)
        return GestureResult(self._confirmed_gesture, scroll_delta=0)
