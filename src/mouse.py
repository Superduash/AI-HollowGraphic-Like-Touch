import platform
import time


class MouseController:
    def __init__(self) -> None:
        self._move_interval = 1.0 / 240.0
        self._last_move = 0.0
        self._last_x = -1
        self._last_y = -1
        self._dragging = False

        self._user32 = None
        if platform.system() == "Windows":
            try:
                import ctypes
                self._user32 = ctypes.windll.user32
            except Exception:
                pass

        self._MOUSEEVENTF_LEFTDOWN = 0x0002
        self._MOUSEEVENTF_LEFTUP = 0x0004
        self._MOUSEEVENTF_RIGHTDOWN = 0x0008
        self._MOUSEEVENTF_RIGHTUP = 0x0010
        self._MOUSEEVENTF_WHEEL = 0x0800
        self._WHEEL_DELTA = 120

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def move(self, x: int, y: int) -> None:
        now = time.monotonic()
        if now - self._last_move < self._move_interval:
            return

        dx = x - self._last_x
        dy = y - self._last_y
        if dx * dx + dy * dy < 4:
            return

        if self._user32:
            self._user32.SetCursorPos(x, y)
        self._last_x, self._last_y = x, y
        self._last_move = now

    def left_click(self) -> None:
        if self._user32:
            self._user32.mouse_event(self._MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            self._user32.mouse_event(self._MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    def right_click(self) -> None:
        if self._user32:
            self._user32.mouse_event(self._MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            self._user32.mouse_event(self._MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def double_click(self) -> None:
        if self._user32:
            self.left_click()
            time.sleep(0.04)
            self.left_click()

    def scroll(self, amount: int) -> None:
        if amount == 0 or not self._user32:
            return
        clicks = max(-50, min(50, int(amount)))
        delta = int(clicks * self._WHEEL_DELTA)
        self._user32.mouse_event(self._MOUSEEVENTF_WHEEL, 0, 0, delta, 0)

    def start_drag(self) -> None:
        if not self._dragging:
            self._dragging = True
            if self._user32:
                self._user32.mouse_event(self._MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

    def end_drag(self) -> None:
        if self._dragging:
            self._dragging = False
            if self._user32:
                self._user32.mouse_event(self._MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
