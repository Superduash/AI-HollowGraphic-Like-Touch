"""Mouse control: move, click, double-click, scroll, drag. Supports pydirectinput on Windows."""

import platform
import time
import pyautogui
from config import CLICK_COOLDOWN, CURSOR_MOVE_THRESHOLD

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# On Windows, prefer pydirectinput for lower-latency cursor updates.
_pdi = None
if platform.system() == "Windows":
    try:
        import pydirectinput
        pydirectinput.FAILSAFE = False
        pydirectinput.PAUSE = 0
        _pdi = pydirectinput
    except ImportError:
        pass


def _move(x, y):
    if _pdi:
        _pdi.moveTo(x, y)
    else:
        pyautogui.moveTo(x, y)


class MouseController:
    def __init__(self, cooldown=CLICK_COOLDOWN, threshold=CURSOR_MOVE_THRESHOLD):
        # Enforce required deadzone floor for jitter suppression.
        threshold = max(3, int(threshold))
        self.thresh_sq = threshold * threshold
        self._lx = -1
        self._ly = -1
        self._last_move_time = 0.0
        self._move_interval = 1.0 / 100.0
        self._dragging = False
        self.is_available = True
        self.last_error_message = ""

    def _safe(self, fn, *a, **kw):
        if not self.is_available:
            return False
        try:
            fn(*a, **kw)
            return True
        except Exception as e:
            self.is_available = False
            self.last_error_message = str(e)
            return False

    def move_cursor(self, x, y):
        if not self.is_available:
            return

        now = time.monotonic()
        if now - self._last_move_time < self._move_interval:
            return

        dx, dy = x - self._lx, y - self._ly
        if dx * dx + dy * dy < self.thresh_sq:
            return
        if self._safe(_move, x, y):
            self._lx, self._ly = x, y
            self._last_move_time = now

    def left_click(self):
        return self._safe(pyautogui.click, button="left")

    def right_click(self):
        return self._safe(pyautogui.click, button="right")

    def double_click(self):
        return self._safe(pyautogui.doubleClick)

    def scroll(self, amount):
        if amount != 0:
            self._safe(pyautogui.scroll, amount)

    def start_drag(self):
        if not self._dragging:
            self._dragging = True
            self._safe(pyautogui.mouseDown, button="left")

    def end_drag(self):
        if self._dragging:
            self._dragging = False
            self._safe(pyautogui.mouseUp, button="left")

    @property
    def is_dragging(self):
        return self._dragging
