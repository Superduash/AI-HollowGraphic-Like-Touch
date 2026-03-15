"""Map camera-space coordinates to screen-space coordinates."""

from typing import Tuple

import numpy as np

from utils.math_utils import clamp


class CursorMapper:
    """Convert webcam pixel coordinates to display coordinates."""

    def __init__(self, cam_width: int, cam_height: int, screen_width: int, screen_height: int) -> None:
        self.cam_width = cam_width
        self.cam_height = cam_height
        self.screen_width = screen_width
        self.screen_height = screen_height

    def map_to_screen(self, cam_x: int, cam_y: int) -> Tuple[int, int]:
        """Interpolate camera coordinate onto screen resolution."""
        clamped_x = clamp(cam_x, 0, self.cam_width)
        clamped_y = clamp(cam_y, 0, self.cam_height)

        screen_x = np.interp(clamped_x, [0, self.cam_width], [0, self.screen_width - 1])
        screen_y = np.interp(clamped_y, [0, self.cam_height], [0, self.screen_height - 1])

        return int(screen_x), int(screen_y)
