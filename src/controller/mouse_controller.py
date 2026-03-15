"""Mouse control: move, click, double-click, scroll, drag. Synchronous with OS-native optimization."""

import platform
import time

_sys = platform.system()

_quartz = None
_ctypes = None
_user32 = None

# Windows Constants
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

if _sys == "Darwin":
    try:
        import Quartz as _quartz  # type: ignore
    except Exception:
        _quartz = None
elif _sys == "Windows":
    try:
        import ctypes
        _ctypes = ctypes
        _user32 = ctypes.windll.user32
    except Exception:
        _ctypes = None
        _user32 = None

class MouseController:
    def __init__(self, cooldown=0.0, threshold=0.0):
        self._dragging = False
        self.is_available = True
        self.last_error_message = ""
        self._cursor_x = -1.0
        self._cursor_y = -1.0

        if _sys == "Darwin" and _quartz is None:
            self.is_available = False
            self.last_error_message = "Quartz CoreGraphics is unavailable for syncing"
        elif _sys == "Windows" and _user32 is None:
            self.is_available = False
            self.last_error_message = "Windows ctypes.user32 is unavailable"
        elif _sys not in ("Darwin", "Windows"):
            self.is_available = False
            self.last_error_message = f"OS {_sys} not supported for native mouse control"

    def move_cursor(self, x: float, y: float) -> None:
        if not self.is_available:
            return
            
        self._cursor_x = float(x)
        self._cursor_y = float(y)
        
        if _sys == "Darwin" and _quartz:
            event_type = _quartz.kCGEventLeftMouseDragged if self._dragging else _quartz.kCGEventMouseMoved
            event = _quartz.CGEventCreateMouseEvent(
                None,
                event_type,
                (self._cursor_x, self._cursor_y),
                _quartz.kCGMouseButtonLeft,
            )
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)
        elif _sys == "Windows" and _user32:
            _user32.SetCursorPos(int(x), int(y))

    def stop(self) -> None:
        pass

    def __del__(self):
        pass

    def left_click(self) -> bool:
        if not self.is_available: return False
            
        if _sys == "Darwin" and _quartz:
            pos = (self._cursor_x, self._cursor_y)
            event_down = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
            event_up = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up)
            return True
        elif _sys == "Windows" and _user32:
            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True
        return False

    def right_click(self) -> bool:
        if not self.is_available: return False
            
        if _sys == "Darwin" and _quartz:
            pos = (self._cursor_x, self._cursor_y)
            event_down = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventRightMouseDown, pos, _quartz.kCGMouseButtonRight)
            event_up = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventRightMouseUp, pos, _quartz.kCGMouseButtonRight)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up)
            return True
        elif _sys == "Windows" and _user32:
            _user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            _user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return True
        return False

    def double_click(self) -> bool:
        if not self.is_available: return False
            
        if _sys == "Darwin" and _quartz:
            pos = (self._cursor_x, self._cursor_y)
            event_down1 = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
            event_up1 = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
            _quartz.CGEventSetIntegerValueField(event_down1, _quartz.kCGMouseEventClickState, 1)
            _quartz.CGEventSetIntegerValueField(event_up1, _quartz.kCGMouseEventClickState, 1)
            
            event_down2 = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
            event_up2 = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
            _quartz.CGEventSetIntegerValueField(event_down2, _quartz.kCGMouseEventClickState, 2)
            _quartz.CGEventSetIntegerValueField(event_up2, _quartz.kCGMouseEventClickState, 2)
            
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down1)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up1)
            time.sleep(0.01)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down2)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up2)
            return True
        elif _sys == "Windows" and _user32:
            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.02)
            _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return True
        return False

    def scroll(self, amount: int) -> None:
        if not self.is_available or amount == 0:
            return
            
        if _sys == "Darwin" and _quartz:
            try:
                event = _quartz.CGEventCreateScrollWheelEvent(None, 0, 1, int(amount))
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)
            except Exception:
                pass
        elif _sys == "Windows" and _user32:
            try:
                # amount is usually lines, clamp and multiply by 120 per Windows standard
                clicks = max(-50, min(50, int(amount)))
                delta = int(clicks * WHEEL_DELTA)
                _user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
            except Exception:
                pass

    def start_drag(self) -> None:
        if not self._dragging and self.is_available:
            self._dragging = True
            if _sys == "Darwin" and _quartz:
                pos = (self._cursor_x, self._cursor_y)
                event = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)
            elif _sys == "Windows" and _user32:
                _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

    def end_drag(self) -> None:
        if self._dragging and self.is_available:
            self._dragging = False
            if _sys == "Darwin" and _quartz:
                pos = (self._cursor_x, self._cursor_y)
                event = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
                _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)
            elif _sys == "Windows" and _user32:
                _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

    @property
    def is_dragging(self) -> bool:
        return self._dragging

