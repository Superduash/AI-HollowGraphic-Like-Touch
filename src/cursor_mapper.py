from __future__ import annotations

import ctypes
import math


class CursorMapper:
    def __init__(self, cam_w: int, cam_h: int) -> None:
        self.cam_w = cam_w
        self.cam_h = cam_h

        user32 = ctypes.windll.user32
        self._screen_x = user32.GetSystemMetrics(76)
        self._screen_y = user32.GetSystemMetrics(77)
        self.scr_w = max(1, user32.GetSystemMetrics(78) - 1)
        self.scr_h = max(1, user32.GetSystemMetrics(79) - 1)

        self.frame_r = 90
        self.smoothening = 4.8

        self._ploc_x = -1.0
        self._ploc_y = -1.0
        self._exp_x = -1.0
        self._exp_y = -1.0
        self._kalman_x = -1.0
        self._kalman_y = -1.0
        self._kalman_gain = 0.52

    def set_camera_size(self, w: int, h: int) -> None:
        self.cam_w = max(1, int(w))
        self.cam_h = max(1, int(h))

    def control_region(self) -> tuple[int, int, int, int]:
        x1 = self.frame_r
        y1 = self.frame_r
        x2 = max(self.frame_r + 1, self.cam_w - self.frame_r)
        y2 = max(self.frame_r + 1, self.cam_h - self.frame_r)
        return x1, y1, x2, y2

    @staticmethod
    def _interp(v: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
        if in_max <= in_min:
            return out_min
        t = max(0.0, min(1.0, (v - in_min) / (in_max - in_min)))
        return out_min + t * (out_max - out_min)

    def reset(self) -> None:
        self._ploc_x = self._ploc_y = -1.0
        self._exp_x = self._exp_y = -1.0
        self._kalman_x = self._kalman_y = -1.0

    def map_point(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        # Map center 80% of camera region to the full virtual desktop.
        x1, y1, x2, y2 = self.control_region()

        if cam_x < x1 or cam_x > x2 or cam_y < y1 or cam_y > y2:
            if self._kalman_x >= 0:
                return int(self._kalman_x), int(self._kalman_y)
            return int(self._screen_x + self.scr_w // 2), int(self._screen_y + self.scr_h // 2)

        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        hw, hh = (x2 - x1) * 0.4, (y2 - y1) * 0.4
        map_x1, map_x2 = cx - hw, cx + hw
        map_y1, map_y2 = cy - hh, cy + hh

        x3 = self._interp(cam_x, map_x1, map_x2, float(self._screen_x), float(self._screen_x + self.scr_w))
        y3 = self._interp(cam_y, map_y1, map_y2, float(self._screen_y), float(self._screen_y + self.scr_h))

        x3 = max(float(self._screen_x), min(float(self._screen_x + self.scr_w), x3))
        y3 = max(float(self._screen_y), min(float(self._screen_y + self.scr_h), y3))

        if self._ploc_x < 0:
            self._ploc_x, self._ploc_y = x3, y3
            self._exp_x, self._exp_y = x3, y3
            self._kalman_x, self._kalman_y = x3, y3
            return int(x3), int(y3)

        dx = x3 - self._ploc_x
        dy = y3 - self._ploc_y
        d2 = dx * dx + dy * dy
        if d2 < 4:
            return int(self._kalman_x), int(self._kalman_y)

        cloc_x = self._ploc_x + dx / self.smoothening
        cloc_y = self._ploc_y + dy / self.smoothening

        speed = math.sqrt(d2)
        alpha = 0.25 if speed < 20 else 0.7
        self._exp_x = self._exp_x + alpha * (cloc_x - self._exp_x)
        self._exp_y = self._exp_y + alpha * (cloc_y - self._exp_y)

        self._kalman_x = self._kalman_x + self._kalman_gain * (self._exp_x - self._kalman_x)
        self._kalman_y = self._kalman_y + self._kalman_gain * (self._exp_y - self._kalman_y)

        self._ploc_x, self._ploc_y = cloc_x, cloc_y
        return int(self._kalman_x), int(self._kalman_y)