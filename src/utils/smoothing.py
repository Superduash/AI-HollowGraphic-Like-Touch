"""Cursor smoothing utilities to reduce jitter."""

from collections import deque
from typing import Deque, Tuple


class CursorSmoother:
    """Smooth cursor coordinates using moving average + linear interpolation."""

    def __init__(self, window_size: int = 5, alpha: float = 0.35) -> None:
        self.window_size = max(1, window_size)
        self.alpha = min(max(alpha, 0.0), 1.0)
        self.history_x: Deque[float] = deque(maxlen=self.window_size)
        self.history_y: Deque[float] = deque(maxlen=self.window_size)
        self.prev_x: float | None = None
        self.prev_y: float | None = None

    def smooth(self, x: float, y: float) -> Tuple[int, int]:
        """Return smoothed integer cursor coordinates."""
        self.history_x.append(x)
        self.history_y.append(y)

        avg_x = sum(self.history_x) / len(self.history_x)
        avg_y = sum(self.history_y) / len(self.history_y)

        if self.prev_x is None or self.prev_y is None:
            self.prev_x, self.prev_y = avg_x, avg_y
        else:
            self.prev_x = self.prev_x + self.alpha * (avg_x - self.prev_x)
            self.prev_y = self.prev_y + self.alpha * (avg_y - self.prev_y)

        return int(self.prev_x), int(self.prev_y)
