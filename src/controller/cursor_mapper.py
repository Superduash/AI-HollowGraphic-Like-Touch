"""Map camera-space coordinates to screen-space (pure Python, no numpy)."""

import math

from config import (
    ALPHA_FAST,
    ALPHA_SLOW,
    CURSOR_DEADZONE_PX,
    CURSOR_PREDICTION_SECONDS,
    CURSOR_MOVE_THRESHOLD,
    SPEED_THRESHOLD,
)
from utils.math_utils import clamp
from utils.smoothing import AdaptiveExponentialSmoother2D, DeadzoneFilter2D


class CursorMapper:
    """Convert process-frame pixel coordinates to display coordinates."""

    __slots__ = (
        "cam_w",
        "cam_h",
        "scr_w",
        "scr_h",
        "frame_r",
        "smoothening",
        "_ploc_x",
        "_ploc_y",
        "_cloc_x",
        "_cloc_y",
        "_out_x",
        "_out_y",
        "_vel_x",
        "_vel_y",
        "_deadzone_filter",
        "_exp_smoother",
        "_stationary_threshold_sq",
    )

    def __init__(self, cam_width: int, cam_height: int, screen_width: int, screen_height: int) -> None:
        self.cam_w = cam_width
        self.cam_h = cam_height
        self.scr_w = screen_width - 1
        self.scr_h = screen_height - 1
        self.frame_r = 100
        self.smoothening = 3.0
        self._ploc_x = -1.0
        self._ploc_y = -1.0
        self._cloc_x = -1.0
        self._cloc_y = -1.0
        self._out_x = -1.0
        self._out_y = -1.0
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._deadzone_filter = DeadzoneFilter2D(radius=float(CURSOR_DEADZONE_PX))
        self._exp_smoother = AdaptiveExponentialSmoother2D(
            alpha_slow=ALPHA_SLOW,
            alpha_fast=ALPHA_FAST,
            speed_threshold=SPEED_THRESHOLD,
        )
        self._stationary_threshold_sq = float(max(3, int(CURSOR_MOVE_THRESHOLD)) ** 2)

    def set_camera_size(self, cam_width: int, cam_height: int) -> None:
        """Update source frame size for accurate runtime mapping."""
        if cam_width <= 0 or cam_height <= 0:
            return
        self.cam_w = cam_width
        self.cam_h = cam_height

    def control_region(self) -> tuple[int, int, int, int]:
        x1 = self.frame_r
        y1 = self.frame_r
        x2 = max(self.frame_r + 1, self.cam_w - self.frame_r)
        y2 = max(self.frame_r + 1, self.cam_h - self.frame_r)
        return x1, y1, x2, y2

    def reset(self) -> None:
        self._ploc_x = -1.0
        self._ploc_y = -1.0
        self._cloc_x = -1.0
        self._cloc_y = -1.0
        self._out_x = -1.0
        self._out_y = -1.0
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._exp_smoother.reset()

    def _interp(self, value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        if in_max <= in_min:
            return out_min
        t = (value - in_min) / (in_max - in_min)
        t = clamp(t, 0.0, 1.0)
        return out_min + t * (out_max - out_min)

    def map_to_screen(self, cam_x: int, cam_y: int, hand_center: tuple[int, int] | None = None) -> tuple[int, int]:
        x1, y1, x2, y2 = self.control_region()

        if cam_x < x1 or cam_x > x2 or cam_y < y1 or cam_y > y2:
            if self._out_x >= 0:
                py = self._out_y
                px = self._out_x
                return int(clamp(px, 0.0, float(self.scr_w))), int(clamp(py, 0.0, float(self.scr_h)))
            return int(self.scr_w // 2), int(self.scr_h // 2)

        x3 = self._interp(float(cam_x), x1, x2, 0.0, float(self.scr_w))
        y3 = self._interp(float(cam_y), y1, y2, 0.0, float(self.scr_h))

        if hand_center is not None:
            cx3 = self._interp(float(hand_center[0]), x1, x2, 0.0, float(self.scr_w))
            cy3 = self._interp(float(hand_center[1]), y1, y2, 0.0, float(self.scr_h))
            target_x = 0.78 * x3 + 0.22 * cx3
            target_y = 0.78 * y3 + 0.22 * cy3
        else:
            target_x, target_y = x3, y3

        if self._out_x < 0:
            self._ploc_x = target_x
            self._ploc_y = target_y
            self._cloc_x = target_x
            self._cloc_y = target_y
            self._out_x = target_x
            self._out_y = target_y
            return int(target_x), int(target_y)

        # Stage 1: deadzone filter.
        dx_raw = target_x - self._ploc_x
        dy_raw = target_y - self._ploc_y
        if not self._deadzone_filter.apply(dx_raw, dy_raw):
            return int(self._out_x), int(self._out_y)

        # Stage 2: adaptive exponential smoothing.
        speed_sq = dx_raw * dx_raw + dy_raw * dy_raw
        sx, sy = self._exp_smoother.filter(target_x, target_y, speed_sq)

        nx = clamp(sx, 0.0, float(self.scr_w))
        ny = clamp(sy, 0.0, float(self.scr_h))

        # Additional stationary threshold to suppress residual jitter.
        ddx = nx - self._out_x
        ddy = ny - self._out_y
        if ddx * ddx + ddy * ddy < self._stationary_threshold_sq:
            self._ploc_x = target_x
            self._ploc_y = target_y
            return int(self._out_x), int(self._out_y)

        self._vel_x = ddx
        self._vel_y = ddy

        self._ploc_x = target_x
        self._ploc_y = target_y
        self._out_x, self._out_y = nx, ny
        return int(nx), int(ny)

    @property
    def velocity(self) -> tuple[float, float]:
        return self._vel_x, self._vel_y
