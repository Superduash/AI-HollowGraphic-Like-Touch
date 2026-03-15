"""Mouse control: move, click, double-click, scroll, drag. Supports pydirectinput on Windows."""

import platform
import threading
import time
import pyautogui
from config import (
    CLICK_COOLDOWN,
    CURSOR_DEADZONE_PX,
    CURSOR_PREDICTION_SECONDS,
    CURSOR_THREAD_HZ,
    CURSOR_MOVE_THRESHOLD,
)

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

_quartz = None
if platform.system() == "Darwin":
    try:
        import Quartz as _quartz  # type: ignore
    except Exception:
        _quartz = None


def _move_mac_quartz(x: int, y: int) -> None:
    if _quartz is None:
        raise RuntimeError("Quartz CoreGraphics is unavailable for cursor movement")
    event = _quartz.CGEventCreateMouseEvent(
        None,
        _quartz.kCGEventMouseMoved,
        (float(x), float(y)),
        _quartz.kCGMouseButtonLeft,
    )
    _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)


def _move(x: int, y: int) -> None:
    if platform.system() == "Darwin":
        _move_mac_quartz(x, y)
        return
    if _pdi:
        _pdi.moveTo(x, y)
        return
    pyautogui.moveTo(x, y)


class MouseController:
    def __init__(self, cooldown=CLICK_COOLDOWN, threshold=CURSOR_MOVE_THRESHOLD):
        threshold = max(3.0, float(threshold))
        self.thresh_sq = threshold * threshold
        self._lx = -1
        self._ly = -1
        self._last_move_time = 0.0
        self._move_interval = 1.0 / max(1.0, float(CURSOR_THREAD_HZ))
        self._dragging = False
        self.is_available = True
        self.last_error_message = ""

        self._lock = threading.Lock()
        self._running = True
        self._target_x = -1.0
        self._target_y = -1.0
        self._vel_x = 0.0
        self._vel_y = 0.0
        self._last_target_t = 0.0
        self._cursor_x = -1.0
        self._cursor_y = -1.0
        self._predict_t = float(CURSOR_PREDICTION_SECONDS)
        self._thread = threading.Thread(target=self._cursor_loop, daemon=True)
        self._thread.start()

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
        tx = float(x)
        ty = float(y)
        with self._lock:
            if self._target_x >= 0.0:
                dt = max(1e-4, now - self._last_target_t)
                self._vel_x = (tx - self._target_x) / dt
                self._vel_y = (ty - self._target_y) / dt
            self._target_x = tx
            self._target_y = ty
            self._last_target_t = now

    def _cursor_loop(self) -> None:
        while self._running:
            start = time.monotonic()
            with self._lock:
                tx = self._target_x
                ty = self._target_y
                vx = self._vel_x
                vy = self._vel_y
                last_t = self._last_target_t

            if tx >= 0.0 and ty >= 0.0 and self.is_available:
                age = start - last_t if last_t > 0.0 else 0.0
                if age > self._move_interval:
                    # Keep motion continuous when fresh camera points are delayed.
                    tx = tx + vx * self._predict_t
                    ty = ty + vy * self._predict_t

                if self._cursor_x < 0.0:
                    self._cursor_x = tx
                    self._cursor_y = ty

                dx = tx - self._cursor_x
                dy = ty - self._cursor_y
                dist_sq = dx * dx + dy * dy
                if dist_sq >= self.thresh_sq:
                    dist = dist_sq ** 0.5
                    scale = min(1.0, max(0.24, dist / 24.0))
                    self._cursor_x += dx * scale
                    self._cursor_y += dy * scale

                    mx = int(round(self._cursor_x))
                    my = int(round(self._cursor_y))
                    if mx != self._lx or my != self._ly:
                        if self._safe(_move, mx, my):
                            self._lx, self._ly = mx, my
                            self._last_move_time = start

            elapsed = time.monotonic() - start
            time.sleep(max(0.0, self._move_interval - elapsed))

    def stop(self) -> None:
        self._running = False
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

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
