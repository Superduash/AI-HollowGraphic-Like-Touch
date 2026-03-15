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
        self._confirm_frames_required: int = 4
        self._candidate_gesture: GestureType = GestureType.NONE
        self._candidate_frames: int = 0
        self._confirmed_gesture: GestureType = GestureType.NONE

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
            self._confirmed_gesture = GestureType.NONE
            self._candidate_gesture = GestureType.NONE
            self._candidate_frames = 0
            return GestureResult(GestureType.NONE)

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
                return self._confirm_result(GestureType.DRAG)

            # LEFT_CLICK / DOUBLE_CLICK: pinch stable for N frames
            self._bump_raw(GestureType.LEFT_CLICK)
            if self._raw_frames >= GESTURE_STABILITY_FRAMES and not self._click_fired:
                self._click_fired = True
                if now - self._last_click_time < DOUBLE_CLICK_WINDOW:
                    self._last_click_time = now
                    return self._confirm_result(GestureType.DOUBLE_CLICK)
                self._last_click_time = now
                return self._confirm_result(GestureType.LEFT_CLICK)

            # Still pinching but not yet stable → keep moving cursor
            return self._confirm_result(GestureType.MOVE)

        # Pinch just released
        if self._is_pinching:
            was_drag = self._is_dragging
            self._is_pinching = False
            self._is_dragging = False
            if was_drag:
                # Return NONE so caller can detect drag→non-drag transition
                self._bump_raw(GestureType.NONE)
                return self._confirm_result(GestureType.NONE)

        # ==============================================================
        # FINGER-PATTERN GESTURES (no pinch active)
        # ==============================================================
        fingers = get_finger_states(landmarks)

        # PAUSE — closed fist (4 fingers down, ignore thumb)
        if not fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.PAUSE)
            return self._confirm_result(GestureType.PAUSE)

        # OPEN PALM — all 5 up
        if fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.OPEN_PALM)
            return self._confirm_result(GestureType.OPEN_PALM)

        # VOLUME — 4 fingers up, thumb down
        if not fingers.thumb and fingers.index and fingers.middle and fingers.ring and fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.VOLUME)
            return self._confirm_result(GestureType.VOLUME)

        # SWITCH WINDOW — index + middle + ring up, pinky down
        if fingers.index and fingers.middle and fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.SWITCH_WINDOW)
            return self._confirm_result(GestureType.SWITCH_WINDOW)

        # TWO FINGERS (RIGHT_CLICK / SCROLL) — index + middle up, ring + pinky down
        if fingers.index and fingers.middle and not fingers.ring and not fingers.pinky:
            return self._handle_two_finger(landmarks, now)

        # MOVE — index up only
        if fingers.index and not fingers.middle and not fingers.ring and not fingers.pinky:
            self._reset_scroll()
            self._bump_raw(GestureType.MOVE)
            return self._confirm_result(GestureType.MOVE)

        # Fallback
        self._reset_scroll()
        self._bump_raw(GestureType.NONE)
        return self._confirm_result(GestureType.NONE)

    # ------------------------------------------------------------------
    # Two-finger handler (RIGHT_CLICK vs SCROLL discrimination)
    # ------------------------------------------------------------------

    def _handle_two_finger(self, landmarks: list[tuple[int, int]], now: float) -> GestureResult:
        ix, iy = landmarks[_INDEX]
        mx, my = landmarks[_MIDDLE]
        tip_len = ((mx - ix) * (mx - ix) + (my - iy) * (my - iy)) ** 0.5
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

        # Click detection mode when two fingers are up and tips pinch together.
        if tip_len < PINCH_DISTANCE_THRESHOLD and now - self._last_click_time >= CLICK_COOLDOWN:
            self._last_click_time = now
            self._bump_raw(GestureType.LEFT_CLICK)
            return self._confirm_result(GestureType.LEFT_CLICK)

        # Decision phase: wait stability frames then decide
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
                    return self._confirm_result(GestureType.RIGHT_CLICK)
                self._in_scroll_mode = True

        if self._in_scroll_mode:
            # Smooth the scroll delta (EMA)
            raw = -y_delta * SCROLL_SENSITIVITY
            self._smooth_scroll = 0.6 * self._smooth_scroll + 0.4 * raw
            amount = int(self._smooth_scroll)
            self._bump_raw(GestureType.SCROLL)
            return self._confirm_result(GestureType.SCROLL, scroll_delta=amount)

        # Waiting for decision
        self._bump_raw(GestureType.NONE)
        return self._confirm_result(GestureType.NONE)

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

    def _confirm_result(self, raw_gesture: GestureType, scroll_delta: int = 0) -> GestureResult:
        # Keep click/drag responses immediate to avoid missed transient actions.
        if raw_gesture in {
            GestureType.LEFT_CLICK,
            GestureType.RIGHT_CLICK,
            GestureType.DOUBLE_CLICK,
            GestureType.DRAG,
        }:
            self._confirmed_gesture = self._transition_state(self._confirmed_gesture, raw_gesture)
            if self._confirmed_gesture == GestureType.SCROLL:
                return GestureResult(self._confirmed_gesture, scroll_delta=scroll_delta)
            return GestureResult(self._confirmed_gesture, scroll_delta=0)

        if self._confirmed_gesture == GestureType.NONE and raw_gesture in {GestureType.MOVE, GestureType.PAUSE}:
            self._confirmed_gesture = raw_gesture
            return GestureResult(self._confirmed_gesture, scroll_delta=0)

        if raw_gesture == self._candidate_gesture:
            self._candidate_frames += 1
        else:
            self._candidate_gesture = raw_gesture
            self._candidate_frames = 1

        if self._candidate_frames >= self._confirm_frames_required:
            next_gesture = self._transition_state(self._confirmed_gesture, self._candidate_gesture)
            self._confirmed_gesture = next_gesture

        if self._confirmed_gesture == GestureType.SCROLL:
            return GestureResult(self._confirmed_gesture, scroll_delta=scroll_delta)
        return GestureResult(self._confirmed_gesture, scroll_delta=0)

    def set_confirm_frames(self, frames: int) -> None:
        self._confirm_frames_required = max(1, int(frames))

    @staticmethod
    def _transition_state(current: GestureType, nxt: GestureType) -> GestureType:
        if nxt == current:
            return current

        allowed = {
            GestureType.MOVE: {
                GestureType.LEFT_CLICK,
                GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK,
                GestureType.SCROLL,
                GestureType.DRAG,
                GestureType.PAUSE,
                GestureType.MOVE,
                GestureType.NONE,
            },
            GestureType.LEFT_CLICK: {GestureType.MOVE, GestureType.PAUSE, GestureType.NONE, GestureType.DRAG},
            GestureType.RIGHT_CLICK: {GestureType.MOVE, GestureType.PAUSE, GestureType.NONE, GestureType.DRAG},
            GestureType.DOUBLE_CLICK: {GestureType.MOVE, GestureType.PAUSE, GestureType.NONE, GestureType.DRAG},
            GestureType.SCROLL: {GestureType.MOVE, GestureType.PAUSE, GestureType.NONE, GestureType.SCROLL},
            GestureType.DRAG: {GestureType.MOVE, GestureType.PAUSE, GestureType.NONE, GestureType.DRAG},
            GestureType.PAUSE: {
                GestureType.MOVE,
                GestureType.PAUSE,
                GestureType.NONE,
                GestureType.LEFT_CLICK,
                GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK,
                GestureType.SCROLL,
                GestureType.DRAG,
            },
            GestureType.NONE: {
                GestureType.MOVE,
                GestureType.NONE,
                GestureType.PAUSE,
                GestureType.LEFT_CLICK,
                GestureType.RIGHT_CLICK,
                GestureType.DOUBLE_CLICK,
                GestureType.SCROLL,
                GestureType.DRAG,
            },
        }
        if nxt in allowed.get(current, {nxt}):
            return nxt
        return current
