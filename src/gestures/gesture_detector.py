"""Robust gesture detection engine with state machine and priority system.

Priority order: DRAG > CLICK > SCROLL > MOVE
All detection is O(1) per frame using only required landmark indices.
"""

import time

from config import (
    CLICK_COOLDOWN,
    DOUBLE_CLICK_WINDOW,
    DRAG_HOLD_TIME,
    GESTURE_STABILITY_FRAMES,
    PINCH_DISTANCE_THRESHOLD,
    PINCH_RELEASE_FACTOR,
    SCROLL_SENSITIVITY,
    SCROLL_THRESHOLD,
)
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_finger_states

# Landmark indices (inlined for zero function-call overhead)
_THUMB = 4
_INDEX = 8
_MIDDLE = 12


class GestureResult:
    """Output of gesture detection for one frame."""
    __slots__ = ("gesture", "scroll_delta")

    def __init__(self, gesture: GestureType = GestureType.NONE, scroll_delta: int = 0) -> None:
        self.gesture = gesture
        self.scroll_delta = scroll_delta


_NONE = GestureResult()
_PAUSE = GestureResult(GestureType.PAUSE)
_MOVE = GestureResult(GestureType.MOVE)
_OPEN_PALM = GestureResult(GestureType.OPEN_PALM)
_VOLUME = GestureResult(GestureType.VOLUME)
_SWITCH = GestureResult(GestureType.SWITCH_WINDOW)


class GestureDetector:
    """State-machine gesture detector with stability, cooldowns, and hysteresis."""

    def __init__(self) -> None:
        # State machine
        self._prev_raw: GestureType = GestureType.NONE
        self._raw_frames: int = 0

        # Pinch tracking
        self._is_pinching: bool = False
        self._pinch_start: float = 0.0
        self._click_fired: bool = False

        # Drag
        self._is_dragging: bool = False

        # Click / double-click cooldown
        self._last_click_time: float = 0.0

        # Right-click cooldown
        self._last_rclick_time: float = 0.0
        self._rclick_fired: bool = False

        # Two-finger / scroll state
        self._two_finger_frames: int = 0
        self._two_finger_y_accum: float = 0.0
        self._prev_scroll_y: float = -1.0
        self._in_scroll_mode: bool = False
        self._smooth_scroll: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    def detect(self, landmarks: list[tuple[int, int]] | None) -> GestureResult:
        """Classify the current gesture from 21-point landmarks. O(1)."""
        if not landmarks or len(landmarks) < 21:
            self._reset_all()
            return _NONE

        now = time.monotonic()

        # --- Pinch distance (thumb ↔ index) ---
        tx, ty = landmarks[_THUMB]
        ix, iy = landmarks[_INDEX]
        dx, dy = tx - ix, ty - iy
        pinch_dist = (dx * dx + dy * dy) ** 0.5

        enter_thresh = PINCH_DISTANCE_THRESHOLD
        exit_thresh = PINCH_DISTANCE_THRESHOLD * PINCH_RELEASE_FACTOR

        # Hysteresis: enter at tight threshold, exit at looser threshold
        if self._is_pinching:
            is_pinch = pinch_dist < exit_thresh
        else:
            is_pinch = pinch_dist < enter_thresh

        # ==============================================================
        # PRIORITY 1 — DRAG / CLICK (pinch-based)
        # ==============================================================
        if is_pinch:
            if not self._is_pinching:
                self._is_pinching = True
                self._pinch_start = now
                self._click_fired = False
                self._is_dragging = False
            self._reset_scroll()

            hold = now - self._pinch_start

            # DRAG: pinch held beyond threshold
            if hold >= DRAG_HOLD_TIME:
                self._is_dragging = True
                self._bump_raw(GestureType.DRAG)
                return GestureResult(GestureType.DRAG)

            # LEFT_CLICK / DOUBLE_CLICK: pinch stable for N frames
            self._bump_raw(GestureType.LEFT_CLICK)
            if self._raw_frames >= GESTURE_STABILITY_FRAMES and not self._click_fired:
                self._click_fired = True
                if now - self._last_click_time < DOUBLE_CLICK_WINDOW:
                    self._last_click_time = now
                    return GestureResult(GestureType.DOUBLE_CLICK)
                self._last_click_time = now
                return GestureResult(GestureType.LEFT_CLICK)

            # Still pinching but not yet stable → keep moving cursor
            return _MOVE

        # Pinch just released
        if self._is_pinching:
            was_drag = self._is_dragging
            self._is_pinching = False
            self._is_dragging = False
            if was_drag:
                # Return NONE so caller can detect drag→non-drag transition
                self._bump_raw(GestureType.NONE)
                return _NONE

        # ==============================================================
        # FINGER-PATTERN GESTURES (no pinch active)
        # ==============================================================
        fingers = get_finger_states(landmarks)

        # PAUSE — closed fist (4 fingers down, ignore thumb)
        if not fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.PAUSE)
            return _PAUSE

        # OPEN PALM — all 5 up
        if fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.OPEN_PALM)
            return _OPEN_PALM

        # VOLUME — 4 fingers up, thumb down
        if not fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.VOLUME)
            return _VOLUME

        # SWITCH WINDOW — index + middle + ring up, pinky down
        if fingers.index and fingers.middle and fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.SWITCH_WINDOW)
            return _SWITCH

        # TWO FINGERS (RIGHT_CLICK / SCROLL) — index + middle up, ring + pinky down
        if fingers.index and fingers.middle and not fingers.ring and not fingers.pinky:
            return self._handle_two_finger(landmarks, now)

        # MOVE — index up only
        if fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.MOVE)
            return _MOVE

        # Fallback
        self._reset_scroll()
        self._bump_raw(GestureType.NONE)
        return _NONE

    # ------------------------------------------------------------------
    # Two-finger handler (RIGHT_CLICK vs SCROLL discrimination)
    # ------------------------------------------------------------------

    def _handle_two_finger(self, landmarks: list[tuple[int, int]], now: float) -> GestureResult:
        iy = landmarks[_INDEX][1]
        my = landmarks[_MIDDLE][1]
        current_y = (iy + my) * 0.5

        if self._two_finger_frames == 0:
            # Just entered two-finger mode
            self._prev_scroll_y = current_y
            self._two_finger_y_accum = 0.0
            self._rclick_fired = False
            self._in_scroll_mode = False
            self._smooth_scroll = 0.0

        self._two_finger_frames += 1
        y_delta = current_y - self._prev_scroll_y
        self._two_finger_y_accum += abs(y_delta)
        self._prev_scroll_y = current_y

        # Decision phase: wait STABILITY_FRAMES frames then decide
        if not self._in_scroll_mode and self._two_finger_frames >= GESTURE_STABILITY_FRAMES:
            if self._two_finger_y_accum > SCROLL_THRESHOLD:
                # Significant movement → scroll (no right click)
                self._in_scroll_mode = True
            else:
                # Stable hold → right click (once, then enter scroll standby)
                if not self._rclick_fired and now - self._last_rclick_time >= CLICK_COOLDOWN:
                    self._rclick_fired = True
                    self._last_rclick_time = now
                    self._bump_raw(GestureType.RIGHT_CLICK)
                    return GestureResult(GestureType.RIGHT_CLICK)
                self._in_scroll_mode = True

        if self._in_scroll_mode:
            # Smooth the scroll delta (EMA)
            raw = -y_delta * SCROLL_SENSITIVITY
            self._smooth_scroll = 0.6 * self._smooth_scroll + 0.4 * raw
            amount = int(self._smooth_scroll)
            self._bump_raw(GestureType.SCROLL)
            return GestureResult(GestureType.SCROLL, scroll_delta=amount)

        # Waiting for decision
        self._bump_raw(GestureType.NONE)
        return _NONE

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _bump_raw(self, raw: GestureType) -> None:
        if raw == self._prev_raw:
            self._raw_frames += 1
        else:
            self._prev_raw = raw
            self._raw_frames = 1

    def _reset_scroll(self) -> None:
        self._two_finger_frames = 0
        self._two_finger_y_accum = 0.0
        self._prev_scroll_y = -1.0
        self._in_scroll_mode = False
        self._smooth_scroll = 0.0

    def _reset_all(self) -> None:
        if self._is_dragging:
            self._is_dragging = False
        self._is_pinching = False
        self._reset_scroll()
        self._prev_raw = GestureType.NONE
        self._raw_frames = 0
