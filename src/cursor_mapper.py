from __future__ import annotations

import math
import platform

from .tuning import (
    CURSOR_DEADZONE_BASE,
    CURSOR_DEADZONE_SCALE_FACTOR,
    CURSOR_INNER_RATIO,
    CURSOR_SPEED_NORM_RATIO,
)


class CursorMapper:
    def __init__(self, cam_w: int, cam_h: int) -> None:
        self.cam_w = max(1, cam_w)
        self.cam_h = max(1, cam_h)

        self._screen_x, self._screen_y, self.scr_w, self.scr_h = self._virtual_screen_bounds()

        # Kept for compatibility with the existing settings dialog.
        self.frame_r = 0
        self.smoothening = 3.0

        self._raw_x = -1.0
        self._raw_y = -1.0
        self._flt_x = -1.0
        self._flt_y = -1.0

        self._deadzone_px = 2.0
        self._alpha_min = 0.08
        self._alpha_max = 0.52
        self._inner_ratio = CURSOR_INNER_RATIO
        self._inner_margin_ratio = (1.0 - self._inner_ratio) * 0.5
        self._hand_scale_px = 32.0

    @staticmethod
    def _virtual_screen_bounds() -> tuple[int, int, int, int]:
        if platform.system() == "Windows":
            try:
                import ctypes

                user32 = ctypes.windll.user32
                sx = int(user32.GetSystemMetrics(76))
                sy = int(user32.GetSystemMetrics(77))
                sw = max(1, int(user32.GetSystemMetrics(78) - sx - 1))
                sh = max(1, int(user32.GetSystemMetrics(79) - sy - 1))
                return sx, sy, sw, sh
            except Exception:
                pass

        if platform.system() == "Darwin":
            try:
                import Quartz  # type: ignore[import-not-found]

                max_displays = 16
                active = Quartz.CGGetActiveDisplayList(max_displays, None, None)
                if isinstance(active, tuple) and len(active) >= 2:
                    display_ids = active[1]
                else:
                    display_ids = []
                if display_ids:
                    min_x = 10**9
                    min_y = 10**9
                    max_x = -10**9
                    max_y = -10**9
                    for did in display_ids:
                        bounds = Quartz.CGDisplayBounds(did)
                        x = int(bounds.origin.x)
                        y = int(bounds.origin.y)
                        w = int(bounds.size.width)
                        h = int(bounds.size.height)
                        min_x = min(min_x, x)
                        min_y = min(min_y, y)
                        max_x = max(max_x, x + w)
                        max_y = max(max_y, y + h)
                    return min_x, min_y, max(1, max_x - min_x), max(1, max_y - min_y)
            except Exception:
                pass

        return 0, 0, 1920, 1080

    def set_camera_size(self, w: int, h: int) -> None:
        self.cam_w = max(1, int(w))
        self.cam_h = max(1, int(h))
        self.set_frame_margin(self.frame_r)

    def set_smoothening(self, value: float) -> None:
        v = max(1.0, min(10.0, float(value)))
        self.smoothening = v
        t = (v - 1.0) / 9.0
        self._alpha_min = 0.06 + t * 0.14
        self._alpha_max = 0.40 + t * 0.30

    def set_frame_margin(self, margin_px: int) -> None:
        self.frame_r = max(0, int(margin_px))
        px = float(min(self.cam_w, self.cam_h))
        if px <= 1.0:
            return
        ratio = max(0.0, min(0.35, self.frame_r / px))
        self._inner_margin_ratio = ratio
        self._inner_ratio = max(0.30, 1.0 - (2.0 * self._inner_margin_ratio))

    def set_hand_scale(self, hand_scale_px: float) -> None:
        self._hand_scale_px = max(8.0, float(hand_scale_px))

    def control_region(self) -> tuple[int, int, int, int]:
        left = int(round(self.cam_w * self._inner_margin_ratio))
        right = int(round(self.cam_w * (1.0 - self._inner_margin_ratio))) - 1
        top = int(round(self.cam_h * self._inner_margin_ratio))
        bottom = int(round(self.cam_h * (1.0 - self._inner_margin_ratio))) - 1
        return max(0, left), max(0, top), min(self.cam_w - 1, right), min(self.cam_h - 1, bottom)

    def reset(self) -> None:
        self._raw_x = -1.0
        self._raw_y = -1.0
        self._flt_x = -1.0
        self._flt_y = -1.0

    def _map_to_screen(self, cam_x: int, cam_y: int) -> tuple[float, float]:
        raw_nx = max(0.0, min(1.0, float(cam_x) / float(max(1, self.cam_w - 1))))
        raw_ny = max(0.0, min(1.0, float(cam_y) / float(max(1, self.cam_h - 1))))

        nx = (raw_nx - self._inner_margin_ratio) / self._inner_ratio
        ny = (raw_ny - self._inner_margin_ratio) / self._inner_ratio
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))

        sx = float(self._screen_x) + nx * float(self.scr_w)
        sy = float(self._screen_y) + ny * float(self.scr_h)
        return sx, sy

    def map_point(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        raw_x, raw_y = self._map_to_screen(cam_x, cam_y)

        if self._raw_x < 0.0:
            self._raw_x = raw_x
            self._raw_y = raw_y
            self._flt_x = raw_x
            self._flt_y = raw_y
            return int(raw_x), int(raw_y)

        dx = raw_x - self._raw_x
        dy = raw_y - self._raw_y
        speed = math.sqrt(dx * dx + dy * dy)

        self._raw_x = raw_x
        self._raw_y = raw_y

        dynamic_deadzone = max(CURSOR_DEADZONE_BASE, self._deadzone_px, self._hand_scale_px * CURSOR_DEADZONE_SCALE_FACTOR)
        if speed <= dynamic_deadzone:
            return int(self._flt_x), int(self._flt_y)

        screen_norm = max(60.0, math.sqrt(float(self.scr_w * self.scr_w + self.scr_h * self.scr_h)) * CURSOR_SPEED_NORM_RATIO)
        v_norm = min(1.0, speed / screen_norm)
        alpha = self._alpha_min + v_norm * (self._alpha_max - self._alpha_min)

        self._flt_x = self._flt_x + alpha * (raw_x - self._flt_x)
        self._flt_y = self._flt_y + alpha * (raw_y - self._flt_y)

        return int(self._flt_x), int(self._flt_y)
