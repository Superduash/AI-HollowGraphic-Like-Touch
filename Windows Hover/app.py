"""Windows Hover: single-file Windows-optimized holographic touch mouse.

Designed for USB portability: one main Python file with merged camera, tracking,
gesture, cursor, and UI logic.
"""

from __future__ import annotations

import math
import os
import platform
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
try:
    import mediapipe as mp  # type: ignore
except Exception:  # ImportError on missing package; also guard weird install states
    mp = None  # type: ignore[assignment]
import pyautogui
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


def _mediapipe_diagnostic() -> str:
    try:
        if mp is None:
            return "mediapipe import failed (package not installed or import error)"
        file_path = getattr(mp, "__file__", None)
        version = getattr(mp, "__version__", None)
        has_solutions = hasattr(mp, "solutions")
        return f"mediapipe version={version} file={file_path} has_solutions={has_solutions}"
    except Exception:
        return "mediapipe diagnostic unavailable"


def _ensure_mediapipe_solutions() -> None:
    if mp is None:
        raise RuntimeError(
            "MediaPipe is not installed (or failed to import).\n\n"
            "Fix (inside this app's .venv):\n"
            "1) Open a terminal in this folder\n"
            "2) Run: .venv\\Scripts\\python -m pip install -r requirements.txt\n"
        )

    if hasattr(mp, "solutions"):
        return

    detail = _mediapipe_diagnostic()
    raise RuntimeError(
        "MediaPipe import looks wrong: 'mediapipe' has no attribute 'solutions'.\n"
        f"{detail}\n\n"
        "Most common causes:\n"
        "- A different 'mediapipe' module is being imported (shadowing).\n"
        "- A broken/partial mediapipe install in the venv.\n\n"
        "Fix (inside this app's .venv):\n"
        "1) Open a terminal in this folder\n"
        "2) Run: .venv\\Scripts\\python -m pip uninstall -y mediapipe\n"
        "3) Run: .venv\\Scripts\\python -m pip install mediapipe==0.10.21\n"
    )


def _configure_input_latency() -> None:
    # Reduce pyautogui built-in delays for lower latency.
    try:
        pyautogui.PAUSE = 0
        pyautogui.MINIMUM_DURATION = 0
        pyautogui.MINIMUM_SLEEP = 0
        pyautogui.FAILSAFE = False
    except Exception:
        pass


def _boost_runtime_priority() -> None:
    # Best-effort: prefer responsiveness on Windows.
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        GetCurrentProcess = kernel32.GetCurrentProcess
        GetCurrentThread = kernel32.GetCurrentThread
        SetPriorityClass = kernel32.SetPriorityClass
        SetThreadPriority = kernel32.SetThreadPriority

        HIGH_PRIORITY_CLASS = 0x00000080
        THREAD_PRIORITY_HIGHEST = 2

        SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS)
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_HIGHEST)
    except Exception:
        pass


class GestureType(str, Enum):
    NONE = "NONE"
    MOVE = "MOVE"
    LEFT_CLICK = "LEFT CLICK"
    RIGHT_CLICK = "RIGHT CLICK"
    DOUBLE_CLICK = "DOUBLE CLICK"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    TASK_VIEW = "TASK VIEW"
    PAUSE = "PAUSED"


@dataclass
class GestureResult:
    gesture: GestureType = GestureType.NONE
    scroll_delta: int = 0


@dataclass
class FingerStates:
    thumb: bool
    index: bool
    middle: bool
    ring: bool
    pinky: bool


_OVERLAY_LABELS = {
    GestureType.NONE: "PAUSED",
    GestureType.MOVE: "MOVE",
    GestureType.LEFT_CLICK: "CLICK",
    GestureType.DOUBLE_CLICK: "DOUBLE",
    GestureType.RIGHT_CLICK: "RIGHT CLICK",
    GestureType.SCROLL: "SCROLL",
    GestureType.DRAG: "DRAG",
    GestureType.TASK_VIEW: "TASK VIEW",
    GestureType.PAUSE: "PAUSED",
}


_BADGE_COLORS = {
    GestureType.MOVE: "#60A5FA",
    GestureType.LEFT_CLICK: "#4ADE80",
    GestureType.RIGHT_CLICK: "#4ADE80",
    GestureType.DOUBLE_CLICK: "#4ADE80",
    GestureType.SCROLL: "#A78BFA",
    GestureType.DRAG: "#A78BFA",
    GestureType.TASK_VIEW: "#A78BFA",
    GestureType.PAUSE: "#F87171",
    GestureType.NONE: "#64748B",
}


class CameraSource:
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread = None
        self._frame = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        if self._running:
            return True

        indexes = [0, 1, 2]
        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY

        for idx in indexes:
            cap = cv2.VideoCapture(idx, backend)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ok = False
            for _ in range(10):
                r, f = cap.read()
                if r and f is not None:
                    ok = True
                    break
                time.sleep(0.02)

            if ok:
                self._cap = cap
                self._running = True
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
                return True

            cap.release()

        return False

    def _loop(self) -> None:
        while self._running:
            cap = self._cap
            if cap is None:
                time.sleep(0.005)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue
            with self._lock:
                self._frame = frame

    def latest(self):
        with self._lock:
            if self._frame is None:
                return None
            return self._frame

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        with self._lock:
            self._frame = None


class HandTracker:
    def __init__(self, process_w: int = 320, process_h: int = 240) -> None:
        self.process_w = process_w
        self.process_h = process_h

        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
        self._draw = mp.solutions.drawing_utils  # type: ignore[attr-defined]
        self._styles = mp.solutions.drawing_styles  # type: ignore[attr-defined]

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.45,
            min_tracking_confidence=0.45,
        )

        self._landmark_style = self._styles.get_default_hand_landmarks_style()
        self._conn_style = self._styles.get_default_hand_connections_style()

    def detect(self, frame_bgr):
        small = cv2.resize(frame_bgr, (self.process_w, self.process_h), interpolation=cv2.INTER_NEAREST)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        if not result.multi_hand_landmarks:
            return None, None

        hand = result.multi_hand_landmarks[0]
        xy = [(int(lm.x * self.process_w), int(lm.y * self.process_h)) for lm in hand.landmark]
        z = [float(lm.z) for lm in hand.landmark]
        return {"xy": xy, "z": z}, hand

    def draw(self, frame_rgb, hand_proto):
        if hand_proto is None:
            return
        self._draw.draw_landmarks(
            frame_rgb,
            hand_proto,
            self._mp_hands.HAND_CONNECTIONS,
            self._landmark_style,
            self._conn_style,
        )

    def close(self):
        try:
            self._hands.close()
        except Exception:
            pass


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

        x3 = self._interp(cam_x, x1, x2, 0.0, float(self.scr_w))
        y3 = self._interp(cam_y, y1, y2, 0.0, float(self.scr_h))

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


class StatusOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowTitle("Windows Hover Status")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(260, 120)

        root = QFrame(self)
        root.setObjectName("overlayRoot")
        root.setGeometry(0, 0, 260, 120)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(10)
        self._dot = QLabel("●")
        self._dot.setObjectName("statusOnline")
        self._title = QLabel("Windows Hover")
        self._title.setObjectName("overlayTitle")
        top.addWidget(self._dot)
        top.addWidget(self._title)
        top.addStretch(1)
        self._fps = QLabel("FPS 0")
        self._fps.setObjectName("muted")
        top.addWidget(self._fps)
        layout.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(10)
        self._badge = QLabel("PAUSED")
        self._badge.setObjectName("badge")
        self._hand = QLabel("Hand: -")
        self._hand.setObjectName("muted")
        mid.addWidget(self._badge)
        mid.addWidget(self._hand)
        mid.addStretch(1)
        layout.addLayout(mid)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.open_btn = QPushButton("Open")
        self.open_btn.setObjectName("ghostButton")
        self.disable_btn = QPushButton("Disable Mouse")
        self.disable_btn.setObjectName("redButton")
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(self.disable_btn)
        layout.addLayout(btns)

        self.setStyleSheet(
            """
            #overlayRoot {
                background: #1A1D24;
                border: 1px solid #222733;
                border-radius: 14px;
            }
            QLabel { color: #E5E7EB; font-size: 13px; }
            #overlayTitle { font-weight: 700; }
            #muted { color: #A3A9B8; }
            #statusOnline { color: #4ADE80; font-size: 18px; }
            #badge {
                border-radius: 12px;
                padding: 6px 10px;
                font-weight: 700;
                background: #334155;
                color: #F8FAFC;
                max-width: 160px;
            }
            QPushButton {
                border: 0;
                border-radius: 12px;
                color: #F8FAFC;
                padding: 8px 10px;
                font-weight: 600;
                background: #2A3040;
            }
            QPushButton:hover { background: #394055; }
            #ghostButton { background: #252A36; color: #E5E7EB; }
            #ghostButton:hover { background: #313849; }
            #redButton { background: #F87171; color: #0B1118; }
            #redButton:hover { background: #FA8A8A; }
            """
        )

    def update_status(self, gesture: GestureType, fps: float, hand_ok: bool) -> None:
        self._fps.setText(f"FPS {fps:.0f}")
        self._hand.setText(f"Hand: {'Detected' if hand_ok else 'Not Detected'}")
        self._badge.setText(gesture.value)
        self._badge.setStyleSheet(
            f"border-radius: 12px; padding: 6px 10px; font-weight: 700; background: {_BADGE_COLORS.get(gesture, '#64748B')}; color: #0B1118;"
        )


class MouseController:
    def __init__(self) -> None:
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0

        self._move_interval = 1.0 / 240.0
        self._last_move = 0.0
        self._last_x = -1
        self._last_y = -1
        self._dragging = False

        self._pdi = None
        if platform.system() == "Windows":
            try:
                import pydirectinput  # type: ignore[import-not-found]

                pydirectinput.FAILSAFE = False
                pydirectinput.PAUSE = 0
                self._pdi = pydirectinput
            except Exception:
                self._pdi = None

    @staticmethod
    def _native_scroll_windows(amount: int) -> bool:
        if platform.system() != "Windows":
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32  # type: ignore[attr-defined]
            MOUSEEVENTF_WHEEL = 0x0800
            WHEEL_DELTA = 120

            clicks = int(amount)
            if clicks == 0:
                return True

            # Clamp to avoid extreme values.
            clicks = max(-50, min(50, clicks))
            delta = int(clicks * WHEEL_DELTA)
            user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
            return True
        except Exception:
            return False

    @property
    def is_dragging(self) -> bool:
        return self._dragging

    def _move_to(self, x: int, y: int) -> None:
        if self._pdi is not None:
            self._pdi.moveTo(x, y)
        else:
            pyautogui.moveTo(x, y)

    def move(self, x: int, y: int) -> None:
        now = time.monotonic()
        if now - self._last_move < self._move_interval:
            return

        dx = x - self._last_x
        dy = y - self._last_y
        if dx * dx + dy * dy < 4:
            return

        self._move_to(x, y)
        self._last_x, self._last_y = x, y
        self._last_move = now

    def left_click(self) -> None:
        if self._pdi is not None:
            self._pdi.click(button="left")
        else:
            pyautogui.click(button="left")

    def right_click(self) -> None:
        if self._pdi is not None:
            self._pdi.click(button="right")
        else:
            pyautogui.click(button="right")

    def scroll(self, amount: int) -> None:
        if amount == 0:
            return

        pdi = self._pdi
        if pdi is not None and hasattr(pdi, "scroll"):
            try:
                pdi.scroll(int(amount))
                return
            except Exception:
                pass

        if hasattr(pyautogui, "scroll"):
            try:
                pyautogui.scroll(int(amount))
                return
            except Exception:
                pass

        # Last resort: Windows-native wheel event.
        self._native_scroll_windows(int(amount))

    def start_drag(self) -> None:
        if not self._dragging:
            self._dragging = True
            if self._pdi is not None:
                self._pdi.mouseDown(button="left")
            else:
                pyautogui.mouseDown(button="left")

    def end_drag(self) -> None:
        if self._dragging:
            self._dragging = False
            if self._pdi is not None:
                self._pdi.mouseUp(button="left")
            else:
                pyautogui.mouseUp(button="left")


class GestureEngine:
    def __init__(self) -> None:
        self._candidate = GestureType.NONE
        self._candidate_frames = 0
        self._confirmed = GestureType.NONE
        self._dragging = False

        self._confirm_required = 3

        self._left_pinch_active = False
        self._right_pinch_active = False
        self._left_pinch_start = 0.0
        self._left_pinch_frames = 0
        self._right_pinch_frames = 0
        self._left_click_fired = False
        self._right_click_fired = False

        self._last_left = 0.0
        self._last_right = 0.0
        self._last_task_view = 0.0

        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        self._pinch_enter = 0.23
        self._pinch_exit = 0.30
        self._scroll_motion_threshold = 3.0
        self._task_view_cooldown = 1.0
        self._click_cooldown = 0.25

    @property
    def dragging(self) -> bool:
        return self._dragging

    @staticmethod
    def _distance(a, b) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return math.sqrt(dx * dx + dy * dy)

    @staticmethod
    def _finger_states(landmarks_xy) -> FingerStates:
        # Thumb: orientation-independent (same as repo main app)
        tt = landmarks_xy[4]
        ti = landmarks_xy[3]
        im = landmarks_xy[5]
        dx1, dy1 = tt[0] - im[0], tt[1] - im[1]
        dx2, dy2 = ti[0] - im[0], ti[1] - im[1]
        thumb = (dx1 * dx1 + dy1 * dy1) > (dx2 * dx2 + dy2 * dy2)
        index = landmarks_xy[8][1] < landmarks_xy[6][1]
        middle = landmarks_xy[12][1] < landmarks_xy[10][1]
        ring = landmarks_xy[16][1] < landmarks_xy[14][1]
        pinky = landmarks_xy[20][1] < landmarks_xy[18][1]
        return FingerStates(thumb, index, middle, ring, pinky)

    def detect(self, hand_data) -> GestureResult:
        if not hand_data:
            self._confirmed = GestureType.NONE
            self._candidate = GestureType.NONE
            self._candidate_frames = 0
            self._dragging = False

            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_start = 0.0
            self._left_pinch_frames = 0
            self._right_pinch_frames = 0
            self._left_click_fired = False
            self._right_click_fired = False

            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            return GestureResult(GestureType.PAUSE)

        xy = hand_data["xy"]
        now = time.monotonic()

        fs = self._finger_states(xy)

        # Open palm: Task View.
        if fs.thumb and fs.index and fs.middle and fs.ring and fs.pinky:
            self._dragging = False
            self._left_pinch_active = False
            self._right_pinch_active = False
            self._left_pinch_start = 0.0
            self._left_pinch_frames = 0
            self._right_pinch_frames = 0
            self._left_click_fired = False
            self._right_click_fired = False
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0

            if now - self._last_task_view >= self._task_view_cooldown:
                self._last_task_view = now
            return self._confirm(GestureType.TASK_VIEW, 0, edge_trigger=True)

        # Pinch distances (scale-invariant).
        thumb = xy[4]
        index_tip = xy[8]
        middle_tip = xy[12]

        hand_scale = max(40.0, self._distance(xy[5], xy[17]))
        enter = max(12.0, min(42.0, hand_scale * self._pinch_enter))
        exit_ = max(enter + 2.0, min(58.0, hand_scale * self._pinch_exit))

        left_dist = self._distance(thumb, index_tip)
        right_dist = self._distance(thumb, middle_tip)

        if self._left_pinch_active:
            if left_dist > exit_:
                self._left_pinch_active = False
        else:
            if left_dist < enter:
                self._left_pinch_active = True

        if self._right_pinch_active:
            if right_dist > exit_:
                self._right_pinch_active = False
        else:
            if right_dist < enter:
                self._right_pinch_active = True

        # Right click: thumb + middle pinch.
        if self._right_pinch_active and not self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._right_pinch_frames += 1
            if (
                not self._right_click_fired
                and self._right_pinch_frames >= 1
                and now - self._last_right >= self._click_cooldown
            ):
                self._right_click_fired = True
                self._last_right = now
                return self._confirm(GestureType.RIGHT_CLICK, 0, edge_trigger=True)
            return self._confirm(GestureType.MOVE, 0)
        if not self._right_pinch_active:
            self._right_pinch_frames = 0
            self._right_click_fired = False

        # Left click/drag: thumb + index pinch.
        if self._left_pinch_active:
            self._prev_scroll_y = None
            self._smooth_scroll = 0.0
            self._left_pinch_frames += 1
            if (
                not self._left_click_fired
                and self._left_pinch_frames >= 1
                and now - self._last_left >= self._click_cooldown
            ):
                self._left_click_fired = True
                self._last_left = now
                self._left_pinch_start = now
                return self._confirm(GestureType.LEFT_CLICK, 0, edge_trigger=True)

            if self._left_pinch_start == 0.0:
                self._left_pinch_start = now

            if now - self._left_pinch_start >= 0.30:
                self._dragging = True
                return self._confirm(GestureType.DRAG, 0, edge_trigger=True)

            return self._confirm(GestureType.MOVE, 0)

        # Pinch released.
        self._left_pinch_frames = 0
        self._left_click_fired = False
        self._left_pinch_start = 0.0
        self._dragging = False

        # Scroll: peace sign + vertical motion.
        if fs.index and fs.middle and not fs.ring and not fs.pinky:
            y = 0.5 * (xy[8][1] + xy[12][1])
            if self._prev_scroll_y is None:
                self._prev_scroll_y = y
                return self._confirm(GestureType.SCROLL, 0)

            dy = y - self._prev_scroll_y
            self._prev_scroll_y = y
            if abs(dy) < self._scroll_motion_threshold:
                return self._confirm(GestureType.SCROLL, 0)

            raw = -dy * 2.0
            self._smooth_scroll = 0.6 * self._smooth_scroll + 0.4 * raw
            return self._confirm(GestureType.SCROLL, int(self._smooth_scroll))

        self._prev_scroll_y = None
        self._smooth_scroll = 0.0

        # Move: index finger only.
        if fs.index and not fs.middle and not fs.ring and not fs.pinky:
            return self._confirm(GestureType.MOVE, 0)

        return self._confirm(GestureType.PAUSE, 0)

    def _confirm(self, raw: GestureType, scroll_delta: int, edge_trigger: bool = False) -> GestureResult:
        if raw == self._candidate:
            self._candidate_frames += 1
        else:
            self._candidate = raw
            self._candidate_frames = 1

        if raw in {GestureType.PAUSE, GestureType.SCROLL}:
            self._confirmed = raw
        elif edge_trigger:
            self._confirmed = raw
        else:
            if self._confirmed == GestureType.NONE and raw != GestureType.NONE:
                self._confirmed = raw
            elif self._candidate_frames >= self._confirm_required:
                self._confirmed = raw

        if self._confirmed == GestureType.SCROLL:
            return GestureResult(self._confirmed, scroll_delta)
        return GestureResult(self._confirmed, 0)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        _configure_input_latency()

        if platform.system() != "Windows":
            print("Windows Hover is optimized for Windows.")

        self.setWindowTitle("Holographic Touch")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        self.camera = CameraSource(640, 480)
        self._mediapipe_error: str | None = None
        try:
            self.tracker: HandTracker | None = HandTracker(320, 240)
        except Exception as exc:
            self.tracker = None
            self._mediapipe_error = str(exc)
        self.gestures = GestureEngine()
        self.fps = 0.0
        self._fps_prev = time.monotonic()

        sw, sh = pyautogui.size()
        self.mapper = CursorMapper(640, 480, sw, sh)
        self.mouse = MouseController()

        self.running = False
        self.proc_thread = None
        self.mouse_enabled = False
        self.debug = False
        self._overlay: StatusOverlay | None = None

        # Self-contained: only use assets shipped inside the Windows Hover folder.
        self._icons_dir = Path(__file__).resolve().parent / "assets" / "icons"

        self._lock = threading.Lock()
        self._frame = None
        self._hand_proto = None
        self._gesture = GestureType.PAUSE
        self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
        self._fingers = 0

        self._build_ui()

        if self._mediapipe_error:
            self.cam_status.setText("MediaPipe Error")
            self.preview.setText(self._mediapipe_error)
            self.start_btn.setEnabled(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._render)
        self.timer.start(16)

    def _icon(self, name: str) -> QIcon:
        p = self._icons_dir / name
        return QIcon(str(p)) if p.exists() else QIcon()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        top = QVBoxLayout(root)
        top.setContentsMargins(18, 18, 18, 18)
        top.setSpacing(14)

        header = QFrame()
        header.setObjectName("headerCard")
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(16, 14, 16, 14)
        header_l.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(self._icon("camera.svg").pixmap(QSize(22, 22)))

        self.title_lbl = QLabel("Holographic Touch")
        self.title_lbl.setObjectName("title")

        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusOffline")
        self.cam_status = QLabel("Camera Offline")
        self.fps_lbl = QLabel("FPS 0")

        header_l.addWidget(icon_label)
        header_l.addWidget(self.title_lbl)
        header_l.addStretch(1)
        header_l.addWidget(self._status_dot)
        header_l.addWidget(self.cam_status)
        header_l.addSpacing(10)
        header_l.addWidget(self.fps_lbl)
        header_l.addSpacing(10)

        body_l = QHBoxLayout()
        body_l.setSpacing(14)

        cam_card = QFrame()
        cam_card.setObjectName("cameraCard")
        cam_l = QVBoxLayout(cam_card)
        cam_l.setContentsMargins(12, 12, 12, 12)

        self.preview = QLabel("Camera Offline")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("preview")
        self.preview.setMinimumSize(760, 520)
        cam_l.addWidget(self.preview, 1)

        side = QVBoxLayout()
        side.setSpacing(12)

        status = QFrame()
        status.setObjectName("sideCard")
        sl = QVBoxLayout(status)
        sl.setContentsMargins(14, 14, 14, 14)
        sl.setSpacing(8)
        status_title = QLabel("Gesture Status")
        status_title.setObjectName("cardTitle")

        self.gesture_lbl = QLabel("PAUSED")
        self.gesture_lbl.setObjectName("badge")
        self.hand_lbl = QLabel("Hand: Not Detected")
        self.mouse_lbl = QLabel("Mouse: OFF")
        self.fingers_lbl = QLabel("Fingers: 0")
        sl.addWidget(status_title)
        sl.addWidget(self.gesture_lbl)
        sl.addWidget(self.hand_lbl)
        sl.addWidget(self.mouse_lbl)
        sl.addWidget(self.fingers_lbl)

        guide = QFrame()
        guide.setObjectName("sideCard")
        gl = QGridLayout(guide)
        gl.setContentsMargins(14, 14, 14, 14)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(8)

        guide_title = QLabel("Gesture Guide")
        guide_title.setObjectName("cardTitle")
        gl.addWidget(guide_title, 0, 0, 1, 3)

        guide_rows = [
            ("move.svg", "Index finger", "Move cursor"),
            ("click.svg", "Thumb + Index pinch", "Left click"),
            ("drag.svg", "Hold Thumb + Index pinch", "Drag"),
            ("click.svg", "Thumb + Middle pinch", "Right click"),
            ("scroll.svg", "Peace sign + up/down", "Scroll"),
            ("settings.svg", "Open palm", "Task View (Win+Tab)"),
            ("pause.svg", "No gesture / hand down", "Pause"),
        ]
        for i, (ico, a, b) in enumerate(guide_rows, start=1):
            il = QLabel()
            il.setPixmap(self._icon(ico).pixmap(QSize(16, 16)))
            tl = QLabel(a)
            dl = QLabel(b)
            dl.setObjectName("muted")
            gl.addWidget(il, i, 0)
            gl.addWidget(tl, i, 1)
            gl.addWidget(dl, i, 2)

        side.addWidget(status)
        side.addWidget(guide, 1)

        side_wrap = QWidget()
        side_wrap.setLayout(side)
        side_wrap.setMinimumWidth(360)

        body_l.addWidget(cam_card, 1)
        body_l.addWidget(side_wrap)

        controls = QFrame()
        controls.setObjectName("controlCard")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(16, 12, 16, 12)
        cl.setSpacing(10)

        self.start_btn = QPushButton("Start Camera")
        self.start_btn.setIcon(self._icon("camera.svg"))
        self.start_btn.setObjectName("greenButton")
        self.stop_btn = QPushButton("Stop Camera")
        self.stop_btn.setIcon(self._icon("stop.svg"))
        self.stop_btn.setObjectName("redButton")
        self.stop_btn.setEnabled(False)
        self.mouse_btn = QPushButton("Enable Mouse")
        self.mouse_btn.setIcon(self._icon("mouse.svg"))
        self.mouse_btn.setObjectName("blueButton")

        self._region_label = QLabel(f"Control margin: {self.mapper.frame_r}")
        self._region_label.setObjectName("muted")
        self._region_slider = QSlider(Qt.Orientation.Horizontal)
        self._region_slider.setRange(40, 200)
        self._region_slider.setValue(int(self.mapper.frame_r))
        self._region_slider.setFixedWidth(180)
        self._region_slider.valueChanged.connect(self._set_control_margin)

        self.start_btn.clicked.connect(self.start_camera)
        self.stop_btn.clicked.connect(self.stop_camera)
        self.mouse_btn.clicked.connect(self.toggle_mouse)

        cl.addWidget(self.start_btn)
        cl.addWidget(self.stop_btn)
        cl.addWidget(self.mouse_btn)
        cl.addSpacing(8)
        cl.addWidget(self._region_label)
        cl.addWidget(self._region_slider)
        cl.addStretch(1)

        top.addWidget(header)

        body_wrap = QWidget()
        body_wrap.setLayout(body_l)
        top.addWidget(body_wrap, 1)

        top.addWidget(controls)

        self.setStyleSheet(
            """
            QMainWindow { background: #0F1115; color: #E5E7EB; }
            #headerCard, #cameraCard, #sideCard, #controlCard {
                background: #1A1D24;
                border: 1px solid #222733;
                border-radius: 16px;
            }
            #title { font-size: 20px; font-weight: 700; color: #F3F4F6; }
            #statusOffline { color: #F87171; font-size: 18px; }
            #statusOnline { color: #4ADE80; font-size: 18px; }
            #preview {
                background: #0D1016;
                border-radius: 14px;
                border: 1px solid #263041;
                color: #9CA3AF;
                font-size: 18px;
            }
            #cardTitle { font-size: 14px; font-weight: 700; color: #F3F4F6; }
            #muted { color: #A3A9B8; }
            #badge {
                border-radius: 12px;
                padding: 6px 10px;
                font-weight: 700;
                background: #334155;
                color: #F8FAFC;
                max-width: 160px;
            }
            QPushButton {
                border: 0;
                border-radius: 12px;
                padding: 10px 14px;
                color: #F8FAFC;
                font-weight: 600;
                background: #2A3040;
            }
            QPushButton:hover { background: #394055; }
            QPushButton:disabled { background: #202532; color: #6B7280; }
            #greenButton { background: #4ADE80; color: #0B1118; }
            #greenButton:hover { background: #67E69A; }
            #redButton { background: #F87171; color: #0B1118; }
            #redButton:hover { background: #FA8A8A; }
            #blueButton { background: #60A5FA; color: #0B1118; }
            #blueButton:hover { background: #79B5FB; }
            #purpleButton { background: #A78BFA; color: #0B1118; }
            #purpleButton:hover { background: #B79EFB; }
            #ghostButton { background: #252A36; color: #E5E7EB; }
            #ghostButton:hover { background: #313849; }
            """
        )

    def _set_control_margin(self, value: int) -> None:
        v = int(value)
        self.mapper.frame_r = max(10, min(260, v))
        self._region_label.setText(f"Control margin: {self.mapper.frame_r}")

    def start_camera(self) -> None:
        if self.running:
            return

        if self._mediapipe_error:
            self.preview.setText(self._mediapipe_error)
            return

        if self.tracker is not None:
            self.tracker.close()
        try:
            self.tracker = HandTracker(320, 240)
        except Exception as exc:
            self.tracker = None
            self._mediapipe_error = str(exc)
            self.cam_status.setText("MediaPipe Error")
            self.preview.setText(self._mediapipe_error)
            self.start_btn.setEnabled(False)
            return
        self.gestures = GestureEngine()

        if not self.camera.start():
            self.preview.setText("Cannot open camera")
            return

        self.running = True
        self.proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.proc_thread.start()

        self.cam_status.setText("Camera Active")
        self._status_dot.setObjectName("statusOnline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_camera(self) -> None:
        self.running = False
        if self.proc_thread and self.proc_thread.is_alive():
            self.proc_thread.join(timeout=1.5)
        self.proc_thread = None

        self.camera.stop()
        if self.mouse.is_dragging:
            self.mouse.end_drag()

        self.mapper.reset()
        with self._lock:
            self._frame = None
            self._gesture = GestureType.PAUSE
            self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
            self._fingers = 0
            self._hand_proto = None

        self.preview.setPixmap(QPixmap())
        self.preview.setText("Camera Offline")
        self.cam_status.setText("Camera Offline")
        self._status_dot.setObjectName("statusOffline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None

    def closeEvent(self, event) -> None:
        try:
            self.stop_camera()
        except Exception:
            pass
        try:
            if self.tracker is not None:
                self.tracker.close()
        except Exception:
            pass
        try:
            if self._overlay is not None:
                self._overlay.close()
        except Exception:
            pass
        event.accept()

    def toggle_mouse(self) -> None:
        self.mouse_enabled = not self.mouse_enabled
        if self.mouse_enabled:
            self.mouse_btn.setText("Disable Mouse")
            self.mouse_lbl.setText("Mouse: ON")

            if self._overlay is None:
                self._overlay = StatusOverlay()
                self._overlay.open_btn.clicked.connect(self._show_main_window)
                self._overlay.disable_btn.clicked.connect(self._disable_mouse_from_overlay)
                # Top-right-ish.
                try:
                    sw, _ = pyautogui.size()
                    self._overlay.move(max(10, sw - self._overlay.width() - 20), 20)
                except Exception:
                    self._overlay.move(20, 20)
                self._overlay.show()

            # Minimize the main UI when mouse control is active.
            self.showMinimized()
        else:
            self.mouse_btn.setText("Enable Mouse")
            self.mouse_lbl.setText("Mouse: OFF")

            if self._overlay is not None:
                self._overlay.close()
                self._overlay = None
            self.showNormal()
            self.raise_()

    def _show_main_window(self) -> None:
        self.showNormal()
        self.raise_()

    def _disable_mouse_from_overlay(self) -> None:
        if self.mouse_enabled:
            self.toggle_mouse()

    def _process_loop(self) -> None:
        last_overlay = GestureType.NONE
        last_action = GestureType.NONE
        last_task_view_action = 0.0

        _boost_runtime_priority()
        try:
            cv2.setUseOptimized(True)
        except Exception:
            pass

        while self.running:
            frame = self.camera.latest()
            if frame is None:
                time.sleep(0.001)
                continue

            frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            self.mapper.set_camera_size(w, h)

            tracker = self.tracker
            if tracker is None:
                time.sleep(0.01)
                continue
            hand_data, hand_proto = tracker.detect(frame)
            result = self.gestures.detect(hand_data)
            gesture = result.gesture
            gesture_changed = gesture != last_action

            if self.mouse_enabled and gesture == GestureType.TASK_VIEW and gesture_changed:
                now = time.monotonic()
                if now - last_task_view_action >= 1.0:
                    last_task_view_action = now
                    try:
                        pyautogui.hotkey("winleft", "tab")
                    except Exception:
                        pass

            fingers = 0
            if hand_data is not None:
                fs = self.gestures._finger_states(hand_data["xy"])
                fingers = int(fs.thumb) + int(fs.index) + int(fs.middle) + int(fs.ring) + int(fs.pinky)

            if self.mouse_enabled and hand_data and gesture not in {GestureType.NONE, GestureType.PAUSE, GestureType.TASK_VIEW}:
                tip = hand_data["xy"][8]
                cam_x = int((tip[0] / float(tracker.process_w)) * w)
                cam_y = int((tip[1] / float(tracker.process_h)) * h)
                sx, sy = self.mapper.map_point(cam_x, cam_y)

                if gesture == GestureType.MOVE:
                    self.mouse.move(sx, sy)
                elif gesture == GestureType.LEFT_CLICK and gesture_changed:
                    self.mouse.move(sx, sy)
                    self.mouse.left_click()
                elif gesture == GestureType.RIGHT_CLICK and gesture_changed:
                    self.mouse.right_click()
                elif gesture == GestureType.SCROLL:
                    self.mouse.scroll(result.scroll_delta)
                elif gesture == GestureType.DRAG:
                    self.mouse.move(sx, sy)
                    self.mouse.start_drag()

                if gesture != GestureType.DRAG and self.mouse.is_dragging:
                    self.mouse.end_drag()

            elif self.mouse.is_dragging:
                self.mouse.end_drag()

            if gesture != last_overlay:
                overlay = _OVERLAY_LABELS.get(gesture, "")
                last_overlay = gesture
            else:
                overlay = self._overlay_text

            last_action = gesture

            now = time.monotonic()
            dt = now - self._fps_prev
            self._fps_prev = now
            if dt > 0:
                fps_i = 1.0 / dt
                self.fps = fps_i if self.fps == 0 else 0.9 * self.fps + 0.1 * fps_i

            with self._lock:
                self._frame = frame
                self._gesture = gesture
                self._overlay_text = overlay
                self._fingers = fingers
                self._hand_proto = hand_proto

    def _render(self) -> None:
        with self._lock:
            frame = self._frame
            gesture = self._gesture
            overlay = self._overlay_text
            fingers = self._fingers
            hand_proto = self._hand_proto

        self.fps_lbl.setText(f"FPS {self.fps:.0f}")
        self.gesture_lbl.setText(gesture.value)
        self.gesture_lbl.setStyleSheet(
            f"border-radius: 12px; padding: 6px 10px; font-weight: 700; background: {_BADGE_COLORS.get(gesture, '#64748B')}; color: #0B1118;"
        )
        self.fingers_lbl.setText(f"Fingers: {fingers}")
        self.hand_lbl.setText("Hand: Detected" if hand_proto is not None else "Hand: Not Detected")

        if self._overlay is not None:
            try:
                self._overlay.update_status(gesture, self.fps, hand_proto is not None)
            except Exception:
                pass

        # When minimized (mouse control mode), keep the overlay responsive and
        # avoid spending CPU on preview rendering.
        if self.isMinimized():
            return

        if frame is None:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        x1, y1, x2, y2 = self.mapper.control_region()
        cv2.rectangle(rgb, (x1, y1), (x2, y2), (96, 165, 250), 2)

        tracker = self.tracker
        if self.debug and hand_proto is not None and tracker is not None:
            tracker.draw(rgb, hand_proto)

        cv2.putText(
            rgb,
            f"Fingers: {fingers}",
            (16, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (110, 220, 190),
            2,
            cv2.LINE_AA,
        )

        if overlay:
            (tw, th), bl = cv2.getTextSize(overlay, cv2.FONT_HERSHEY_SIMPLEX, 0.85, 2)
            px = rgb.shape[1] - tw - 48
            py = 22
            bw = tw + 28
            bh = th + bl + 20
            ov = rgb.copy()
            cv2.rectangle(ov, (px, py), (px + bw, py + bh), (32, 38, 52), -1)
            cv2.addWeighted(ov, 0.65, rgb, 0.35, 0, rgb)
            cv2.putText(
                rgb,
                overlay,
                (px + 14, py + bh - 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.85,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.preview.setPixmap(
            pix.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )


def main() -> None:
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
