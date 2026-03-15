"""Lightweight FPS counter with frame-skip advisory."""

import time


class FPSCounter:
    """Track FPS and advise whether to skip processing to maintain target."""

    __slots__ = ("prev_time", "fps", "target_fps")

    def __init__(self, target_fps: float = 60.0) -> None:
        self.prev_time = time.monotonic()
        self.fps = 0.0
        self.target_fps = target_fps

    def update(self) -> float:
        now = time.monotonic()
        delta = now - self.prev_time
        self.prev_time = now
        if delta > 0.0:
            instant = 1.0 / delta
            self.fps = instant if self.fps == 0.0 else 0.9 * self.fps + 0.1 * instant
        return self.fps

    def should_skip(self) -> bool:
        """Return True when FPS is significantly below target."""
        return 0.0 < self.fps < self.target_fps * 0.75
