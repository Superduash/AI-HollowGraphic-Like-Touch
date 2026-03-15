"""Adaptive cursor smoothing with motion prediction and acceleration curve."""

from config import ALPHA_SLOW, ALPHA_FAST, SPEED_THRESHOLD


class AdaptiveSmoother:
    """Speed-adaptive exponential smoothing with optional acceleration.

    Slow movement → strong smoothing (jitter removal)
    Fast movement → light smoothing (responsiveness)
    Optional acceleration curve for large, fast movements.
    """
    __slots__ = (
        "a_slow",
        "a_fast",
        "speed_t",
        "px",
        "py",
        "vx",
        "vy",
        "accel_factor",
        "accel_thresh",
        "deadzone",
        "max_boost",
    )

    def __init__(self, alpha_slow=ALPHA_SLOW, alpha_fast=ALPHA_FAST,
                 speed_threshold=SPEED_THRESHOLD,
                 accel_factor=1.35, accel_threshold=80.0,
                 deadzone=4.0, max_boost=1.8):
        self.a_slow = alpha_slow
        self.a_fast = alpha_fast
        self.speed_t = speed_threshold
        self.accel_factor = accel_factor    # multiplier for fast large moves
        self.accel_thresh = accel_threshold  # speed above which acceleration kicks in
        self.deadzone = deadzone
        self.max_boost = max_boost
        self.px = -1.0
        self.py = -1.0
        self.vx = 0.0
        self.vy = 0.0

    def smooth(self, x: float, y: float) -> tuple[int, int]:
        if self.px < 0:
            self.px, self.py = x, y
            self.vx = self.vy = 0.0
            return int(x), int(y)

        dx, dy = x - self.px, y - self.py
        speed = (dx * dx + dy * dy) ** 0.5

        # Ignore tiny micro-movements to suppress jitter.
        if speed < self.deadzone:
            self.vx = 0.0
            self.vy = 0.0
            return int(self.px), int(self.py)

        # Adaptive alpha
        if speed >= self.speed_t:
            a = self.a_fast
        else:
            t = speed / self.speed_t if self.speed_t > 0 else 1.0
            a = self.a_slow + t * (self.a_fast - self.a_slow)

        # Acceleration curve: boost large fast movements
        if speed > self.accel_thresh:
            overshoot = (speed - self.accel_thresh) / self.accel_thresh
            boost = 1.0 + overshoot * (self.accel_factor - 1.0)
            boost = min(boost, self.max_boost)
            dx *= boost
            dy *= boost

        ox, oy = self.px, self.py
        self.px += a * dx
        self.py += a * dy
        self.vx = self.px - ox
        self.vy = self.py - oy
        return int(self.px), int(self.py)

    def predict(self, factor: float = 0.5) -> tuple[int, int]:
        """Predict next position using current velocity."""
        if self.px < 0:
            return -1, -1
        return int(self.px + self.vx * factor), int(self.py + self.vy * factor)

    def reset(self):
        self.px = self.py = -1.0
        self.vx = self.vy = 0.0


# Backward-compatible alias
CursorSmoother = AdaptiveSmoother
