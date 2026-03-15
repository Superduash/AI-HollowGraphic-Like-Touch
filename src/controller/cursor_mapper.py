"""Map camera-space coordinates to screen-space (pure Python, no numpy)."""

from utils.math_utils import clamp


class CursorMapper:
    """Convert process-frame pixel coordinates to display coordinates."""

    __slots__ = ("cam_w", "cam_h", "scr_w", "scr_h", "scale_x", "scale_y")

    def __init__(self, cam_width: int, cam_height: int, screen_width: int, screen_height: int) -> None:
        self.cam_w = cam_width
        self.cam_h = cam_height
        self.scr_w = screen_width - 1
        self.scr_h = screen_height - 1
        # Pre-compute scale factors once
        self.scale_x = self.scr_w / cam_width if cam_width else 1.0
        self.scale_y = self.scr_h / cam_height if cam_height else 1.0

    def map_to_screen(self, cam_x: int, cam_y: int) -> tuple[int, int]:
        sx = clamp(cam_x, 0, self.cam_w) * self.scale_x
        sy = clamp(cam_y, 0, self.cam_h) * self.scale_y
        return int(sx), int(sy)
