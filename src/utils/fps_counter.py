"""Simple FPS counter utility."""

import time


class FPSCounter:
    """Track frames-per-second with a lightweight moving estimate."""

    def __init__(self) -> None:
        self.prev_time = time.time()
        self.fps = 0.0

    def update(self) -> float:
        """Update and return the current FPS estimate."""
        current_time = time.time()
        delta = current_time - self.prev_time
        self.prev_time = current_time

        if delta > 0:
            instant_fps = 1.0 / delta
            if self.fps == 0.0:
                self.fps = instant_fps
            else:
                self.fps = (0.9 * self.fps) + (0.1 * instant_fps)

        return self.fps
