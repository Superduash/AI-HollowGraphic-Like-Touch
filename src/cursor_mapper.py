from __future__ import annotations

import math
import platform

try:
    from .fast_math import ema_step, clamp, map_range
except Exception:
    def ema_step(prev: float, target: float, alpha: float) -> float:
        return prev + alpha * (target - prev)

    def clamp(value: float, lo: float, hi: float) -> float:
        if value < lo:
            return lo
        if value > hi:
            return hi
        return value

    def map_range(value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> float:
        if in_hi == in_lo:
            return out_lo
        t = (value - in_lo) / (in_hi - in_lo)
        return out_lo + t * (out_hi - out_lo)
from .tuning import (
    CURSOR_INNER_RATIO,
    CURSOR_SOFT_DEADZONE_PX,
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
        self._initialized = False
        self._prev_flt_x: float = -1.0
        self._prev_flt_y: float = -1.0
        self._pred_strength: float = 0.45   # 0=no prediction, 1=full 1-frame lookahead

        self._deadzone_px = float(CURSOR_SOFT_DEADZONE_PX)
        self._alpha_min = 0.25
        self._alpha_max = 0.72
        self._inner_ratio = CURSOR_INNER_RATIO
        self._max_inner_margin_ratio = 0.35
        self._inner_margin_ratio = (1.0 - self._inner_ratio) * 0.5
        self._margin_x_ratio = self._inner_margin_ratio
        self._margin_y_ratio = self._inner_margin_ratio
        self._inner_x_ratio = self._inner_ratio
        self._inner_y_ratio = self._inner_ratio
        self._hand_scale_px = 32.0
        import threading as _th
        self._mapper_lock = _th.Lock()
        # Face tracking: slower EMA for stable nose movements
        self._alpha_min_face: float = 0.18
        self._alpha_max_face: float = 0.60
        # Hand-only: faster EMA for fingertip responsiveness
        self._alpha_min_hand: float = 0.28
        self._alpha_max_hand: float = 0.75
        self._hand_only_mode: bool = False

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
        with self._mapper_lock:
            self.smoothening = v
            t = (v - 1.0) / 9.0
            # Scale within the tuned range — never go below the tuned min
            self._alpha_min_face = 0.18 + t * 0.07
            self._alpha_max_face = 0.60 + t * 0.10
            self._alpha_min_hand = 0.28 + t * 0.07
            self._alpha_max_hand = 0.75 + t * 0.10
            self._alpha_min = self._alpha_min_face
            self._alpha_max = self._alpha_max_face

    def set_prediction_strength(self, v: float) -> None:
        """0.0 = no prediction (pure follow), 1.0 = full velocity lookahead."""
        self._pred_strength = max(0.0, min(1.0, float(v)))

    def set_frame_margin(self, margin_px: int) -> None:
        with self._mapper_lock:
            self.frame_r = max(0, min(int(margin_px), self.max_effective_margin_px()))
            if self.cam_w <= 1 or self.cam_h <= 1:
                return
            self._margin_x_ratio = max(0.0, min(self._max_inner_margin_ratio,
                                                self.frame_r / float(self.cam_w)))
            self._margin_y_ratio = max(0.0, min(self._max_inner_margin_ratio,
                                                self.frame_r / float(self.cam_h)))
            self._inner_x_ratio = max(0.20, 1.0 - 2.0 * self._margin_x_ratio)
            self._inner_y_ratio = max(0.20, 1.0 - 2.0 * self._margin_y_ratio)
            # keep legacy vars in sync for compatibility
            self._inner_margin_ratio = self._margin_y_ratio
            self._inner_ratio = self._inner_y_ratio

    def max_effective_margin_px(self) -> int:
        px = float(min(self.cam_w, self.cam_h))
        if px <= 1.0:
            return 0
        return int(px * self._max_inner_margin_ratio)

    def set_hand_scale(self, hand_scale_px: float) -> None:
        self._hand_scale_px = max(8.0, float(hand_scale_px))

    def control_region(self) -> tuple[int, int, int, int]:
        left = int(round(self.cam_w * self._margin_x_ratio))
        right = int(round(self.cam_w * (1.0 - self._margin_x_ratio))) - 1
        top = int(round(self.cam_h * self._margin_y_ratio))
        bottom = int(round(self.cam_h * (1.0 - self._margin_y_ratio))) - 1
        return max(0, left), max(0, top), min(self.cam_w - 1, right), min(self.cam_h - 1, bottom)

    def reset(self) -> None:
        self._raw_x = -1.0
        self._raw_y = -1.0
        self._flt_x = -1.0
        self._flt_y = -1.0
        self._prev_flt_x = -1.0
        self._prev_flt_y = -1.0
        self._initialized = False

    def _map_to_screen(self, cam_x: int, cam_y: int) -> tuple[float, float]:
        raw_nx = clamp(float(cam_x) / float(max(1, self.cam_w - 1)), 0.0, 1.0)
        raw_ny = clamp(float(cam_y) / float(max(1, self.cam_h - 1)), 0.0, 1.0)

        nx = map_range(raw_nx, self._margin_x_ratio,
                       self._margin_x_ratio + self._inner_x_ratio, 0.0, 1.0)
        ny = map_range(raw_ny, self._margin_y_ratio,
                       self._margin_y_ratio + self._inner_y_ratio, 0.0, 1.0)
        nx = clamp(nx, 0.0, 1.0)
        ny = clamp(ny, 0.0, 1.0)

        sx = float(self._screen_x) + nx * float(self.scr_w)
        sy = float(self._screen_y) + ny * float(self.scr_h)
        return sx, sy

    def map_point(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        raw_x, raw_y = self._map_to_screen(cam_x, cam_y)
        true_raw_x = raw_x
        true_raw_y = raw_y

        if not self._initialized:
            self._raw_x = raw_x
            self._raw_y = raw_y
            self._flt_x = raw_x
            self._flt_y = raw_y
            self._initialized = True
            return int(raw_x), int(raw_y)

        prev_raw_x = self._raw_x
        prev_raw_y = self._raw_y
        dx = raw_x - prev_raw_x
        dy = raw_y - prev_raw_y
        speed = math.sqrt(dx * dx + dy * dy)

        # Soft deadzone: suppress micro-jitter without fully blocking intentional movement.
        if speed < self._deadzone_px:
            scale = (speed / self._deadzone_px) ** 2
            raw_x = prev_raw_x + dx * scale
            raw_y = prev_raw_y + dy * scale
            dx = raw_x - prev_raw_x
            dy = raw_y - prev_raw_y
            speed = math.sqrt(dx * dx + dy * dy)

        # Store the true (non-deadzoned) raw point for consistent speed tracking.
        self._raw_x = true_raw_x
        self._raw_y = true_raw_y

        screen_norm = max(60.0, math.sqrt(float(self.scr_w * self.scr_w + self.scr_h * self.scr_h)) * CURSOR_SPEED_NORM_RATIO)
        v_norm = min(1.0, speed / screen_norm)
        with self._mapper_lock:
            if self._hand_only_mode:
                amin, amax = self._alpha_min_hand, self._alpha_max_hand
            else:
                amin, amax = self._alpha_min_face, self._alpha_max_face
        alpha = amin + v_norm * (amax - amin)

        # Clamp max single-frame jump to 15% of screen diagonal to
        # absorb landmark teleport caused by blur/fast motion.
        scr_diag = math.sqrt(float(self.scr_w ** 2 + self.scr_h ** 2))
        max_jump = scr_diag * 0.08
        jump_dx = raw_x - self._flt_x
        jump_dy = raw_y - self._flt_y
        jump_dist = math.sqrt(jump_dx * jump_dx + jump_dy * jump_dy)
        if jump_dist > max_jump and max_jump > 0:
            scale = max_jump / jump_dist
            raw_x = self._flt_x + jump_dx * scale
            raw_y = self._flt_y + jump_dy * scale

        self._flt_x = ema_step(self._flt_x, raw_x, alpha)
        self._flt_y = ema_step(self._flt_y, raw_y, alpha)

        # Velocity extrapolation: predict next position from current velocity.
        # Uses exponentially smoothed filtered position to avoid amplifying noise.
        if self._initialized and self._prev_flt_x >= 0:
            vx = self._flt_x - self._prev_flt_x
            vy = self._flt_y - self._prev_flt_y
            pred_x = self._flt_x + vx * self._pred_strength
            pred_y = self._flt_y + vy * self._pred_strength
        else:
            pred_x = self._flt_x
            pred_y = self._flt_y

        self._prev_flt_x = self._flt_x
        self._prev_flt_y = self._flt_y

        return int(pred_x), int(pred_y)
