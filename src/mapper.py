import math


class CursorMapper:
    def __init__(self, cam_w: int, cam_h: int, scr_w: int, scr_h: int) -> None:
        self.cam_w = cam_w
        self.cam_h = cam_h
        self.scr_w = scr_w - 1
        self.scr_h = scr_h - 1

        self.frame_r = 90
        # Lower smoothing => more responsive.
        self.smoothening = 4.8

        self._ploc_x = -1.0
        self._ploc_y = -1.0
        self._cloc_x = -1.0
        self._cloc_y = -1.0

        self._exp_x = -1.0
        self._exp_y = -1.0

        self._kalman_x = -1.0
        self._kalman_y = -1.0
        self._kalman_gain = 0.52

    def set_camera_size(self, w: int, h: int) -> None:
        self.cam_w = max(1, w)
        self.cam_h = max(1, h)

    def control_region(self):
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
        self._cloc_x = self._cloc_y = -1.0
        self._exp_x = self._exp_y = -1.0
        self._kalman_x = self._kalman_y = -1.0

    def map_point(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        x1, y1, x2, y2 = self.control_region()

        if cam_x < x1 or cam_x > x2 or cam_y < y1 or cam_y > y2:
            if self._kalman_x >= 0:
                return int(self._kalman_x), int(self._kalman_y)
            return int(self.scr_w // 2), int(self.scr_h // 2)

        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        hw, hh = (x2 - x1) * 0.425, (y2 - y1) * 0.425
        map_x1, map_x2 = cx - hw, cx + hw
        map_y1, map_y2 = cy - hh, cy + hh

        x3 = self._interp(cam_x, map_x1, map_x2, 0.0, float(self.scr_w))
        y3 = self._interp(cam_y, map_y1, map_y2, 0.0, float(self.scr_h))
        
        x3 = max(0.0, min(float(self.scr_w), x3))
        y3 = max(0.0, min(float(self.scr_h), y3))

        if self._ploc_x < 0:
            self._ploc_x, self._ploc_y = x3, y3
            self._cloc_x, self._cloc_y = x3, y3
            self._exp_x, self._exp_y = x3, y3
            self._kalman_x, self._kalman_y = x3, y3
            return int(x3), int(y3)

        if abs(x3 - self._ploc_x) < 2 and abs(y3 - self._ploc_y) < 2:
            return int(self._kalman_x), int(self._kalman_y)

        self._cloc_x = self._ploc_x + (x3 - self._ploc_x) / self.smoothening
        self._cloc_y = self._ploc_y + (y3 - self._ploc_y) / self.smoothening

        dx = self._cloc_x - self._ploc_x
        dy = self._cloc_y - self._ploc_y
        d2 = dx * dx + dy * dy

        if d2 <= 25:
            ratio = 0.0
        elif d2 <= 900:
            ratio = 0.07 * math.sqrt(d2)
        else:
            ratio = 2.1

        damp_x = self._ploc_x + dx * ratio
        damp_y = self._ploc_y + dy * ratio

        speed = math.sqrt(d2)
        alpha = 0.25 if speed < 20 else 0.7
        self._exp_x = self._exp_x + alpha * (damp_x - self._exp_x)
        self._exp_y = self._exp_y + alpha * (damp_y - self._exp_y)

        self._kalman_x = self._kalman_x + self._kalman_gain * (self._exp_x - self._kalman_x)
        self._kalman_y = self._kalman_y + self._kalman_gain * (self._exp_y - self._kalman_y)

        self._ploc_x, self._ploc_y = damp_x, damp_y
        return int(self._kalman_x), int(self._kalman_y)
