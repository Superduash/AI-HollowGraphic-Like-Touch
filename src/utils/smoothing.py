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

    __slots__ = ("alpha_slow", "alpha_fast", "speed_threshold", "x", "y", "initialized")

    def __init__(self, alpha_slow: float = 0.25, alpha_fast: float = 0.70, speed_threshold: float = 50.0) -> None:
        self.alpha_slow = float(alpha_slow)
        self.alpha_fast = float(alpha_fast)
        self.speed_threshold = max(1e-6, float(speed_threshold))
        self.x = 0.0
        self.y = 0.0
        self.initialized = False

    def _alpha(self, speed: float) -> float:
        if speed <= 0.0:
            return self.alpha_slow
        t = min(1.0, speed / self.speed_threshold)
        return self.alpha_slow + (self.alpha_fast - self.alpha_slow) * t

    def filter(self, x: float, y: float, speed: float) -> tuple[float, float]:
        if not self.initialized:
            self.initialized = True
            self.x = float(x)
            self.y = float(y)
            return self.x, self.y

        a = self._alpha(speed)
        self.x += a * (float(x) - self.x)
        self.y += a * (float(y) - self.y)
        return self.x, self.y

    def reset(self) -> None:
        self.initialized = False
        self.x = 0.0
        self.y = 0.0


class Kalman1D:
    __slots__ = ("q", "r", "x", "p", "initialized")

    def __init__(self, process_noise: float = 0.02, measurement_noise: float = 2.5) -> None:
        self.q = float(process_noise)
        self.r = float(measurement_noise)
        self.x = 0.0
        self.p = 1.0
        self.initialized = False

    def filter(self, measurement: float) -> float:
        z = float(measurement)
        if not self.initialized:
            self.initialized = True
            self.x = z
            self.p = 1.0
            return self.x

        self.p = self.p + self.q
        k = self.p / (self.p + self.r)
        self.x = self.x + k * (z - self.x)
        self.p = (1.0 - k) * self.p
        return self.x

    def reset(self) -> None:
        self.initialized = False
        self.x = 0.0
        self.p = 1.0


class Kalman2D:
    __slots__ = ("_kx", "_ky")

    def __init__(self, process_noise: float = 0.02, measurement_noise: float = 2.5) -> None:
        self._kx = Kalman1D(process_noise=process_noise, measurement_noise=measurement_noise)
        self._ky = Kalman1D(process_noise=process_noise, measurement_noise=measurement_noise)

    def filter(self, x: float, y: float) -> tuple[float, float]:
        return self._kx.filter(x), self._ky.filter(y)

    def reset(self) -> None:
        self._kx.reset()
        self._ky.reset()


class MotionPredictor2D:
    __slots__ = ("_prev_x", "_prev_y", "_has_prev")

    def __init__(self) -> None:
        self._prev_x = 0.0
        self._prev_y = 0.0
        self._has_prev = False

    def predict(self, x: float, y: float, factor: float = 0.1) -> tuple[float, float, float, float]:
        fx = float(x)
        fy = float(y)
        if not self._has_prev:
            self._has_prev = True
            self._prev_x = fx
            self._prev_y = fy
            return fx, fy, 0.0, 0.0

        vx = fx - self._prev_x
        vy = fy - self._prev_y
        self._prev_x = fx
        self._prev_y = fy
        return fx + vx * factor, fy + vy * factor, vx, vy

    def reset(self) -> None:
        self._has_prev = False
        self._prev_x = 0.0
        self._prev_y = 0.0


# Backward-compatible alias.
CursorSmoother = AdaptiveExponentialSmoother2D
