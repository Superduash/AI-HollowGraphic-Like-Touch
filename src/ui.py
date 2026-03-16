from __future__ import annotations

import platform
import threading
import time
from pathlib import Path

import cv2
import pyautogui
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
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

from .camera import CameraSource
from .constants import _BADGE_COLORS, _OVERLAY_LABELS
from .engine import GestureEngine
from .mapper import CursorMapper
from .models import GestureType
from .mouse import MouseController
from .tracker import HandTracker
from .utils import _boost_runtime_priority, _configure_input_latency


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
        self.debug = True
        self._overlay: StatusOverlay | None = None

        # Self-contained: use assets shipped inside the app directory.
        self._icons_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"

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

        self._last_esc_time = 0.0
        try:
            import keyboard  # type: ignore
            keyboard.on_press_key("esc", self._on_esc_press)
        except Exception:
            pass

    def _on_esc_press(self, event=None) -> None:
        now = time.monotonic()
        if now - self._last_esc_time < 0.5:
            self._last_esc_time = 0.0
            QTimer.singleShot(0, self._execute_panic)
        else:
            self._last_esc_time = now

    def _execute_panic(self) -> None:
        if self.mouse_enabled:
            self.toggle_mouse()
        if self.mouse.is_dragging:
            self.mouse.end_drag()

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
            ("click.svg", "Index down + Thumb + Middle pinch", "Right click"),
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

            if self.mouse_enabled and gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN, GestureType.MEDIA_NEXT, GestureType.MEDIA_PREV):
                if gesture_changed or gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN):
                    if gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN) and result.scroll_delta == 0:
                        pass
                    else:
                        self._execute_media(gesture, result.scroll_delta)

            if self.mouse_enabled and hand_data and gesture not in {GestureType.NONE, GestureType.PAUSE, GestureType.TASK_VIEW, GestureType.KEYBOARD}:
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

    def _execute_media(self, gesture: GestureType, delta: int) -> None:
        def _run():
            try:
                import ctypes
                user32 = ctypes.windll.user32
                vk = 0
                if gesture == GestureType.MEDIA_VOL_UP: vk = 0xAF
                elif gesture == GestureType.MEDIA_VOL_DOWN: vk = 0xAE
                elif gesture == GestureType.MEDIA_NEXT: vk = 0xB0
                elif gesture == GestureType.MEDIA_PREV: vk = 0xB1
                if vk:
                    count = max(1, delta) if gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN) else 1
                    for _ in range(count):
                        user32.keybd_event(vk, 0, 0, 0)
                        user32.keybd_event(vk, 0, 2, 0)
            except Exception:
                pass
        threading.Thread(target=_run, daemon=True).start()
