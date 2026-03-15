"""
gesture_detector.py - Interpret hand landmarks as actionable gestures.

Detects:
  * Cursor position  – index finger tip (landmark 8).
  * Left click       – pinch between thumb tip (4) and index finger tip (8).
  * Right click      – pinch between thumb tip (4) and middle finger tip (12).

A *cooldown* mechanism prevents a single sustained pinch from firing many
clicks.  Distances are measured in pixel space so the threshold scales
naturally with the webcam resolution.
"""

import math
import time

# MediaPipe landmark indices used for gesture detection
THUMB_TIP   = 4
INDEX_TIP   = 8
MIDDLE_TIP  = 12


def _distance(p1, p2):
    """
    Euclidean distance between two (x, y) points.

    Args:
        p1 (tuple[int, int]): First point.
        p2 (tuple[int, int]): Second point.

    Returns:
        float: Pixel distance.
    """
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])


class GestureDetector:
    """
    Stateful gesture recogniser that operates on a list of 21 hand landmarks.

    Call :meth:`detect` once per frame with the current landmark list.  The
    returned :class:`GestureResult` carries the cursor position and any click
    events that occurred this frame.
    """

    def __init__(
        self,
        pinch_threshold_ratio=0.07,
        click_cooldown=0.5,
    ):
        """
        Args:
            pinch_threshold_ratio (float): Pinch is detected when the distance
                between the two fingertips is less than
                ``frame_diagonal * pinch_threshold_ratio``.  Adjust to taste –
                larger values make the gesture easier to trigger.
            click_cooldown (float): Minimum seconds between two consecutive
                click events of the *same* type to avoid unintended double
                clicks from a single gesture hold.
        """
        self.pinch_threshold_ratio = pinch_threshold_ratio
        self.click_cooldown = click_cooldown

        # Timestamps of the last detected click for each button
        self._last_left_click  = 0.0
        self._last_right_click = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, landmarks, frame_w, frame_h):
        """
        Analyse *landmarks* and return a :class:`GestureResult`.

        Args:
            landmarks (list[tuple[int, int]]): 21 (x, y) pixel coordinates
                from :class:`hand_tracker.HandTracker`.
            frame_w (int): Width of the webcam frame in pixels.
            frame_h (int): Height of the webcam frame in pixels.

        Returns:
            GestureResult: Detected cursor position and click events.
        """
        # Compute pixel diagonal to derive a resolution-independent threshold
        diagonal = math.hypot(frame_w, frame_h)
        threshold = diagonal * self.pinch_threshold_ratio

        thumb  = landmarks[THUMB_TIP]
        index  = landmarks[INDEX_TIP]
        middle = landmarks[MIDDLE_TIP]

        # Cursor tracks the index finger tip
        cursor_x, cursor_y = index

        # --- Left click: thumb ↔ index pinch ---
        left_click = False
        dist_left = _distance(thumb, index)
        if dist_left < threshold:
            now = time.monotonic()
            if now - self._last_left_click >= self.click_cooldown:
                left_click = True
                self._last_left_click = now

        # --- Right click: thumb ↔ middle pinch ---
        right_click = False
        dist_right = _distance(thumb, middle)
        if dist_right < threshold:
            now = time.monotonic()
            if now - self._last_right_click >= self.click_cooldown:
                right_click = True
                self._last_right_click = now

        return GestureResult(
            cursor_x=cursor_x,
            cursor_y=cursor_y,
            left_click=left_click,
            right_click=right_click,
            pinch_dist_left=dist_left,
            pinch_dist_right=dist_right,
            pinch_threshold=threshold,
        )


class GestureResult:
    """
    Data class holding the output of a single :meth:`GestureDetector.detect`
    call.

    Attributes:
        cursor_x (int):          Webcam-space X of the index finger tip.
        cursor_y (int):          Webcam-space Y of the index finger tip.
        left_click (bool):       True if a left-click event fired this frame.
        right_click (bool):      True if a right-click event fired this frame.
        pinch_dist_left (float): Current pixel distance for left-click pinch.
        pinch_dist_right (float): Current pixel distance for right-click pinch.
        pinch_threshold (float): Pixel distance threshold used this frame.
    """

    __slots__ = (
        "cursor_x",
        "cursor_y",
        "left_click",
        "right_click",
        "pinch_dist_left",
        "pinch_dist_right",
        "pinch_threshold",
    )

    def __init__(
        self,
        cursor_x,
        cursor_y,
        left_click,
        right_click,
        pinch_dist_left,
        pinch_dist_right,
        pinch_threshold,
    ):
        self.cursor_x        = cursor_x
        self.cursor_y        = cursor_y
        self.left_click      = left_click
        self.right_click     = right_click
        self.pinch_dist_left  = pinch_dist_left
        self.pinch_dist_right = pinch_dist_right
        self.pinch_threshold  = pinch_threshold
