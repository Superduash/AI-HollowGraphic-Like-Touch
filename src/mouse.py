from __future__ import annotations

import platform
import subprocess
import threading
import time

from .tuning import MOUSE_CURSOR_INTERP_ALPHA, MOUSE_WORKER_HZ


class MouseController:
    def __init__(self) -> None:
        self._platform = platform.system()
        self._dragging = False

        self._target_x = -1
        self._target_y = -1
        self._cursor_x = -1.0
        self._cursor_y = -1.0
        self._last_x = -1
        self._last_y = -1
        self._deadzone_px = 2

        self._lock = threading.Lock()
        self._running = True
        self._worker = threading.Thread(target=self._cursor_worker, daemon=True)

        self._user32 = None
        self._quartz = None

        if self._platform == "Windows":
            try:
                import ctypes

                self._user32 = ctypes.windll.user32
                self._mouse_event = self._user32.mouse_event
                self._mouse_event.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
                self._mouse_event.restype = None
                self._MOUSEEVENTF_LEFTDOWN = 0x0002
                self._MOUSEEVENTF_LEFTUP = 0x0004
                self._MOUSEEVENTF_RIGHTDOWN = 0x0008
                self._MOUSEEVENTF_RIGHTUP = 0x0010
                self._MOUSEEVENTF_WHEEL = 0x0800
                self._WHEEL_DELTA = 120
            except Exception:
                self._user32 = None
                self._mouse_event = None

        elif self._platform == "Darwin":
            try:
                import Quartz  # type: ignore[import-not-found]

                self._quartz = Quartz
            except Exception:
                self._quartz = None

        self._worker.start()

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def stop(self) -> None:
        self._running = False
        if self._worker.is_alive():
            self._worker.join(timeout=0.5)

    def move(self, x: int, y: int) -> None:
        with self._lock:
            self._target_x = int(x)
            self._target_y = int(y)

    def _cursor_worker(self) -> None:
        interval = 1.0 / max(30.0, float(MOUSE_WORKER_HZ))
        while self._running:
            with self._lock:
                tx = self._target_x
                ty = self._target_y

            if tx != -1 and ty != -1:
                if self._cursor_x < 0.0 or self._cursor_y < 0.0:
                    self._cursor_x = float(tx)
                    self._cursor_y = float(ty)
                else:
                    self._cursor_x = self._cursor_x + (float(tx) - self._cursor_x) * float(MOUSE_CURSOR_INTERP_ALPHA)
                    self._cursor_y = self._cursor_y + (float(ty) - self._cursor_y) * float(MOUSE_CURSOR_INTERP_ALPHA)

                cx = int(self._cursor_x)
                cy = int(self._cursor_y)
                dx = cx - self._last_x
                dy = cy - self._last_y
                if dx * dx + dy * dy >= self._deadzone_px * self._deadzone_px:
                    self._set_cursor_pos(cx, cy)
                    self._last_x = cx
                    self._last_y = cy

            time.sleep(interval)

    def _set_cursor_pos(self, x: int, y: int) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            self._user32.SetCursorPos(int(x), int(y))
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            event = q.CGEventCreateMouseEvent(None, q.kCGEventMouseMoved, (float(x), float(y)), q.kCGMouseButtonLeft)
            q.CGEventPost(q.kCGHIDEventTap, event)

    def left_click(self) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            self._mouse_event(self._MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
            self._mouse_event(self._MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseDown, (float(x), float(y)), q.kCGMouseButtonLeft)
            up = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseUp, (float(x), float(y)), q.kCGMouseButtonLeft)
            q.CGEventPost(q.kCGHIDEventTap, down)
            q.CGEventPost(q.kCGHIDEventTap, up)

    def right_click(self) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            self._mouse_event(self._MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, None)
            self._mouse_event(self._MOUSEEVENTF_RIGHTUP, 0, 0, 0, None)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventRightMouseDown, (float(x), float(y)), q.kCGMouseButtonRight)
            up = q.CGEventCreateMouseEvent(None, q.kCGEventRightMouseUp, (float(x), float(y)), q.kCGMouseButtonRight)
            q.CGEventPost(q.kCGHIDEventTap, down)
            q.CGEventPost(q.kCGHIDEventTap, up)

    def double_click(self) -> None:
        self.left_click()
        time.sleep(0.03)
        self.left_click()

    def scroll(self, amount: int) -> None:
        if amount == 0:
            return

        if self._platform == "Windows" and self._user32 is not None:
            clicks = max(-20, min(20, int(amount)))
            delta = int(clicks * self._WHEEL_DELTA)
            self._mouse_event(self._MOUSEEVENTF_WHEEL, 0, 0, delta & 0xFFFFFFFF, None)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, int(amount)))

    def start_drag(self) -> None:
        if self._dragging:
            return
        self._dragging = True

        if self._platform == "Windows" and self._user32 is not None:
            self._mouse_event(self._MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseDown, (float(x), float(y)), q.kCGMouseButtonLeft)
            q.CGEventPost(q.kCGHIDEventTap, down)

    def end_drag(self) -> None:
        if not self._dragging:
            return
        self._dragging = False

        if self._platform == "Windows" and self._user32 is not None:
            self._mouse_event(self._MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            up = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseUp, (float(x), float(y)), q.kCGMouseButtonLeft)
            q.CGEventPost(q.kCGHIDEventTap, up)

    def send_media_key(self, action: str, count: int = 1) -> bool:
        if self._platform != "Windows" or self._user32 is None:
            return False
        key_map = {
            "vol_up": 0xAF,
            "vol_down": 0xAE,
            "next": 0xB0,
            "prev": 0xB1,
        }
        vk = key_map.get(action)
        if vk is None:
            return False
        reps = max(1, int(count))
        for _ in range(reps):
            self._user32.keybd_event(vk, 0, 0, 0)
            self._user32.keybd_event(vk, 0, 2, 0)
        return True

    def show_osk(self) -> bool:
        if self._platform == "Windows":
            try:
                flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(["osk.exe"], creationflags=flags)
                return True
            except Exception:
                return False
        if self._platform == "Darwin":
            try:
                subprocess.Popen(["open", "-a", "Keyboard Viewer"])
                return True
            except Exception:
                return False
        return False

    def open_task_view(self) -> bool:
        if self._platform != "Windows" or self._user32 is None:
            return False
        try:
            self._user32.keybd_event(0x5B, 0, 0, 0)
            self._user32.keybd_event(0x09, 0, 0, 0)
            self._user32.keybd_event(0x09, 0, 2, 0)
            self._user32.keybd_event(0x5B, 0, 2, 0)
            return True
        except Exception:
            return False
