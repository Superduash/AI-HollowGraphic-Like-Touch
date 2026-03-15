"""Low-latency smoothing primitives for real-time cursor control."""

import math


class DeadzoneFilter2D:
    __slots__ = ("radius",)

    def __init__(self, radius: float = 2.0) -> None:
        self.radius = float(radius)

    def apply(self, dx: float, dy: float) -> bool:
        return (dx * dx + dy * dy) >= (self.radius * self.radius)


class AdaptiveExponentialSmoother2D:
    """Adaptive exponential smoothing with velocity-based alpha."""

    __slots__ = ("alpha_slow", "alpha_fast", "speed_threshold_sq", "x", "y", "initialized")

    def __init__(self, alpha_slow: float = 0.25, alpha_fast: float = 0.70, speed_threshold: float = 50.0) -> None:
        self.alpha_slow = float(alpha_slow)
        self.alpha_fast = float(alpha_fast)
        self.speed_threshold_sq = max(1e-12, float(speed_threshold) ** 2)
        self.x = 0.0
        self.y = 0.0
        self.initialized = False

    def _alpha(self, speed_sq: float) -> float:
        if speed_sq <= 0.0:
            return self.alpha_slow
        t = min(1.0, speed_sq / self.speed_threshold_sq)
        # Using sqrt here would undo the optimization, but to approximate t linearly with speed_sq:
        # Actually it's better to just interpolate with speed_sq directly for speed.
        return self.alpha_slow + (self.alpha_fast - self.alpha_slow) * t

    def filter(self, x: float, y: float, speed_sq: float) -> tuple[float, float]:
        if not self.initialized:
            self.initialized = True
            self.x = float(x)
            self.y = float(y)
            return self.x, self.y

        a = self._alpha(speed_sq)
        self.x += a * (float(x) - self.x)
        self.y += a * (float(y) - self.y)
        return self.x, self.y

    def reset(self) -> None:
        self.initialized = False
        self.x = 0.0
        self.y = 0.0


# Backward-compatible alias.
CursorSmoother = AdaptiveExponentialSmoother2D
