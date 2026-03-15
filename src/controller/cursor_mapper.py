"""Map camera-space coordinates to screen-space (pure Python, no numpy)."""

import math

from utils.math_utils import clamp


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
        "_kalman_x",
        "_kalman_y",
        "_kalman_gain",
    )

    def __init__(self, cam_width: int, cam_height: int, screen_width: int, screen_height: int) -> None:
        self.cam_w = cam_width
        self.cam_h = cam_height
        self.scr_w = screen_width - 1
        self.scr_h = screen_height - 1
        self.frame_r = 100
        self.smoothening = 7.0
        self._ploc_x = -1.0
        self._ploc_y = -1.0
        self._cloc_x = -1.0
        self._cloc_y = -1.0
        self._kalman_x = -1.0
        self._kalman_y = -1.0
        self._kalman_gain = 0.45

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
        self._kalman_x = -1.0
        self._kalman_y = -1.0

    def _interp(self, value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        if in_max <= in_min:
            return out_min
        t = (value - in_min) / (in_max - in_min)
        t = clamp(t, 0.0, 1.0)
        return out_min + t * (out_max - out_min)

    def map_to_screen(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        x1, y1, x2, y2 = self.control_region()

        if cam_x < x1 or cam_x > x2 or cam_y < y1 or cam_y > y2:
            if self._kalman_x >= 0:
                return int(self._kalman_x), int(self._kalman_y)
            return int(self.scr_w // 2), int(self.scr_h // 2)

        x3 = self._interp(cam_x, x1, x2, 0.0, float(self.scr_w))
        y3 = self._interp(cam_y, y1, y2, 0.0, float(self.scr_h))

        if self._ploc_x < 0:
            self._ploc_x, self._ploc_y = x3, y3
            self._cloc_x, self._cloc_y = x3, y3
            self._kalman_x, self._kalman_y = x3, y3
            return int(x3), int(y3)

        # Movement dampening for tiny motions.
        if abs(x3 - self._ploc_x) < 2.0 and abs(y3 - self._ploc_y) < 2.0:
            return int(self._kalman_x), int(self._kalman_y)

        # Reference-style smoothing.
        self._cloc_x = self._ploc_x + (x3 - self._ploc_x) / self.smoothening
        self._cloc_y = self._ploc_y + (y3 - self._ploc_y) / self.smoothening

        # Piecewise movement dampening/boosting.
        dx = self._cloc_x - self._ploc_x
        dy = self._cloc_y - self._ploc_y
        distsq = dx * dx + dy * dy
        if distsq <= 25.0:
            ratio = 0.0
        elif distsq <= 900.0:
            ratio = 0.07 * math.sqrt(distsq)
        else:
            ratio = 2.1

        damp_x = self._ploc_x + dx * ratio
        damp_y = self._ploc_y + dy * ratio

        # Kalman-style single-state filtering stage.
        self._kalman_x = self._kalman_x + self._kalman_gain * (damp_x - self._kalman_x)
        self._kalman_y = self._kalman_y + self._kalman_gain * (damp_y - self._kalman_y)

        self._ploc_x, self._ploc_y = damp_x, damp_y
        return int(self._kalman_x), int(self._kalman_y)
