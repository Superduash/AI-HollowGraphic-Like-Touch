"""PySide6 main window for Holographic Touch."""

from __future__ import annotations

import threading
import time
import sys
from pathlib import Path

import cv2
import pyautogui
from PySide6.QtCore import QTimer, Qt, QSize
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

from config import CAMERA_HEIGHT, CAMERA_WIDTH, PROCESS_HEIGHT, PROCESS_WIDTH, TARGET_FPS
from controller.cursor_mapper import CursorMapper
from controller.mouse_controller import MouseController
from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType
from tracking.hand_tracker import HandTracker
from tracking.landmark_processor import get_finger_states
from utils.camera_thread import CameraThread
from utils.fps_counter import FPSCounter

_OVERLAY_LABELS = {
    GestureType.NONE: "PAUSED",
    GestureType.MOVE: "MOVE",
    GestureType.LEFT_CLICK: "CLICK",
    GestureType.DOUBLE_CLICK: "DOUBLE",
    GestureType.RIGHT_CLICK: "RIGHT CLICK",
    GestureType.SCROLL: "SCROLL",
    GestureType.DRAG: "DRAG",
    GestureType.PAUSE: "PAUSED",
    GestureType.TASK_VIEW: "TASK VIEW",
}

_BADGE_COLORS = {
    GestureType.MOVE: "#60A5FA",
    GestureType.LEFT_CLICK: "#4ADE80",
    GestureType.RIGHT_CLICK: "#4ADE80",
    GestureType.DOUBLE_CLICK: "#4ADE80",
    GestureType.SCROLL: "#A78BFA",
    GestureType.DRAG: "#A78BFA",
    GestureType.PAUSE: "#F87171",
    GestureType.TASK_VIEW: "#A78BFA",
    GestureType.NONE: "#64748B",
}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self._app = QApplication.instance()
        self.setWindowTitle("Holographic Touch")
        self.resize(1280, 820)
        self.setMinimumSize(1024, 680)

        self._camera = CameraThread()
        self._tracker = HandTracker()
        self._detector = GestureDetector()
        self._detector.set_confirm_frames(3)
        self._fps = FPSCounter(target_fps=TARGET_FPS)

        try:
            sw, sh = pyautogui.size()
        except Exception:
            sw, sh = 1920, 1080
        self._mapper = CursorMapper(CAMERA_WIDTH, CAMERA_HEIGHT, sw, sh)
        self._mouse = MouseController()

        self._lock = threading.Lock()
        self._processing = False
        self._proc_thread = None
        self._closing = False
        self._mouse_enabled = False
        self._perf_mode = False
        self._debug_mode = True
        self._was_dragging = False
        self._last_task_view_action = 0.0

        self._disp_frame = None
        self._gesture = GestureType.PAUSE
        self._hand_ok = False
        self._fps_val = 0.0
        self._overlay_text = ""
        self._fingers_count = 0

        self._icons_dir = Path(__file__).resolve().parents[2] / "assets" / "icons"

        self._build_ui()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_gui)
        self._timer.start(16)

    def mainloop(self) -> None:
        app = QApplication.instance()
        created = False
        if app is None:
            app = QApplication([])
            created = True
        self.show()
        app.exec()
        if created:
            del app

    def closeEvent(self, event) -> None:
        self._closing = True
        self._stop_camera()
        try:
            self._tracker.close()
        except Exception:
            pass
        event.accept()

    def _icon(self, name: str) -> QIcon:
        p = self._icons_dir / name
        return QIcon(str(p)) if p.exists() else QIcon()

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setPixmap(self._icon("camera.svg").pixmap(QSize(22, 22)))
        title = QLabel("Holographic Touch")
        title.setObjectName("title")

        header_layout.addWidget(icon_label)
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusOffline")
        self._status_text = QLabel("Camera Offline")
        self._fps_label = QLabel("FPS 0")

        header_layout.addWidget(self._status_dot)
        header_layout.addWidget(self._status_text)
        header_layout.addSpacing(10)
        header_layout.addWidget(self._fps_label)
        header_layout.addSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(14)

        cam_card = QFrame()
        cam_card.setObjectName("cameraCard")
        cam_layout = QVBoxLayout(cam_card)
        cam_layout.setContentsMargins(12, 12, 12, 12)

        self._preview = QLabel("Camera Offline")
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setObjectName("preview")
        self._preview.setMinimumSize(760, 520)
        cam_layout.addWidget(self._preview, 1)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(12)

        status_card = QFrame()
        status_card.setObjectName("sideCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 14, 14, 14)
        status_layout.setSpacing(8)

        status_title = QLabel("Gesture Status")
        status_title.setObjectName("cardTitle")
        self._gesture_badge = QLabel("PAUSE")
        self._gesture_badge.setObjectName("badge")
        self._hand_label = QLabel("Hand: Not Detected")
        self._mouse_label = QLabel("Mouse: OFF")
        self._fingers_label = QLabel("Fingers: 0")

        status_layout.addWidget(status_title)
        status_layout.addWidget(self._gesture_badge)
        status_layout.addWidget(self._hand_label)
        status_layout.addWidget(self._mouse_label)
        status_layout.addWidget(self._fingers_label)

        guide_card = QFrame()
        guide_card.setObjectName("sideCard")
        guide_layout = QGridLayout(guide_card)
        guide_layout.setContentsMargins(14, 14, 14, 14)
        guide_layout.setHorizontalSpacing(10)
        guide_layout.setVerticalSpacing(8)

        guide_title = QLabel("Gesture Guide")
        guide_title.setObjectName("cardTitle")
        guide_layout.addWidget(guide_title, 0, 0, 1, 3)

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
            guide_layout.addWidget(il, i, 0)
            guide_layout.addWidget(tl, i, 1)
            guide_layout.addWidget(dl, i, 2)

        sidebar.addWidget(status_card)
        sidebar.addWidget(guide_card, 1)

        body.addWidget(cam_card, 1)

        side_wrap = QWidget()
        side_wrap.setLayout(sidebar)
        side_wrap.setMinimumWidth(360)
        body.addWidget(side_wrap)

        controls = QFrame()
        controls.setObjectName("controlCard")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(16, 12, 16, 12)
        controls_layout.setSpacing(10)

        self._start_btn = QPushButton("Start Camera")
        self._start_btn.setIcon(self._icon("camera.svg"))
        self._start_btn.setObjectName("greenButton")
        self._start_btn.clicked.connect(self._start_camera)

        self._stop_btn = QPushButton("Stop Camera")
        self._stop_btn.setIcon(self._icon("stop.svg"))
        self._stop_btn.setObjectName("redButton")
        self._stop_btn.clicked.connect(self._stop_camera)
        self._stop_btn.setEnabled(False)

        self._mouse_btn = QPushButton("Enable Mouse")
        self._mouse_btn.setIcon(self._icon("mouse.svg"))
        self._mouse_btn.setObjectName("blueButton")
        self._mouse_btn.clicked.connect(self._toggle_mouse)

        self._region_label = QLabel(f"Control margin: {self._mapper.frame_r}")
        self._region_label.setObjectName("muted")
        self._region_slider = QSlider(Qt.Orientation.Horizontal)
        self._region_slider.setRange(40, 200)
        self._region_slider.setValue(int(self._mapper.frame_r))
        self._region_slider.setFixedWidth(180)
        self._region_slider.valueChanged.connect(self._set_control_margin)


        controls_layout.addWidget(self._start_btn)
        controls_layout.addWidget(self._stop_btn)
        controls_layout.addWidget(self._mouse_btn)
        controls_layout.addSpacing(8)
        controls_layout.addWidget(self._region_label)
        controls_layout.addWidget(self._region_slider)
        controls_layout.addStretch(1)

        layout.addWidget(header)

        body_wrap = QWidget()
        body_wrap.setLayout(body)
        layout.addWidget(body_wrap, 1)

        layout.addWidget(controls)

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
        # Lower margin => bigger blue rectangle (more movement area).
        v = int(value)
        self._mapper.frame_r = max(10, min(260, v))
        self._region_label.setText(f"Control margin: {self._mapper.frame_r}")

    def _start_camera(self) -> None:
        if self._processing:
            return
        try:
            self._tracker.close()
        except Exception:
            pass
        self._tracker = HandTracker()
        self._detector = GestureDetector()
        self._detector.set_confirm_frames(3)

        if not self._camera.start():
            self._status_text.setText("Camera Error")
            self._status_dot.setObjectName("statusOffline")
            self._status_dot.style().unpolish(self._status_dot)
            self._status_dot.style().polish(self._status_dot)
            self._preview.setText("Cannot open camera")
            return

        self._processing = True
        self._proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._proc_thread.start()

        self._status_text.setText("Camera Active")
        self._status_dot.setObjectName("statusOnline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)

    def _stop_camera(self) -> None:
        self._processing = False
        if self._proc_thread and self._proc_thread.is_alive():
            self._proc_thread.join(timeout=2.0)
        self._proc_thread = None

        self._camera.stop()
        if self._mouse.is_dragging:
            self._mouse.end_drag()
        self._was_dragging = False
        self._mapper.reset()

        with self._lock:
            self._disp_frame = None
            self._gesture = GestureType.PAUSE
            self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
            self._fingers_count = 0
            self._hand_ok = False

        self._status_text.setText("Camera Offline")
        self._status_dot.setObjectName("statusOffline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self._preview.setPixmap(QPixmap())
        self._preview.setText("Camera Offline")
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def _toggle_mouse(self) -> None:
        self._mouse_enabled = not self._mouse_enabled
        if self._mouse_enabled:
            self._mouse_btn.setText("Disable Mouse")
            self._mouse_label.setText("Mouse: ON")
        else:
            self._mouse_btn.setText("Enable Mouse")
            self._mouse_label.setText("Mouse: OFF")

    def _process_loop(self) -> None:
        last_overlay_gesture = GestureType.NONE
        last_action_gesture = GestureType.NONE

        while self._processing:
            if not self._camera.is_running:
                self._processing = False
                break

            frame = self._camera.get_frame()
            if frame is None:
                time.sleep(0.004)
                continue

            frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            self._mapper.set_camera_size(fw, fh)

            hand_data, raw_hand = self._tracker.process_frame(frame)
            result = self._detector.detect(hand_data)
            gesture = result.gesture
            gesture_changed = gesture != last_action_gesture

            if self._mouse_enabled and gesture == GestureType.TASK_VIEW and gesture_changed:
                now = time.monotonic()
                if now - self._last_task_view_action >= 1.0:
                    self._last_task_view_action = now
                    if sys.platform.startswith("win"):
                        try:
                            pyautogui.hotkey("winleft", "tab")
                        except Exception:
                            pass

            fingers_count = 0
            if hand_data and isinstance(hand_data, dict):
                xy = hand_data.get("xy")
                if xy:
                    fs = get_finger_states(xy)
                    fingers_count = int(fs.thumb) + int(fs.index) + int(fs.middle) + int(fs.ring) + int(fs.pinky)

            if self._mouse_enabled and hand_data and gesture not in {GestureType.PAUSE, GestureType.NONE, GestureType.TASK_VIEW}:
                xy = hand_data.get("xy")
                if xy and len(xy) > 8:
                    tip_x, tip_y = xy[8]
                    cam_x = int((tip_x / PROCESS_WIDTH) * fw)
                    cam_y = int((tip_y / PROCESS_HEIGHT) * fh)
                    sx, sy = self._mapper.map_to_screen(cam_x, cam_y)

                    if gesture == GestureType.MOVE:
                        self._mouse.move_cursor(sx, sy)
                    elif gesture == GestureType.LEFT_CLICK and gesture_changed:
                        self._mouse.move_cursor(sx, sy)
                        self._mouse.left_click()
                    elif gesture == GestureType.RIGHT_CLICK and gesture_changed:
                        self._mouse.right_click()
                    elif gesture == GestureType.DOUBLE_CLICK and gesture_changed:
                        self._mouse.double_click()
                    elif gesture == GestureType.SCROLL and result.scroll_delta != 0:
                        self._mouse.scroll(result.scroll_delta)
                    elif gesture == GestureType.DRAG:
                        self._mouse.move_cursor(sx, sy)
                        if not self._was_dragging:
                            self._mouse.start_drag()

                    if self._was_dragging and gesture != GestureType.DRAG:
                        self._mouse.end_drag()
                    self._was_dragging = gesture == GestureType.DRAG

            elif self._was_dragging:
                self._mouse.end_drag()
                self._was_dragging = False

            last_action_gesture = gesture
            if gesture != last_overlay_gesture:
                overlay_text = _OVERLAY_LABELS.get(gesture, "")
                last_overlay_gesture = gesture
            else:
                overlay_text = self._overlay_text

            fps_v = self._fps.update()
            with self._lock:
                self._disp_frame = frame
                self._gesture = gesture
                self._hand_ok = hand_data is not None
                self._fps_val = fps_v
                self._overlay_text = overlay_text
                self._fingers_count = fingers_count
                self._raw_hand = raw_hand

    def _update_gui(self) -> None:
        if self._closing:
            return

        with self._lock:
            frame = self._disp_frame
            gesture = self._gesture
            hand_ok = self._hand_ok
            fps_v = self._fps_val
            overlay_text = self._overlay_text
            fingers_count = self._fingers_count
            raw_hand = getattr(self, "_raw_hand", None)

        self._fps_label.setText(f"FPS {fps_v:.0f}")
        self._gesture_badge.setText(gesture.value)
        self._gesture_badge.setStyleSheet(
            f"border-radius: 12px; padding: 6px 10px; font-weight: 700; background: {_BADGE_COLORS.get(gesture, '#64748B')}; color: #0B1118;"
        )
        self._hand_label.setText(f"Hand: {'Detected' if hand_ok else 'Not Detected'}")
        self._fingers_label.setText(f"Fingers: {fingers_count}")

        if frame is None:
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        x1, y1, x2, y2 = self._mapper.control_region()
        cv2.rectangle(rgb, (x1, y1), (x2, y2), (96, 165, 250), 2)

        if self._debug_mode and not self._perf_mode and raw_hand is not None:
            self._tracker.draw_landmarks(rgb, raw_hand)

        cv2.putText(
            rgb,
            f"Fingers: {fingers_count}",
            (18, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (120, 220, 200),
            2,
            cv2.LINE_AA,
        )

        if overlay_text:
            (tw, th), baseline = cv2.getTextSize(overlay_text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            pad = 12
            x = rgb.shape[1] - tw - pad * 2 - 20
            y = 24
            w = tw + pad * 2
            h = th + baseline + pad * 2
            overlay = rgb.copy()
            cv2.rectangle(overlay, (x, y), (x + w, y + h), (40, 45, 58), -1)
            cv2.addWeighted(overlay, 0.65, rgb, 0.35, 0, rgb)
            cv2.putText(
                rgb,
                overlay_text,
                (x + pad, y + h - pad - baseline),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg.copy())
        self._preview.setPixmap(
            pix.scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
