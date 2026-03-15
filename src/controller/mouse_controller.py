"""Mouse control: move, click, double-click, scroll, drag. Synchronous with macOS Quartz optimization."""

import platform
import time

_quartz = None
if platform.system() == "Darwin":
    try:
        import Quartz as _quartz  # type: ignore
    except Exception:
        _quartz = None

class MouseController:
    def __init__(self, cooldown=0.0, threshold=0.0):
        self._dragging = False
        self.is_available = True
        self.last_error_message = ""
        self._cursor_x = -1.0
        self._cursor_y = -1.0

        if platform.system() == "Darwin" and _quartz is None:
            self.is_available = False
            self.last_error_message = "Quartz CoreGraphics is unavailable for syncing"

    def move_cursor(self, x: float, y: float) -> None:
        if not self.is_available:
            return
            
        self._cursor_x = float(x)
        self._cursor_y = float(y)
        
        if _quartz:
            event_type = _quartz.kCGEventLeftMouseDragged if self._dragging else _quartz.kCGEventMouseMoved
            event = _quartz.CGEventCreateMouseEvent(
                None,
                event_type,
                (self._cursor_x, self._cursor_y),
                _quartz.kCGMouseButtonLeft,
            )
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)

    def stop(self) -> None:
        pass

    def __del__(self):
        pass

    def left_click(self) -> bool:
        if not self.is_available or not _quartz:
            return False
            
        pos = (self._cursor_x, self._cursor_y)
        event_down = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
        event_up = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
        
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down)
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up)
        return True

    def right_click(self) -> bool:
        if not self.is_available or not _quartz:
            return False
            
        pos = (self._cursor_x, self._cursor_y)
        event_down = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventRightMouseDown, pos, _quartz.kCGMouseButtonRight)
        event_up = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventRightMouseUp, pos, _quartz.kCGMouseButtonRight)
        
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down)
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up)
        return True

    def double_click(self) -> bool:
        if not self.is_available or not _quartz:
            return False
            
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
        # Small delay often needed for macOS to register the double click state properly
        time.sleep(0.01)
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_down2)
        _quartz.CGEventPost(_quartz.kCGHIDEventTap, event_up2)
        return True

    def scroll(self, amount: int) -> None:
        if not self.is_available or not _quartz or amount == 0:
            return
            
        try:
            # param 0 is lines, 1 is pixels. We'll send standard pixel events.
            event = _quartz.CGEventCreateScrollWheelEvent(None, 0, 1, int(amount))
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)
        except Exception as e:
            pass

    def start_drag(self) -> None:
        if not self._dragging and self.is_available and _quartz:
            self._dragging = True
            pos = (self._cursor_x, self._cursor_y)
            event = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseDown, pos, _quartz.kCGMouseButtonLeft)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)

    def end_drag(self) -> None:
        if self._dragging and self.is_available and _quartz:
            self._dragging = False
            pos = (self._cursor_x, self._cursor_y)
            event = _quartz.CGEventCreateMouseEvent(None, _quartz.kCGEventLeftMouseUp, pos, _quartz.kCGMouseButtonLeft)
            _quartz.CGEventPost(_quartz.kCGHIDEventTap, event)

    @property
    def is_dragging(self) -> bool:
        return self._dragging

