"""Main application window implemented with PySide6."""

import sys
import threading
import time
from pathlib import Path

import cv2
import pyautogui
from PIL import Image
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config import CAMERA_HEIGHT, CAMERA_WIDTH, PROCESS_HEIGHT, PROCESS_WIDTH, TARGET_FPS
from controller.cursor_mapper import CursorMapper
from controller.mouse_controller import MouseController
from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType
from tracking.hand_tracker import HandTracker
from utils.camera_thread import CameraThread
from utils.fps_counter import FPSCounter

_PAUSE_GESTURES = frozenset({GestureType.PAUSE, GestureType.NONE})
_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"

_BADGE_COLORS = {
    "IDLE": "#374151",
    "MOVE": "#60A5FA",
    "CLICK": "#4ADE80",
    "R-CLICK": "#4ADE80",
    "SCROLL": "#A78BFA",
    "DRAG": "#4ADE80",
    "PAUSE": "#F87171",
}


class GlassButton(QPushButton):
    """Rounded button with subtle hover animation."""

    def __init__(self, text: str = ""):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setColor(Qt.GlobalColor.black)
        self._shadow.setBlurRadius(10.0)
        self._shadow.setOffset(0, 2)
        self.setGraphicsEffect(self._shadow)

        self._anim = QPropertyAnimation(self._shadow, b"blurRadius", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(18.0)
        self._anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim.stop()
        self._anim.setStartValue(self._shadow.blurRadius())
        self._anim.setEndValue(10.0)
        self._anim.start()
        super().leaveEvent(event)


class MainWindow(QMainWindow):
    def __init__(self):
        self._app = QApplication.instance() or QApplication(sys.argv)
        super().__init__()

        self.setWindowTitle("Holographic Touch")
        self.resize(1280, 820)
        self.setMinimumSize(1120, 720)

        self._camera = CameraThread()
        self._tracker = HandTracker()
        self._detector = GestureDetector()
        self._detector.set_confirm_frames(4)
        self._fps = FPSCounter(target_fps=TARGET_FPS)

        try:
            sw, sh = pyautogui.size()
        except Exception:
            sw, sh = 1920, 1080

        self._mapper = CursorMapper(CAMERA_WIDTH, CAMERA_HEIGHT, sw, sh)
        self._mouse = MouseController()

        self._processing = False
        self._proc_thread = None
        self._mouse_enabled = False
        self._perf_mode = False
        self._debug_mode = True
        self._was_dragging = False
        self._closing = False

        self._lock = threading.Lock()
        self._disp_frame = None
        self._gesture = GestureType.NONE
        self._hand_ok = False
        self._raw_hand = None
        self._fps_val = 0.0
        self._error_msg = ""
        self._overlay_label = ""
        self._last_overlay_text = "IDLE"

        self._preview_pixmap = QPixmap()

        self._build_ui()

        self._ui_timer = QTimer(self)
        self._ui_timer.setInterval(16)
        self._ui_timer.timeout.connect(self._update_gui)

    def mainloop(self):
        self.show()
        return self._app.exec()

    def _build_ui(self):
        root = QWidget(self)
        root.setObjectName("Root")
        self.setCentralWidget(root)

        self.setStyleSheet(
            """
            QMainWindow {
                background: #0F1115;
            }
            QWidget#Root {
                background: qradialgradient(
                    cx: 0.15, cy: 0.05, radius: 1.2,
                    fx: 0.15, fy: 0.05,
                    stop: 0 rgba(44, 68, 110, 92),
                    stop: 0.4 rgba(18, 25, 39, 80),
                    stop: 1 rgba(15, 17, 21, 255)
                );
                color: #E5E7EB;
                font-family: "SF Pro Text", "Manrope", "Inter", sans-serif;
                font-size: 14px;
            }
            QFrame#Shell {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(22, 30, 45, 205),
                    stop: 0.6 rgba(20, 28, 40, 215),
                    stop: 1 rgba(18, 26, 37, 225)
                );
                border: 1px solid rgba(141, 173, 219, 70);
                border-radius: 26px;
            }
            QFrame#Card {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(31, 42, 61, 170),
                    stop: 1 rgba(26, 34, 49, 185)
                );
                border: 1px solid rgba(147, 183, 235, 58);
                border-radius: 20px;
            }
            QFrame#PreviewViewport {
                background: #0A1019;
                border: 1px solid rgba(139, 241, 203, 120);
                border-radius: 18px;
            }
            QLabel#Title {
                font-size: 32px;
                font-weight: 700;
                color: #F3F7FF;
            }
            QLabel#Muted {
                color: #9DB0CE;
                font-size: 15px;
            }
            QLabel#SectionTitle {
                color: #DEE7F7;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#OverlayPill {
                color: #E9FFF8;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(73, 197, 140, 128),
                    stop: 1 rgba(91, 187, 250, 90)
                );
                border: 1px solid rgba(162, 255, 222, 180);
                border-radius: 16px;
                padding: 6px 14px;
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 0.4px;
            }
            QLabel#GestureBadge {
                border-radius: 14px;
                padding: 8px 14px;
                color: #F7FAFF;
                font-weight: 700;
                font-size: 17px;
            }
            QLabel#GuideText {
                color: #CEDAF0;
                font-size: 14px;
            }
            QLabel#GuideHint {
                color: #9AB0D4;
                font-size: 13px;
            }
            QPushButton {
                background: rgba(33, 46, 67, 220);
                border: 1px solid rgba(137, 171, 224, 95);
                border-radius: 14px;
                color: #EAF1FF;
                padding: 11px 16px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(42, 60, 89, 230);
                border: 1px solid rgba(162, 206, 255, 155);
            }
            QPushButton:disabled {
                background: rgba(22, 30, 45, 150);
                border: 1px solid rgba(102, 120, 150, 70);
                color: rgba(201, 214, 237, 120);
            }
            QPushButton[variant="start"] {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(74, 222, 128, 210),
                    stop: 1 rgba(46, 189, 109, 225)
                );
                border: 1px solid rgba(177, 255, 204, 170);
                color: #EDFFF5;
            }
            QPushButton[variant="stop"] {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(248, 113, 113, 215),
                    stop: 1 rgba(210, 72, 87, 230)
                );
                border: 1px solid rgba(255, 200, 208, 170);
                color: #FFF6F7;
            }
            QPushButton[variant="mouse"][active="true"] {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(88, 205, 177, 220),
                    stop: 1 rgba(65, 171, 151, 220)
                );
                border: 1px solid rgba(175, 255, 238, 185);
                color: #F0FFFC;
            }
            """
        )

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("Shell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(20, 20, 20, 20)
        shell_layout.setSpacing(14)
        root_layout.addWidget(shell)

        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 2, 8, 2)
        header_layout.setSpacing(10)

        title_icon = QLabel()
        title_icon.setPixmap(self._icon("move").pixmap(QSize(24, 24)))
        header_layout.addWidget(title_icon)

        title = QLabel("Holographic Touch")
        title.setObjectName("Title")
        header_layout.addWidget(title)
        header_layout.addStretch(1)

        self._status_dot = QLabel("●")
        self._status_dot.setStyleSheet("color: #F87171; font-size: 15px;")
        header_layout.addWidget(self._status_dot)

        self._status_text = QLabel("Offline")
        self._status_text.setObjectName("Muted")
        header_layout.addWidget(self._status_text)

        divider = QLabel("| |")
        divider.setObjectName("Muted")
        header_layout.addWidget(divider)

        self._fps_lbl = QLabel("FPS: 0")
        self._fps_lbl.setObjectName("Muted")
        header_layout.addWidget(self._fps_lbl)

        self._header_settings = GlassButton("")
        self._header_settings.setIcon(self._icon("settings"))
        self._header_settings.setIconSize(QSize(18, 18))
        self._header_settings.setFixedSize(40, 40)
        self._header_settings.setEnabled(False)
        header_layout.addWidget(self._header_settings)

        shell_layout.addWidget(header)

        center = QHBoxLayout()
        center.setSpacing(14)

        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(10)

        preview_title = QLabel("Live Camera")
        preview_title.setObjectName("SectionTitle")
        preview_layout.addWidget(preview_title)

        viewport = QFrame()
        viewport.setObjectName("PreviewViewport")
        viewport_layout = QGridLayout(viewport)
        viewport_layout.setContentsMargins(0, 0, 0, 0)

        self._preview_image = QLabel("Camera Offline")
        self._preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_image.setMinimumSize(640, 430)
        self._preview_image.setObjectName("Muted")
        viewport_layout.addWidget(self._preview_image, 0, 0)

        overlay_top = QWidget()
        overlay_top.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay_top_layout = QHBoxLayout(overlay_top)
        overlay_top_layout.setContentsMargins(0, 10, 12, 0)
        overlay_top_layout.addStretch(1)

        self._overlay_pill = QLabel("IDLE")
        self._overlay_pill.setObjectName("OverlayPill")
        overlay_top_layout.addWidget(self._overlay_pill)
        viewport_layout.addWidget(overlay_top, 0, 0, Qt.AlignmentFlag.AlignTop)

        overlay_bottom = QWidget()
        overlay_bottom.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        overlay_bottom_layout = QHBoxLayout(overlay_bottom)
        overlay_bottom_layout.setContentsMargins(14, 0, 14, 10)

        self._finger_overlay = QLabel("Detected Fingers: -")
        self._finger_overlay.setObjectName("Muted")
        overlay_bottom_layout.addWidget(self._finger_overlay)
        overlay_bottom_layout.addStretch(1)

        self._fps_overlay = QLabel("FPS: 0")
        self._fps_overlay.setObjectName("Muted")
        overlay_bottom_layout.addWidget(self._fps_overlay)
        viewport_layout.addWidget(overlay_bottom, 0, 0, Qt.AlignmentFlag.AlignBottom)

        preview_layout.addWidget(viewport, 1)
        center.addWidget(preview_card, 4)

        sidebar = QVBoxLayout()
        sidebar.setSpacing(14)

        status_card = QFrame()
        status_card.setObjectName("Card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 14, 14, 14)
        status_layout.setSpacing(10)

        status_title = QLabel("Gesture Status")
        status_title.setObjectName("SectionTitle")
        status_layout.addWidget(status_title)

        self._gesture_badge = QLabel("IDLE")
        self._gesture_badge.setObjectName("GestureBadge")
        status_layout.addWidget(self._gesture_badge)

        self._hand_status = QLabel("Hand: Not Detected")
        self._hand_status.setObjectName("Muted")
        status_layout.addWidget(self._hand_status)

        self._mouse_status = QLabel("Mouse: Disabled")
        self._mouse_status.setObjectName("Muted")
        status_layout.addWidget(self._mouse_status)

        sidebar.addWidget(status_card)

        guide_card = QFrame()
        guide_card.setObjectName("Card")
        guide_layout = QVBoxLayout(guide_card)
        guide_layout.setContentsMargins(14, 14, 14, 14)
        guide_layout.setSpacing(12)

        guide_title = QLabel("Air-Touch Guide")
        guide_title.setObjectName("SectionTitle")
        guide_layout.addWidget(guide_title)

        for icon_name, title_text, hint_text in [
            ("move", "Index hover", "Move cursor"),
            ("click", "Forward finger tap", "Left click"),
            ("drag", "Forward hold", "Drag"),
            ("click", "Two finger tap", "Right click"),
            ("scroll", "Vertical swipe", "Scroll"),
            ("pause", "Open palm", "Pause"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            icon_label = QLabel()
            icon_label.setPixmap(self._icon(icon_name).pixmap(QSize(18, 18)))
            row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            primary = QLabel(title_text)
            primary.setObjectName("GuideText")
            text_col.addWidget(primary)
            hint = QLabel(hint_text)
            hint.setObjectName("GuideHint")
            text_col.addWidget(hint)
            row.addLayout(text_col)
            row.addStretch(1)
            guide_layout.addLayout(row)

        sidebar.addWidget(guide_card)
        sidebar.addStretch(1)

        center.addLayout(sidebar, 2)
        shell_layout.addLayout(center, 1)

        bottom_card = QFrame()
        bottom_card.setObjectName("Card")
        bottom_layout = QHBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(14, 12, 14, 12)
        bottom_layout.setSpacing(10)

        self._btn_start = GlassButton("Start Camera")
        self._btn_start.setProperty("variant", "start")
        self._btn_start.setIcon(self._icon("camera"))
        self._btn_start.clicked.connect(self._start)

        self._btn_stop = GlassButton("Stop Camera")
        self._btn_stop.setProperty("variant", "stop")
        self._btn_stop.setIcon(self._icon("stop"))
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setEnabled(False)

        self._btn_mouse = GlassButton("Enable Mouse")
        self._btn_mouse.setProperty("variant", "mouse")
        self._btn_mouse.setProperty("active", "false")
        self._btn_mouse.setIcon(self._icon("mouse"))
        self._btn_mouse.clicked.connect(self._toggle_mouse)

        self._btn_settings = GlassButton("Settings")
        self._btn_settings.setIcon(self._icon("settings"))
        self._btn_settings.setEnabled(False)

        bottom_layout.addWidget(self._btn_start)
        bottom_layout.addWidget(self._btn_stop)
        bottom_layout.addWidget(self._btn_mouse)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self._btn_settings)

        shell_layout.addWidget(bottom_card)

        self._overlay_opacity = QGraphicsOpacityEffect(self._overlay_pill)
        self._overlay_pill.setGraphicsEffect(self._overlay_opacity)
        self._overlay_fade = QPropertyAnimation(self._overlay_opacity, b"opacity", self)
        self._overlay_fade.setDuration(180)
        self._overlay_fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _icon(self, name: str) -> QIcon:
        path = _ASSETS_DIR / f"{name}.svg"
        if path.exists():
            return QIcon(str(path))
        return QIcon()

    def _status_gesture_name(self, gesture: GestureType) -> str:
        if gesture == GestureType.MOVE:
            return "MOVE"
        if gesture in (GestureType.LEFT_CLICK, GestureType.DOUBLE_CLICK):
            return "CLICK"
        if gesture == GestureType.RIGHT_CLICK:
            return "R-CLICK"
        if gesture == GestureType.SCROLL:
            return "SCROLL"
        if gesture == GestureType.DRAG:
            return "DRAG"
        if gesture in (GestureType.PAUSE, GestureType.OPEN_PALM):
            return "PAUSE"
        return "IDLE"

    def _overlay_name(self, gesture: GestureType) -> str:
        if gesture == GestureType.MOVE:
            return "HOVER MOVE"
        if gesture in (GestureType.LEFT_CLICK, GestureType.DOUBLE_CLICK):
            return "FORWARD TAP"
        if gesture == GestureType.RIGHT_CLICK:
            return "TWO FINGER TAP"
        if gesture == GestureType.SCROLL:
            return "VERTICAL SWIPE"
        if gesture == GestureType.DRAG:
            return "FORWARD HOLD"
        if gesture in (GestureType.PAUSE, GestureType.OPEN_PALM):
            return "OPEN PALM"
        return "IDLE"

    def _animate_overlay_pill(self):
        self._overlay_fade.stop()
        self._overlay_fade.setStartValue(0.35)
        self._overlay_fade.setEndValue(1.0)
        self._overlay_fade.start()

    def _start(self):
        if self._processing or (self._proc_thread and self._proc_thread.is_alive()):
            return

        try:
            self._tracker.close()
        except Exception:
            pass
        self._tracker = HandTracker()

        if not self._camera.start():
            self._preview_image.setText(f"Cannot open camera\n{self._camera.last_error or ''}")
            self._status_dot.setStyleSheet("color: #F87171; font-size: 15px;")
            self._status_text.setText("Error")
            return

        with self._lock:
            self._error_msg = ""
            self._gesture = GestureType.NONE
            self._overlay_label = "IDLE"

        self._processing = True
        self._proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._proc_thread.start()

        self._status_dot.setStyleSheet("color: #4ADE80; font-size: 15px;")
        self._status_text.setText("Online")
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._ui_timer.start()

    def _stop(self):
        was_processing = self._processing
        self._processing = False

        if self._proc_thread and self._proc_thread.is_alive():
            self._proc_thread.join(timeout=2.0)
        self._proc_thread = None

        self._camera.stop()
        try:
            self._tracker.close()
        except Exception:
            pass

        if self._mouse.is_dragging:
            self._mouse.end_drag()
        self._was_dragging = False
        self._mapper.reset()

        with self._lock:
            self._disp_frame = None
            self._gesture = GestureType.NONE
            self._hand_ok = False
            self._raw_hand = None
            self._overlay_label = "IDLE"
            if not was_processing:
                self._error_msg = ""

        self._ui_timer.stop()
        self._preview_image.clear()
        self._preview_image.setText("Camera Offline")
        self._status_dot.setStyleSheet("color: #F87171; font-size: 15px;")
        self._status_text.setText("Offline")
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)

    def _toggle_mouse(self):
        self._mouse_enabled = not self._mouse_enabled
        self._btn_mouse.setText("Disable Mouse" if self._mouse_enabled else "Enable Mouse")
        self._btn_mouse.setProperty("active", "true" if self._mouse_enabled else "false")
        self._btn_mouse.style().unpolish(self._btn_mouse)
        self._btn_mouse.style().polish(self._btn_mouse)

    def _process_loop(self):
        skip = False
        last_action_gesture = GestureType.NONE

        while self._processing:
            if not self._camera.is_running:
                with self._lock:
                    self._error_msg = "Camera disconnected"
                self._processing = False
                break

            frame = self._camera.get_frame()
            if frame is None:
                time.sleep(0.004)
                continue

            frame = cv2.flip(frame, 1)
            fh, fw = frame.shape[:2]
            self._mapper.set_camera_size(fw, fh)

            if skip and self._perf_mode:
                skip = False
                with self._lock:
                    self._disp_frame = frame
                continue

            try:
                landmarks, raw_hand = self._tracker.process_frame(frame)
                result = self._detector.detect(landmarks)
            except Exception:
                landmarks, raw_hand = None, None
                result = self._detector.detect(None)

            gesture = result.gesture
            gesture_changed = gesture != last_action_gesture

            if self._mouse_enabled and landmarks and gesture not in _PAUSE_GESTURES:
                tip = landmarks[8]
                cam_x = int((tip[0] / PROCESS_WIDTH) * fw)
                cam_y = int((tip[1] / PROCESS_HEIGHT) * fh)
                sx, sy = self._mapper.map_to_screen(cam_x, cam_y)

                if gesture == GestureType.MOVE:
                    self._mouse.move_cursor(sx, sy)
                elif gesture == GestureType.LEFT_CLICK and gesture_changed:
                    self._mouse.move_cursor(sx, sy)
                    self._mouse.left_click()
                elif gesture == GestureType.DOUBLE_CLICK and gesture_changed:
                    self._mouse.move_cursor(sx, sy)
                    self._mouse.double_click()
                elif gesture == GestureType.RIGHT_CLICK and gesture_changed:
                    self._mouse.right_click()
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

            with self._lock:
                self._disp_frame = frame
                self._gesture = gesture
                self._hand_ok = landmarks is not None
                self._raw_hand = raw_hand
                self._fps_val = self._fps.update()
                self._overlay_label = self._overlay_name(gesture)

            if self._fps.should_skip():
                skip = True

    def _update_gui(self):
        if self._closing:
            return

        if not self._processing:
            with self._lock:
                err = self._error_msg
            if err:
                self._preview_image.setText(f"Warning: {err}")
                self._btn_start.setEnabled(True)
                self._btn_stop.setEnabled(False)
            return

        with self._lock:
            frame = self._disp_frame
            gesture = self._gesture
            hand = self._hand_ok
            raw_hand = self._raw_hand
            fps = self._fps_val
            overlay_text = self._overlay_label

        if frame is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self._debug_mode and raw_hand:
                self._tracker.draw_landmarks(rgb, raw_hand)

            display_w = max(320, self._preview_image.width())
            display_h = max(240, self._preview_image.height())
            pil_img = Image.fromarray(rgb).resize((display_w, display_h), Image.Resampling.BILINEAR)

            image_data = pil_img.tobytes("raw", "RGB")
            qimg = QImage(image_data, pil_img.width, pil_img.height, QImage.Format.Format_RGB888)
            self._preview_pixmap = QPixmap.fromImage(qimg)
            self._preview_image.setPixmap(
                self._preview_pixmap.scaled(
                    self._preview_image.size(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self._fps_lbl.setText(f"FPS: {fps:.0f}")
        self._fps_overlay.setText(f"FPS: {fps:.0f}")
        self._finger_overlay.setText("Detected Fingers: Present" if hand else "Detected Fingers: -")

        self._hand_status.setText("Hand: Detected" if hand else "Hand: Not Detected")
        self._mouse_status.setText("Mouse: Enabled" if self._mouse_enabled else "Mouse: Disabled")

        badge_text = self._status_gesture_name(gesture)
        badge_color = _BADGE_COLORS.get(badge_text, "#374151")
        self._gesture_badge.setText(badge_text)
        self._gesture_badge.setStyleSheet(
            f"border-radius: 14px; padding: 8px 14px; color: #F7FAFF;"
            f"font-weight: 700; font-size: 17px; background: {badge_color};"
        )

        if overlay_text != self._last_overlay_text:
            self._overlay_pill.setText(overlay_text)
            self._animate_overlay_pill()
            self._last_overlay_text = overlay_text

    def closeEvent(self, event):
        self._closing = True
        self._stop()
        try:
            self._tracker.close()
        except Exception:
            pass
        event.accept()
