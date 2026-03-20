from __future__ import annotations

import collections
import ctypes
import platform
import subprocess
import threading
import time
from typing import Any

try:
    import pyautogui  # type: ignore

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.0
except Exception:
    pyautogui = None  # type: ignore[assignment]

if platform.system() == "Windows":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
        except Exception:
            pass

from .tuning import MOUSE_WORKER_HZ  # type: ignore


class MouseController:
    def __init__(self) -> None:
        self._platform = platform.system()
        self._dragging = False

        self._target_x = -1
        self._target_y = -1
        self._has_target = False
        self._last_x = -1
        self._last_y = -1
        self._deadzone_px = 1

        self._lock = threading.Lock()
        self._running = True
        self._worker = threading.Thread(target=self._cursor_worker, daemon=True)
        self._media_queue: collections.deque[tuple[str, int]] = collections.deque()
        self._media_lock = threading.Lock()
        self._media_worker = threading.Thread(target=self._media_worker_loop, daemon=True)

        self._user32: Any = None
        self._quartz: Any = None

        if self._platform == "Windows":
            try:
                import ctypes

                self._user32 = ctypes.windll.user32 # type: ignore
                self._MOUSEEVENTF_LEFTDOWN = 0x0002
                self._MOUSEEVENTF_LEFTUP = 0x0004
                self._MOUSEEVENTF_RIGHTDOWN = 0x0008
                self._MOUSEEVENTF_RIGHTUP = 0x0010
                self._MOUSEEVENTF_WHEEL = 0x0800
                self._WHEEL_DELTA = 120

                # --- SendInput structs (modern API, replaces mouse_event) ---
                class _MOUSEINPUT(ctypes.Structure):
                    _fields_ = [
                        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                    ]
                class _INPUT(ctypes.Structure):
                    _fields_ = [("type", ctypes.c_ulong), ("mi", _MOUSEINPUT)]

                self._MOUSEINPUT = _MOUSEINPUT
                self._INPUT = _INPUT
                self._SendInput = self._user32.SendInput
                self._SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(_INPUT), ctypes.c_int]
                self._SendInput.restype = ctypes.c_uint
                self._scr_w: int = int(ctypes.windll.user32.GetSystemMetrics(0)) or 1920
                self._scr_h: int = int(ctypes.windll.user32.GetSystemMetrics(1)) or 1080
                self._MOUSEEVENTF_MOVE = 0x0001
                self._MOUSEEVENTF_ABSOLUTE = 0x8000
            except Exception:
                self._user32 = None

        elif self._platform == "Darwin":
            try:
                import Quartz  # type: ignore[import-not-found]

                self._quartz = Quartz
            except Exception:
                self._quartz = None

        self._worker.start()
        self._media_worker.start()

    def _send_mouse_flags(self, flags: int, mouse_data: int = 0) -> None:
        """Send a single SendInput mouse event. Windows only."""
        if self._platform != "Windows" or not hasattr(self, '_SendInput'):
            return
        inp = self._INPUT(
            type=0,
            mi=self._MOUSEINPUT(0, 0, mouse_data, flags, 0, None)
        )
        self._SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def stop(self) -> None:
        self._running = False
        if self._worker.is_alive():  # type: ignore
            self._worker.join(timeout=0.5)  # type: ignore
        if self._media_worker.is_alive():  # type: ignore
            self._media_worker.join(timeout=0.5)  # type: ignore

    def move(self, x: int, y: int) -> None:
        with self._lock:
            self._target_x = int(x)
            self._target_y = int(y)
            self._has_target = True

    def _cursor_worker(self) -> None:
        hz = max(10.0, min(1000.0, float(MOUSE_WORKER_HZ)))
        interval = max(0.001, 1.0 / hz)
        while self._running:
            with self._lock:
                tx = self._target_x
                ty = self._target_y
                has_target = self._has_target

            if has_target:
                cx = int(tx)
                cy = int(ty)
                dx = cx - self._last_x
                dy = cy - self._last_y
                if dx * dx + dy * dy >= self._deadzone_px * self._deadzone_px:
                    self._set_cursor_pos(cx, cy)
                    self._last_x = cx
                    self._last_y = cy

            time.sleep(interval)

    def _media_worker_loop(self) -> None:
        while self._running:
            item = None
            with self._media_lock:
                if self._media_queue:
                    item = self._media_queue.popleft()
            if item is None:
                time.sleep(0.002)
                continue
            action, count = item
            self._send_media_key_now(action, count)

    def _set_cursor_pos(self, x: int, y: int) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            try:
                ax = int(x * 65535 // self._scr_w)
                ay = int(y * 65535 // self._scr_h)
                inp = self._INPUT(
                    type=0,
                    mi=self._MOUSEINPUT(
                        dx=ax, dy=ay, mouseData=0,
                        dwFlags=self._MOUSEEVENTF_MOVE | self._MOUSEEVENTF_ABSOLUTE,
                        time=0, dwExtraInfo=None,
                    )
                )
                self._SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
            except Exception:
                self._user32.SetCursorPos(int(x), int(y))
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            event = q.CGEventCreateMouseEvent(None, q.kCGEventMouseMoved, (float(x), float(y)), q.kCGMouseButtonLeft)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, event)  # type: ignore

    def left_click(self) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            self._send_mouse_flags(self._MOUSEEVENTF_LEFTDOWN)
            time.sleep(0.008)
            self._send_mouse_flags(self._MOUSEEVENTF_LEFTUP)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseDown, (float(x), float(y)), q.kCGMouseButtonLeft)  # type: ignore
            up = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseUp, (float(x), float(y)), q.kCGMouseButtonLeft)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, down)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, up)  # type: ignore

    def right_click(self) -> None:
        if self._platform == "Windows" and self._user32 is not None:
            self._send_mouse_flags(self._MOUSEEVENTF_RIGHTDOWN)
            time.sleep(0.008)
            self._send_mouse_flags(self._MOUSEEVENTF_RIGHTUP)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventRightMouseDown, (float(x), float(y)), q.kCGMouseButtonRight)  # type: ignore
            up = q.CGEventCreateMouseEvent(None, q.kCGEventRightMouseUp, (float(x), float(y)), q.kCGMouseButtonRight)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, down)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, up)  # type: ignore

    def double_click(self) -> None:
        self.left_click()
        time.sleep(0.05)
        self.left_click()

    def scroll(self, amount: int) -> None:
        if amount == 0:
            return

        if self._platform == "Windows" and self._user32 is not None:
            clicks = max(-20, min(20, int(amount)))
            delta = int(clicks * self._WHEEL_DELTA)
            self._send_mouse_flags(self._MOUSEEVENTF_WHEEL, delta & 0xFFFFFFFF)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            q.CGEventPost(q.kCGHIDEventTap, q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, int(amount)))  # type: ignore

    def start_drag(self) -> None:
        if self._dragging:
            return
        self._dragging = True

        if self._platform == "Windows" and self._user32 is not None:
            self._send_mouse_flags(self._MOUSEEVENTF_LEFTDOWN)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            down = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseDown, (float(x), float(y)), q.kCGMouseButtonLeft)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, down)  # type: ignore

    def end_drag(self) -> None:
        if not self._dragging:
            return
        self._dragging = False

        if self._platform == "Windows" and self._user32 is not None:
            self._send_mouse_flags(self._MOUSEEVENTF_LEFTUP)
            return

        if self._platform == "Darwin" and self._quartz is not None:
            q = self._quartz
            x, y = self._last_x, self._last_y
            up = q.CGEventCreateMouseEvent(None, q.kCGEventLeftMouseUp, (float(x), float(y)), q.kCGMouseButtonLeft)  # type: ignore
            q.CGEventPost(q.kCGHIDEventTap, up)  # type: ignore

    def _send_media_key_now(self, action: str, count: int = 1) -> bool:
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
            self._user32.keybd_event(vk, 0, 0, 0)  # type: ignore
            self._user32.keybd_event(vk, 0, 2, 0)  # type: ignore
            time.sleep(0.01)
        return True

    def send_media_key(self, action: str, count: int = 1) -> bool:
        if self._platform != "Windows" or self._user32 is None:
            return False
        with self._media_lock:
            self._media_queue.append((action, max(1, int(count))))
            if len(self._media_queue) > 8:
                while len(self._media_queue) > 8:
                    self._media_queue.popleft()
        return True

    def show_osk(self) -> bool:
        if self._platform == "Windows":
            import os
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            sys_root = os.environ.get("SystemRoot", "C:\\Windows")

            # Candidate keyboard executables in priority order:
            # 1. TabTip.exe — Windows Accessibility Touch Keyboard (works on Win10/11, no UAC)
            # 2. osk.exe via System32
            # 3. osk.exe via sysnative (32-bit host on 64-bit Windows)
            tabtip = os.path.join(sys_root, "System32", "InputApp", "TabTip.exe")
            if not os.path.exists(tabtip):
                tabtip = os.path.join(sys_root, "System32", "TabTip.exe")

            osk_path = os.path.join(sys_root, "System32", "osk.exe")
            if not os.path.exists(osk_path):
                osk_path = os.path.join(sys_root, "sysnative", "osk.exe")

            try:
                # Check running keyboards and toggle
                tasklist = subprocess.check_output(
                    'tasklist /NH', shell=True, creationflags=flags
                ).decode(errors="replace").lower()

                if "tabtip.exe" in tasklist:
                    subprocess.run('taskkill /IM TabTip.exe /F', shell=True,
                                   capture_output=True, creationflags=flags)
                    return True
                if "osk.exe" in tasklist:
                    subprocess.run('taskkill /IM osk.exe /F', shell=True,
                                   capture_output=True, creationflags=flags)
                    return True

                # Not running — launch preferred keyboard
                if os.path.exists(tabtip):
                    subprocess.Popen([tabtip], creationflags=flags,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True
                if os.path.exists(osk_path):
                    subprocess.Popen([osk_path], creationflags=flags,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True

                # Last resort: shell start
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", "osk.exe"],
                    creationflags=flags,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                return False

        if self._platform == "Darwin":
            try:
                output = subprocess.check_output(['ps', '-ax']).decode('utf-8')
                if 'Keyboard Viewer' in output:
                    subprocess.run(['killall', 'Keyboard Viewer'])
                else:
                    subprocess.Popen(["open", "-a", "Keyboard Viewer"])
                return True
            except Exception:
                return False
        return False


    def open_task_view(self) -> bool:
        if self._platform != "Windows" or self._user32 is None:
            return False
        try:
            self._user32.keybd_event(0x5B, 0, 0, 0)  # type: ignore
            self._user32.keybd_event(0x09, 0, 0, 0)  # type: ignore
            self._user32.keybd_event(0x09, 0, 2, 0)  # type: ignore
            self._user32.keybd_event(0x5B, 0, 2, 0)  # type: ignore
            return True
        except Exception:
            return False
