"""
utils.py - Helper utilities for the AI Holographic Touch system.

Provides coordinate interpolation, exponential moving average smoothing,
and FPS calculation used across the other modules.
"""

import time
import numpy as np


def map_coordinates(x, y, src_w, src_h, dst_w, dst_h, margin=0.05):
    """
    Map a point from webcam/source space to screen/destination space.

    A small margin is subtracted from the usable webcam area so the cursor
    can reach the screen edges without the user having to move their finger
    all the way to the frame border.

    Args:
        x (float): X coordinate in source space (0 – src_w).
        y (float): Y coordinate in source space (0 – src_h).
        src_w (int): Source frame width in pixels.
        src_h (int): Source frame height in pixels.
        dst_w (int): Destination (screen) width in pixels.
        dst_h (int): Destination (screen) height in pixels.
        margin (float): Fractional margin to crop from each edge (default 5 %).

    Returns:
        tuple[int, int]: Mapped (screen_x, screen_y) clipped to [0, dst_w/h].
    """
    # Compute the usable inner rectangle of the webcam frame
    margin_x = src_w * margin
    margin_y = src_h * margin

    # Normalise x/y to [0, 1] within the inner rectangle
    norm_x = (x - margin_x) / (src_w - 2 * margin_x)
    norm_y = (y - margin_y) / (src_h - 2 * margin_y)

    # Clamp to [0, 1] so points outside the inner rectangle still map to edges
    norm_x = float(np.clip(norm_x, 0.0, 1.0))
    norm_y = float(np.clip(norm_y, 0.0, 1.0))

    screen_x = int(norm_x * dst_w)
    screen_y = int(norm_y * dst_h)

    return screen_x, screen_y


class EMAFilter:
    """
    Exponential Moving Average (EMA) filter for 2-D coordinates.

    Smooths noisy landmark positions so the on-screen cursor feels stable.
    A higher *alpha* tracks the raw signal more closely (less smoothing),
    while a lower *alpha* produces heavier smoothing at the cost of lag.
    """

    def __init__(self, alpha=0.3):
        """
        Args:
            alpha (float): Smoothing factor in (0, 1].  Recommended: 0.2–0.4.
        """
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in the range (0, 1]")
        self.alpha = alpha
        self._x = None  # last smoothed x value
        self._y = None  # last smoothed y value

    def update(self, x, y):
        """
        Feed a new (x, y) sample and return the smoothed position.

        On the very first call the raw values are returned unchanged so the
        cursor jumps directly to the finger instead of sliding in from (0, 0).

        Args:
            x (float): Raw x coordinate.
            y (float): Raw y coordinate.

        Returns:
            tuple[float, float]: Smoothed (x, y).
        """
        if self._x is None:
            self._x, self._y = x, y
        else:
            self._x = self.alpha * x + (1 - self.alpha) * self._x
            self._y = self.alpha * y + (1 - self.alpha) * self._y
        return self._x, self._y

    def reset(self):
        """Reset internal state (e.g. when no hand is detected)."""
        self._x = None
        self._y = None


class FPSCounter:
    """Utility class to compute the rolling average frames-per-second."""

    def __init__(self, window=30):
        """
        Args:
            window (int): Number of recent frame timestamps to average over.
        """
        self._window = window
        self._timestamps = []

    def tick(self):
        """
        Record the current timestamp and return the current FPS estimate.

        Returns:
            float: Frames per second, or 0.0 if fewer than two ticks recorded.
        """
        now = time.monotonic()
        self._timestamps.append(now)

        # Keep only the most recent *window* samples
        if len(self._timestamps) > self._window:
            self._timestamps.pop(0)

        if len(self._timestamps) < 2:
            return 0.0

        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed == 0:
            return 0.0
        return (len(self._timestamps) - 1) / elapsed
