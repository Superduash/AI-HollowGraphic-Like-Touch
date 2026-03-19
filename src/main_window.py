from __future__ import annotations

import collections
import ctypes
import platform
import threading
import time
from typing import Any, cast

import cv2  # type: ignore

# ── BUG C FIX: pyautogui configuration for Windows ──
try:
    import pyautogui  # type: ignore
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except ImportError:
    pyautogui = None  # type: ignore

import qtawesome as qta  # type: ignore
from PySide6.QtCore import QMetaObject, QSize, Signal, Slot, Qt, QTimer  # type: ignore
from PySide6.QtGui import QAction, QImage, QPixmap  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .camera_thread import CameraDevice, CameraThread  # type: ignore
from .constants import _OVERLAY_LABELS  # type: ignore
from .cursor_mapper import CursorMapper  # type: ignore
from .gesture_detector import GestureDetector  # type: ignore
from .hand_tracker import HandTracker  # type: ignore
from .models import GestureResult, GestureType  # type: ignore
from .mouse import MouseController  # type: ignore
from .settings_store import settings  # type: ignore
from .utils import _boost_runtime_priority, _configure_input_latency  # type: ignore


def _as_int(value: object, default: int) -> int:
    try:
        return int(cast(Any, value))
    except Exception:
        return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(cast(Any, value))
    except Exception:
        return default


def _as_bool(value: object, default: bool) -> bool:
    try:
        return bool(value)
    except Exception:
        return default


def _gesture_accent(gesture: GestureType) -> str:
    if gesture in {GestureType.MOVE}:
        return "#00F0FF"
    if gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK, GestureType.DOUBLE_CLICK, GestureType.DRAG}:
        return "#34D399"
    if gesture in {GestureType.SCROLL, GestureType.TASK_VIEW, GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN, GestureType.MEDIA_NEXT, GestureType.MEDIA_PREV}:
        return "#818CF8"
    if gesture == GestureType.KEYBOARD:
        return "#FBBF24"
    if gesture == GestureType.PAUSE:
        return "#F87171"
    return "#8B97B0"


class StatusOverlay(QWidget):
    def __init__(self, icons: dict[str, object]) -> None:
        super().__init__(None)  # type: ignore
        self._icons = icons
        self.setWindowTitle("Windows Hover Status")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(280, 130)
        self._drag_pos = None
        self._last_badge_gesture: GestureType = GestureType.NONE

        root = QFrame(self)
        root.setObjectName("overlayRoot")
        root.setGeometry(0, 0, 280, 130)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self._dot = QLabel("●")
        self._dot.setObjectName("statusOnline")
        self._title = QLabel("Holographic Touch")
        self._title.setObjectName("overlayTitle")
        self._fps = QLabel("FPS 0")
        self._fps.setObjectName("muted")
        top.addWidget(self._dot)
        top.addWidget(self._title)
        top.addStretch(1)
        top.addWidget(self._fps)
        layout.addLayout(top)

        mid = QHBoxLayout()
        self._badge = QLabel("PAUSED")
        self._badge.setObjectName("badge")
        self._hand = QLabel("Hand: -")
        self._hand.setObjectName("muted")
        mid.addWidget(self._badge)
        mid.addWidget(self._hand)
        mid.addStretch(1)
        layout.addLayout(mid)

        btns = QHBoxLayout()
        self.open_btn = QPushButton("Open")
        self.open_btn.setObjectName("ghostButton")
        self.open_btn.setIcon(self._icons["settings"])
        self.open_btn.setIconSize(QSize(18, 18))
        self.disable_btn = QPushButton("Disable Mouse")
        self.disable_btn.setObjectName("redButton")
        self.disable_btn.setIcon(self._icons["pause"])
        self.disable_btn.setIconSize(QSize(18, 18))
        btns.addWidget(self.open_btn)
        btns.addStretch(1)
        btns.addWidget(self.disable_btn)
        layout.addLayout(btns)

        self.setStyleSheet(
            """
            * { font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif; }
            #overlayRoot { background: rgba(9, 9, 11, 0.95); border: 1px solid rgba(34, 211, 238, 0.1); border-radius: 16px; backdrop-filter: blur(20px); }
            QLabel { color: #F1F5F9; font-size: 13px; font-weight: 600; }
            #overlayTitle { font-size: 15px; font-weight: 800; letter-spacing: 0.5px; }
            #muted { color: #8B97B0; }
            #statusOnline { color: #00F0FF; font-size: 18px; }
            #badge {
                border-radius: 10px; padding: 6px 14px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0; 
                text-transform: uppercase; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
                font-size: 12px;
            }
            QPushButton {
                border: 0; border-radius: 12px; color: #021820;
                padding: 8px 12px; font-weight: 700; background: #00F0FF;
            }
            QPushButton:hover { background: #00F0FF; border: 1px solid #00F0FF; }
            #ghostButton { background: #27272A; color: #F1F5F9; }
            #ghostButton:hover { background: #18181B; }
            #redButton { background: #F87171; color: #1A0505; }
            #redButton:hover { background: #F87171; border: 1px solid #F87171; }
            """
        )

    def update_status(self, gesture: GestureType, fps: float, hand_ok: bool) -> None:
        self._fps.setText(f"FPS {fps:.0f}")
        self._hand.setText(f"Hand: {'Detected' if hand_ok else 'Not Detected'}")
        self._badge.setText(gesture.value)
        if gesture != self._last_badge_gesture:
            self._last_badge_gesture = gesture
            color = _gesture_accent(gesture)
            if gesture == GestureType.PAUSE:
                self._badge.setStyleSheet("border-radius: 12px; padding: 6px 12px; font-weight: 800; background: #18181B; color: #F1F5F9;")
            else:
                self._badge.setStyleSheet(
                    f"border-radius: 12px; padding: 6px 12px; font-weight: 800; background: {color}33; border: 1px solid {color}66; color: {color};"
                )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow", cameras: list[CameraDevice], selected_index: int) -> None:
        super().__init__(parent)  # type: ignore
        self._mw = parent
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(560, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setFixedSize(24, 24)
        title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_icon.setPixmap(self._mw.icons["settings"].pixmap(QSize(18, 18)))
        title = QLabel("Settings")
        title.setObjectName("title")
        title_row.addWidget(title_icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        root.addLayout(title_row)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        camera_tab = QWidget()
        camera_layout = QVBoxLayout(camera_tab)
        camera_layout.setContentsMargins(10, 10, 10, 10)
        camera_layout.setSpacing(10)

        cam_label = QLabel("Camera")
        cam_label.setObjectName("section")
        self.camera_combo = QComboBox()
        self.camera_combo.setObjectName("cameraSelector")
        for dev in cameras:
            self.camera_combo.addItem(dev.name, dev.index)
        if self.camera_combo.count() > 0:
            match = self.camera_combo.findData(selected_index)
            self.camera_combo.setCurrentIndex(max(0, match))
        self.auto_start_chk = QCheckBox("Auto-start camera on launch")
        self.auto_start_chk.setChecked(bool(settings.get("auto_start_camera", False)))
        self.mirror_chk = QCheckBox("Mirror camera feed")
        self.mirror_chk.setChecked(bool(settings.get("mirror_camera", True)))
        self.region_chk = QCheckBox("Show control region box")
        self.region_chk.setChecked(bool(settings.get("show_control_region", True)))

        camera_layout.addWidget(cam_label)
        camera_layout.addWidget(self.camera_combo)
        camera_layout.addWidget(self.auto_start_chk)
        camera_layout.addWidget(self.mirror_chk)
        camera_layout.addWidget(self.region_chk)
        camera_layout.addStretch(1)

        cursor_tab = QWidget()
        cursor_layout = QVBoxLayout(cursor_tab)
        cursor_layout.setContentsMargins(10, 10, 10, 10)
        cursor_layout.setSpacing(10)

        cursor_title = QLabel("Cursor")
        cursor_title.setObjectName("section")
        self.smooth_lbl = QLabel("Smoothening")
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(10, 100)
        self.smooth_slider.setValue(int(_as_float(settings.get("smoothening", self._mw.mapper.smoothening), self._mw.mapper.smoothening) * 10))
        self.smooth_lbl.setText(f"Smoothening: {self._mw.mapper.smoothening:.1f}")
        self.margin_lbl = QLabel(f"Control margin: {_as_int(settings.get('frame_r', self._mw.mapper.frame_r), self._mw.mapper.frame_r)}")
        self.margin_slider = QSlider(Qt.Orientation.Horizontal)
        margin_max = max(40, self._mw.mapper.max_effective_margin_px())
        self.margin_slider.setRange(40, margin_max)
        self.margin_slider.setValue(min(_as_int(settings.get("frame_r", self._mw.mapper.frame_r), self._mw.mapper.frame_r), margin_max))

        cursor_layout.addWidget(cursor_title)
        cursor_layout.addWidget(self.smooth_lbl)
        cursor_layout.addWidget(self.smooth_slider)
        cursor_layout.addWidget(self.margin_lbl)
        cursor_layout.addWidget(self.margin_slider)
        cursor_layout.addStretch(1)

        gesture_tab = QWidget()
        gesture_layout = QVBoxLayout(gesture_tab)
        gesture_layout.setContentsMargins(10, 10, 10, 10)
        gesture_layout.setSpacing(10)

        gesture_title = QLabel("Gestures")
        gesture_title.setObjectName("section")
        self.scroll_lbl = QLabel("Scroll speed")
        self.scroll_slider = QSlider(Qt.Orientation.Horizontal)
        self.scroll_slider.setRange(5, 30)
        self.scroll_slider.setValue(int(_as_float(settings.get("scroll_multiplier", self._mw._scroll_multiplier), self._mw._scroll_multiplier) * 10))
        self.scroll_lbl.setText(f"Scroll Speed: {self._mw._scroll_multiplier:.1f}x")
        self.pinch_lbl = QLabel("Pinch sensitivity")
        self.pinch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pinch_slider.setRange(10, 35)
        self.pinch_slider.setValue(int(_as_float(settings.get("pinch_sensitivity", self._mw.gestures._pinch_enter), self._mw.gestures._pinch_enter) * 100))
        self.pinch_lbl.setText(f"Pinch Sensitivity: {self._mw.gestures._pinch_enter:.2f}")
        self.hold_lbl = QLabel("Confirm hold (ms)")
        self.hold_slider = QSlider(Qt.Orientation.Horizontal)
        self.hold_slider.setRange(50, 500)
        self.hold_slider.setValue(int(_as_float(settings.get("confirm_hold_s", 0.06), self._mw.gestures._confirm_hold_s) * 1000))
        self.hold_lbl.setText(f"Hold Time: {self._mw.gestures._confirm_hold_s:.2f}s")
        self.z_tap_chk = QCheckBox("Enable Z-tap (forward air click)")
        self.z_tap_chk.setChecked(bool(settings.get("z_tap_enabled", False)))

        gesture_layout.addWidget(gesture_title)
        gesture_layout.addWidget(self.scroll_lbl)
        gesture_layout.addWidget(self.scroll_slider)
        gesture_layout.addWidget(self.pinch_lbl)
        gesture_layout.addWidget(self.pinch_slider)
        gesture_layout.addWidget(self.hold_lbl)
        gesture_layout.addWidget(self.hold_slider)
        gesture_layout.addWidget(self.z_tap_chk)
        gesture_layout.addStretch(1)

        perf_tab = QWidget()
        perf_layout = QVBoxLayout(perf_tab)
        perf_layout.setContentsMargins(10, 10, 10, 10)
        perf_layout.setSpacing(10)

        perf_title = QLabel("Performance / Debug")
        perf_title.setObjectName("section")
        self.performance_chk = QCheckBox("Performance mode (320x240 processing)")
        self.performance_chk.setChecked(bool(settings.get("performance_mode", False)))
        self.debug_chk = QCheckBox("Show debug skeleton")
        self.debug_chk.setChecked(bool(settings.get("debug_overlay", False)))

        perf_layout.addWidget(perf_title)
        perf_layout.addWidget(self.performance_chk)
        perf_layout.addWidget(self.debug_chk)
        perf_layout.addStretch(1)

        tabs.addTab(camera_tab, "Camera")
        tabs.addTab(cursor_tab, "Cursor")
        tabs.addTab(gesture_tab, "Gestures")
        tabs.addTab(perf_tab, "Performance")

        footer = QHBoxLayout()
        about_btn = QPushButton("About")
        apply_btn = QPushButton("Apply")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("ghostButton")
        footer.addWidget(about_btn)
        footer.addStretch(1)
        footer.addWidget(apply_btn)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self.camera_combo.activated.connect(self._on_camera_changed)
        self.auto_start_chk.stateChanged.connect(self._on_auto_start_changed)
        self.mirror_chk.stateChanged.connect(self._on_mirror_changed)
        self.region_chk.stateChanged.connect(self._on_region_changed)
        self.smooth_slider.valueChanged.connect(self._on_smooth_changed)
        self.margin_slider.valueChanged.connect(self._on_margin_changed)
        self.scroll_slider.valueChanged.connect(self._on_scroll_changed)
        self.pinch_slider.valueChanged.connect(self._on_pinch_changed)
        self.hold_slider.valueChanged.connect(self._on_hold_changed)
        self.z_tap_chk.stateChanged.connect(self._on_z_tap_changed)
        self.performance_chk.stateChanged.connect(self._on_performance_toggled)
        self.debug_chk.stateChanged.connect(self._on_debug_changed)
        about_btn.clicked.connect(self._show_about)
        apply_btn.clicked.connect(self._apply_performance)
        close_btn.clicked.connect(self.accept)

        self.setStyleSheet(
            """
            * {
                font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
            }
            QDialog { background: #18181B; color: #F1F5F9; border: 1px solid #27272A; border-radius: 16px; }
            QLabel { color: #F1F5F9; font-size: 13px; font-weight: 500; }
            #title { font-size: 20px; font-weight: 800; color: #F1F5F9; letter-spacing: 1px;}
            #section { font-size: 13px; color: #8B97B0; font-weight: 800; text-transform: uppercase; margin-bottom: 4px; letter-spacing: 1px;}
            
            QTabWidget::pane { border: none; border-top: 1px solid #27272A; margin-top: -1px; }
            QTabBar::tab {
                background: transparent; color: #8B97B0; padding: 12px 20px;
                border: none; font-weight: 700; font-size: 14px;
            }
            QTabBar::tab:selected { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
            QTabBar::tab:hover { color: #F1F5F9; }
            
            QComboBox {
                background: #18181B; border: 1px solid #27272A; border-radius: 8px; padding: 10px; color: #F1F5F9; font-weight: 600;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #18181B; border: 1px solid #27272A; border-radius: 8px;
                selection-background-color: #00F0FF; selection-color: #021820;
            }
            
            QCheckBox { font-weight: 600; spacing: 12px; color: #8B97B0; }
            QCheckBox::indicator {
                width: 36px; height: 18px; border-radius: 9px;
                background: #18181B; border: 2px solid #27272A;
            }
            QCheckBox::indicator:checked {
                background: #00F0FF; border: 2px solid #00F0FF;
            }
            
            QPushButton {
                border: none; border-radius: 12px; padding: 10px 20px;
                color: #021820; font-weight: 700; font-size: 13px; 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891B2, stop:1 #22D3EE);
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22D3EE, stop:1 #67E8F9);
            }
            #ghostButton { background: transparent; color: #8B97B0; }
            #ghostButton:hover { background: rgba(30, 37, 53, 0.5); color: #F1F5F9; }
            
            QSlider::groove:horizontal { height: 4px; background: #1E1E24; border-radius: 2px; }
            QSlider::sub-page:horizontal { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0E7490, stop:1 #22D3EE); 
                border-radius: 2px; 
            }
            QSlider::handle:horizontal {
                background: #F1F5F9; border: 2px solid #22D3EE;
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #FFFFFF; border: 2px solid #67E8F9;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
            }
            """
        )

    def _on_camera_changed(self, idx: int) -> None:
        camera_index = self.camera_combo.itemData(idx)
        if camera_index is None:
            return
        self._mw._on_camera_selected(camera_index)

    def _on_auto_start_changed(self, state: int) -> None:
        settings.set("auto_start_camera", bool(state))

    def _on_mirror_changed(self, state: int) -> None:
        value = bool(state)
        self._mw._mirror_camera = value
        settings.set("mirror_camera", value)

    def _on_region_changed(self, state: int) -> None:
        value = bool(state)
        self._mw._show_control_region = value
        settings.set("show_control_region", value)

    def _on_smooth_changed(self, value: int) -> None:
        smooth = value / 10.0
        self._mw.mapper.set_smoothening(smooth)
        self.smooth_lbl.setText(f"Smoothening: {smooth:.1f}")
        settings.set("smoothening", smooth)

    def _on_margin_changed(self, value: int) -> None:
        self._mw._set_control_margin(int(value))
        self.margin_slider.setValue(self._mw.mapper.frame_r)
        self.margin_lbl.setText(f"Control margin: {self._mw.mapper.frame_r}")

    def _on_scroll_changed(self, value: int) -> None:
        mult = value / 10.0
        self._mw._scroll_multiplier = mult
        self.scroll_lbl.setText(f"Scroll speed: {mult:.1f}x")
        settings.set("scroll_multiplier", mult)

    def _on_pinch_changed(self, value: int) -> None:
        pinch = value / 100.0
        self._mw.gestures._pinch_enter = pinch
        self._mw.gestures._pinch_exit = max(pinch + 0.05, self._mw.gestures._pinch_exit)
        self.pinch_lbl.setText(f"Pinch sensitivity: {pinch:.2f}")
        settings.set("pinch_sensitivity", pinch)
        settings.set("pinch_exit_sensitivity", self._mw.gestures._pinch_exit)

    def _on_hold_changed(self, value: int) -> None:
        hold_s = value / 1000.0
        self._mw.gestures._confirm_hold_s = hold_s
        self.hold_lbl.setText(f"Hold Time: {hold_s:.2f}s")
        settings.set("confirm_hold_s", hold_s)

    def _on_z_tap_changed(self, state: int) -> None:
        enabled = bool(state)
        if enabled:
            reply = QMessageBox.warning(
                self,
                "Enable Z-tap Click",
                "Depth tap can increase accidental clicks while moving your hand. Enable anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.z_tap_chk.blockSignals(True)
                self.z_tap_chk.setChecked(False)
                self.z_tap_chk.blockSignals(False)
                enabled = False
        self._mw.gestures._z_tap_enabled = enabled
        settings.set("z_tap_enabled", enabled)

    def _on_performance_toggled(self, state: int) -> None:
        value = bool(state)
        settings.set("performance_mode", value)
        if self._mw.running:
            QMessageBox.information(self, "Restart Required", "Camera will be recreated on Apply.")

    def _on_debug_changed(self, state: int) -> None:
        value = bool(state)
        self._mw.debug = value
        settings.set("debug_overlay", value)

    def _apply_performance(self) -> None:
        self._mw._apply_performance_mode(bool(self.performance_chk.isChecked()))

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About Holographic Touch",
            "Holographic Touch v1.0 — AI Hand Gesture Mouse Controller\n"
            "Gestures: Move, Click, Double-Click, Right Click, Drag, Scroll, Task View, Keyboard, Media\n"
            "Camera: OpenCV with DShow/MSMF fallback\n"
            "Detection: MediaPipe Hands (model_complexity=0)",
        )


class MainWindow(QMainWindow):
    _camera_start_result = Signal(bool)

    def __init__(self) -> None:
        super().__init__()

        # ── BUG C FIX: Windows DPI awareness (must be before any GUI/pyautogui calls) ──
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # type: ignore[attr-defined]
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()  # type: ignore[attr-defined]
            except Exception:
                pass

        _configure_input_latency()
        if platform.system() != "Windows":
            print("Holographic Touch is optimized for Windows.")

        self.setWindowTitle("Holographic Touch")
        self.setMinimumSize(960, 640)

        self.camera = CameraThread(640, 480)
        self.camera.camera_index = _as_int(settings.get("camera_index", 0), 0)

        self._mediapipe_error: str | None = None
        try:
            self.tracker: HandTracker | None = HandTracker()
        except Exception as exc:
            self.tracker = None
            self._mediapipe_error = str(exc)

        self.gestures = GestureDetector()
        self.mapper = CursorMapper(640, 480)
        self.mouse = MouseController()
        self.icons = {
            "start": qta.icon("fa6s.video", color="#031A10"),
            "stop": qta.icon("fa6s.stop", color="#1A0505"),
            "enable_mouse": qta.icon("fa6s.computer-mouse", color="#021820"),
            "settings": qta.icon("fa6s.gear", color="#8B97B0"),
            "move": qta.icon("fa6s.crosshairs", color="#8B97B0"),
            "left_click": qta.icon("fa6s.arrow-pointer", color="#8B97B0"),
            "double_click": qta.icon("fa6s.hand-pointer", color="#8B97B0"),
            "drag": qta.icon("fa6s.hand", color="#8B97B0"),
            "right_click": qta.icon("fa6s.arrow-pointer", color="#8B97B0"),
            "scroll": qta.icon("fa6s.arrows-up-down", color="#8B97B0"),
            "task_view": qta.icon("fa6s.table-cells-large", color="#8B97B0"),
            "keyboard": qta.icon("fa6s.keyboard", color="#8B97B0"),
            "pause": qta.icon("fa6s.pause", color="#8B97B0"),
            "media_vol_up": qta.icon("fa6s.volume-high", color="#8B97B0"),
            "media_vol_down": qta.icon("fa6s.volume-low", color="#8B97B0"),
            "media_next": qta.icon("fa6s.forward", color="#8B97B0"),
            "media_prev": qta.icon("fa6s.backward", color="#8B97B0"),
        }

        self.mapper.set_camera_size(640, 480)
        self.mapper.set_frame_margin(_as_int(settings.get("frame_r", 90), 90))
        self.mapper.set_smoothening(_as_float(settings.get("smoothening", 4.8), 4.8))
        self.gestures._confirm_hold_s = _as_float(settings.get("confirm_hold_s", 0.06), 0.06)
        self.gestures._pinch_enter = _as_float(settings.get("pinch_sensitivity", 0.30), 0.30)
        self.gestures._pinch_exit = max(self.gestures._pinch_enter + 0.08, _as_float(settings.get("pinch_exit_sensitivity", 0.45), 0.45))
        self.gestures._z_tap_enabled = _as_bool(settings.get("z_tap_enabled", False), False)
        self._scroll_multiplier: float = _as_float(settings.get("scroll_multiplier", 1.0), 1.0)
        self.debug = _as_bool(settings.get("debug_overlay", False), False)
        self._mirror_camera: bool = _as_bool(settings.get("mirror_camera", True), True)
        self._show_control_region: bool = _as_bool(settings.get("show_control_region", True), True)

        self.fps = 0.0
        self._fps_prev = time.monotonic()
        self.running = False
        self.proc_thread: threading.Thread | None = None
        self.mouse_enabled = False
        self._overlay: StatusOverlay | None = None
        self._dimmer: QWidget | None = None
        self._tray: QSystemTrayIcon | None = None
        self._tray_action_toggle: QAction | None = None
        self._quitting = False

        self._lock = threading.Lock()
        self._frame = None
        self._hand_proto = None
        self._hand_data = None
        self._gesture = GestureType.PAUSE
        self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
        self._fingers = 0
        self._kbd_lock_until = 0.0
        self._camera_cache: list[CameraDevice] = []
        self._camera_cache_ts = 0.0
        self._camera_error_text = ""
        self._last_badge_gesture: GestureType = GestureType.NONE
        self._gesture_history: collections.deque = collections.deque(maxlen=6)
        self._last_debug_print_ts = 0.0
        self._last_debug_label: str = ""
        self._drag_active = False
        self._start_worker: threading.Thread | None = None

        self._build_ui()
        self._camera_start_result.connect(self._on_camera_start_done)
        self._setup_tray()
        self._start_hotkey_listener()

        wx = _as_int(settings.get("window_x", -1), -1)
        wy = _as_int(settings.get("window_y", -1), -1)
        ww = _as_int(settings.get("window_w", 1280), 1280)
        wh = _as_int(settings.get("window_h", 820), 820)
        if wx >= 0 and wy >= 0:
            self.move(wx, wy)
        self.resize(ww, wh)

        self.cam_status.setText("Detecting cameras...")
        QTimer.singleShot(150, lambda: self._refresh_camera_cache(force=True))

        if self._mediapipe_error:
            self.cam_status.setText("MediaPipe Error")
            self.preview.setText(self._mediapipe_error)
            self.start_btn.setEnabled(False)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._render)
        self.timer.start(20)

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        top = QVBoxLayout(root)
        top.setContentsMargins(20, 20, 20, 20)
        top.setSpacing(20)

        header = QFrame()
        header.setObjectName("headerCard")
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(16, 12, 16, 12)
        header_l.setSpacing(16)

        icon_label = QLabel()
        icon_label.setFixedSize(24, 24)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setPixmap(self.icons["start"].pixmap(QSize(18, 18)))

        self.title_lbl = QLabel("HOLOGRAPHIC OS")
        self.title_lbl.setObjectName("title")

        self._status_dot = QLabel("●")
        self._status_dot.setObjectName("statusOffline")
        self.cam_status = QLabel("Camera Offline")
        self.cam_status.setObjectName("muted")

        self.fps_lbl = QLabel("FPS 0")
        self.fps_lbl.setObjectName("secondary")
        self.title_lbl.setWordWrap(True)
        self.cam_status.setWordWrap(True)
        self.fps_lbl.setWordWrap(True)

        header_l.addWidget(icon_label)
        header_l.addWidget(self.title_lbl)
        header_l.addStretch(1)
        header_l.addWidget(self._status_dot)
        header_l.addWidget(self.cam_status)
        header_l.addSpacing(16)
        header_l.addWidget(self.fps_lbl)

        body_l = QHBoxLayout()
        body_l.setSpacing(24)

        cam_card = QFrame()
        cam_card.setObjectName("cameraCard")
        cam_l = QVBoxLayout(cam_card)
        cam_l.setContentsMargins(0, 0, 0, 0)

        self.preview = QLabel("NO SIGNAL")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setObjectName("preview")
        self.preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview.setMinimumSize(320, 240)
        self.preview.setProperty("active", "false")
        cam_l.addWidget(self.preview, 1)

        side = QVBoxLayout()
        side.setSpacing(16)

        status = QFrame()
        status.setObjectName("sideCard")
        sl = QVBoxLayout(status)
        sl.setContentsMargins(0, 8, 0, 8)
        sl.setSpacing(10)
        status_title = QLabel("System Status")
        status_title.setObjectName("cardTitle")
        status_title.setWordWrap(True)
        
        self.gesture_lbl = QLabel("STANDBY")
        self.gesture_lbl.setObjectName("badge")
        self.gesture_lbl.setWordWrap(False)
        self.gesture_lbl.setMinimumWidth(140)
        
        self.hand_lbl = QLabel("Hand: Not Detected")
        self.hand_lbl.setObjectName("secondary")
        self.mouse_lbl = QLabel("Mouse: OFF")
        self.mouse_lbl.setObjectName("secondary")
        self.fingers_lbl = QLabel("Fingers: 0")
        self.fingers_lbl.setObjectName("secondary")
        self.confidence_lbl = QLabel("Confidence: —")
        self.confidence_lbl.setObjectName("secondary")
        self.hand_lbl.setWordWrap(True)
        self.mouse_lbl.setWordWrap(True)
        self.fingers_lbl.setWordWrap(True)
        self.confidence_lbl.setWordWrap(True)
        
        sl.addWidget(status_title)
        sl.addWidget(self.gesture_lbl)
        sl.addSpacing(8)
        sl.addWidget(self.hand_lbl)
        sl.addWidget(self.mouse_lbl)
        sl.addWidget(self.fingers_lbl)
        sl.addWidget(self.confidence_lbl)

        guide = QFrame()
        guide.setObjectName("sideCard")
        guide.setMinimumWidth(260)
        guide.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        gl = QGridLayout(guide)
        gl.setContentsMargins(0, 8, 0, 8)
        gl.setHorizontalSpacing(16)
        gl.setVerticalSpacing(12)

        guide_title = QLabel("Protocol Guide")
        guide_title.setObjectName("cardTitle")
        guide_title.setWordWrap(True)
        gl.addWidget(guide_title, 0, 0, 1, 3)

        guide_rows = [
            ("move", "Move cursor", "Index finger"),
            ("left_click", "Left click", "Thumb + Index pinch"),
            ("double_click", "Double click", "Quick double pinch"),
            ("drag", "Drag", "Hold Thumb + Index pinch"),
            ("right_click", "Right click", "Middle down + Thumb pinch"),
            ("scroll", "Scroll", "Peace sign + up/down"),
            ("task_view", "Task View", "Open palm"),
            ("keyboard", "OS Keyboard", "Thumb + Index + Pinky"),
            ("pause", "Pause", "No gesture / hand down"),
        ]

        for i, (icon_key, action_desc, gesture_desc) in enumerate(guide_rows, start=1):
            il = QLabel()
            il.setFixedSize(24, 24)
            il.setAlignment(Qt.AlignmentFlag.AlignCenter)
            il.setPixmap(self.icons[icon_key].pixmap(QSize(18, 18)))
            
            tl = QLabel(gesture_desc)
            tl.setObjectName("gestureBold")
            tl.setWordWrap(True)
            
            dl = QLabel(action_desc)
            dl.setObjectName("mutedAction")
            dl.setWordWrap(True)
            
            gl.addWidget(il, i, 0)
            gl.addWidget(tl, i, 1)
            gl.addWidget(dl, i, 2)
            
        gl.setColumnStretch(2, 1)
        gl.setColumnStretch(1, 2)
        gl.setColumnStretch(0, 0)

        history_card = QFrame()
        history_card.setObjectName("sideCard")
        history_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        hl = QVBoxLayout(history_card)
        hl.setContentsMargins(0, 8, 0, 8)
        hl.setSpacing(6)
        history_title = QLabel("Audit Log")
        history_title.setObjectName("cardTitle")
        history_title.setWordWrap(True)
        hl.addWidget(history_title)
        self._history_labels: list[QLabel] = []
        for _ in range(6):
            lbl = QLabel("")
            lbl.setObjectName("historyItem")
            lbl.setWordWrap(False)
            lbl.setMinimumHeight(24)
            lbl.setVisible(False)
            hl.addWidget(lbl)
            self._history_labels.append(lbl)

        self.gesture_guide = guide
        self.audit_log = history_card
        self.gesture_guide.setMinimumWidth(240)
        self.audit_log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Wrap audit log in a scroll area for readability at all window sizes.
        audit_scroll = QScrollArea()
        audit_scroll.setWidgetResizable(True)
        audit_scroll.setWidget(self.audit_log)
        audit_scroll.setFrameShape(QFrame.Shape.NoFrame)
        audit_scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent; width: 6px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #27272A; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #3F3F46; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
        """)

        side_content = QVBoxLayout()
        side_content.setSpacing(12)
        side_content.addWidget(self.gesture_guide)
        side_content.addWidget(audit_scroll, 1)
        side_content.setStretch(0, 2)
        side_content.setStretch(1, 1)

        side.addWidget(status)
        side.addLayout(side_content, 1)

        side_wrap = QWidget()
        side_wrap.setLayout(side)
        side_wrap.setMinimumWidth(300)
        side_wrap.setMaximumWidth(420)
        side_wrap.setObjectName("sideCardWrap")

        body_l.addWidget(cam_card, 3)
        body_l.addWidget(side_wrap, 1)

        dock_wrap = QWidget()
        dock_wrap_layout = QHBoxLayout(dock_wrap)
        dock_wrap_layout.setContentsMargins(0, 0, 0, 0)
        dock_wrap_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        controls = QFrame()
        controls.setObjectName("floatingDock")
        cl = QHBoxLayout(controls)
        cl.setContentsMargins(24, 14, 24, 14)
        cl.setSpacing(16)

        self.start_btn = QPushButton(" Initialize")
        self.start_btn.setIcon(self.icons["start"])
        self.start_btn.setIconSize(QSize(18, 18))
        self.start_btn.setObjectName("startBtn")

        self.stop_btn = QPushButton(" Terminate")
        self.stop_btn.setIcon(self.icons["stop"])
        self.stop_btn.setIconSize(QSize(18, 18))
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setEnabled(False)

        self.mouse_btn = QPushButton(" Engage Interface")
        self.mouse_btn.setIcon(self.icons["enable_mouse"])
        self.mouse_btn.setIconSize(QSize(18, 18))
        self.mouse_btn.setObjectName("mouseBtn")

        self._region_label = QLabel(f"Field Margin: {self.mapper.frame_r}")
        self._region_label.setObjectName("primaryText")
        self._region_slider = QSlider(Qt.Orientation.Horizontal)
        self._region_slider.setRange(40, max(40, self.mapper.max_effective_margin_px()))
        self._region_slider.setValue(min(int(self.mapper.frame_r), self._region_slider.maximum()))
        self._region_slider.setFixedWidth(160)

        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(self.icons["settings"])
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.setFixedSize(44, 44)
        self.settings_btn.setToolTip("System Configuration")
        self.settings_btn.setObjectName("settingsBtn")

        self.start_btn.clicked.connect(self.start_camera)
        self.stop_btn.clicked.connect(self.stop_camera)
        self.mouse_btn.clicked.connect(self.toggle_mouse)
        self._region_slider.valueChanged.connect(self._set_control_margin)
        self.settings_btn.clicked.connect(self._open_settings_dialog)

        cl.addWidget(self.start_btn)
        cl.addWidget(self.stop_btn)
        cl.addWidget(self.mouse_btn)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet("border-left: 1px solid #27272A; margin: 0 8px;")
        cl.addWidget(divider)

        cl.addWidget(self._region_label)
        cl.addWidget(self._region_slider)
        cl.addSpacing(8)
        cl.addWidget(self.settings_btn)

        dock_wrap_layout.addWidget(controls)

        top.addWidget(header)
        body_wrap = QWidget()
        body_wrap.setLayout(body_l)
        top.addWidget(body_wrap, 1)
        top.addWidget(dock_wrap)

        self.setStyleSheet(
            """
            * {
                font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
            }
            QMainWindow { background: #09090B; color: #F1F5F9; }
            
            #headerCard {
                background: rgba(15, 18, 25, 0.6);
                border: 1px solid rgba(39, 39, 42, 0.5);
                border-radius: 14px;
            }
            #floatingDock {
                background: rgba(15, 18, 25, 0.9);
                border: 1px solid rgba(34, 211, 238, 0.12);
                border-radius: 26px;
            }
            #sideCard {
                background: rgba(15, 18, 25, 0.4);
                border: 1px solid rgba(39, 39, 42, 0.3);
                border-radius: 12px;
                padding: 12px;
            }
            #sideCardWrap {
                background: transparent;
                border: none;
            }
            #cameraCard {
                background: transparent;
                border: none;
            }
            
            #title { 
                font-size: 18px; font-weight: 800; color: #F1F5F9; 
                letter-spacing: 1.5px; 
            }
            #cardTitle { 
                font-size: 12px; font-weight: 700; color: #64748B; 
                text-transform: uppercase; letter-spacing: 2px; 
                padding-bottom: 4px; 
            }
            
            #statusOffline { color: #F87171; font-size: 16px; }
            #statusOnline { color: #22D3EE; font-size: 16px; }
            
            #preview {
                background: #0F1117; 
                border-radius: 14px; 
                border: 1px solid #1E1E24;
                color: #27272A; 
                font-size: 16px;
                font-weight: 700;
                letter-spacing: 3px;
            }
            #preview[active="true"] {
                border: 1px solid rgba(34, 211, 238, 0.25);
            }
            
            #gestureBold { 
                font-weight: 600; color: #E2E8F0; font-size: 13px;
            }
            #mutedAction { 
                color: #64748B; font-size: 12px; text-align: left; 
            }
            
            #primaryText { color: #E2E8F0; font-size: 13px; font-weight: 600;}
            #secondary { color: #94A3B8; font-size: 13px; font-weight: 500;}
            #muted { color: #475569; font-size: 13px; font-weight: 500;}
            
            #badge {
                border-radius: 10px; padding: 6px 16px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0; 
                max-width: 200px; font-size: 13px; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
            }
            #historyItem { 
                font-weight: 500; 
                font-family: "Cascadia Code", "Consolas", "SF Mono", monospace;
                font-size: 12px;
                color: #64748B;
            }
            
            QPushButton {
                border: none; 
                border-radius: 14px; 
                padding: 10px 22px;
                font-size: 13px;
                font-weight: 700; 
                background: #18181B;
                color: #E2E8F0;
                letter-spacing: 0.5px;
            }
            QPushButton:hover { 
                background: #27272A; 
            }
            QPushButton:disabled { background: #0F0F12; color: #27272A; }
            
            #startBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #059669, stop:1 #34D399); 
                color: #022C22; 
            }
            #startBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #34D399, stop:1 #6EE7B7);
            }
            
            #stopBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #DC2626, stop:1 #F87171); 
                color: #1A0505; 
            }
            #stopBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #F87171, stop:1 #FCA5A5);
            }
            
            #mouseBtn { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0891B2, stop:1 #22D3EE); 
                color: #021820; 
            }
            #mouseBtn:hover { 
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #22D3EE, stop:1 #67E8F9);
            }
            
            #settingsBtn { 
                background: transparent; padding: 0;
                border-radius: 22px;
            }
            #settingsBtn:hover { 
                background: rgba(34, 211, 238, 0.08); 
                border: 1px solid rgba(34, 211, 238, 0.2); 
            }
            
            QSlider::groove:horizontal {
                height: 4px; background: #1E1E24; border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #0E7490, stop:1 #22D3EE);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #F1F5F9; border: 2px solid #22D3EE;
                width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #FFFFFF;
                border: 2px solid #67E8F9;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
            }
            """
        )

    def _setup_tray(self) -> None:
        tray = QSystemTrayIcon(self)
        tray.setIcon(self.icons["enable_mouse"])
        tray.setToolTip("Holographic Touch")

        tray_menu = QMenu()
        action_show = QAction("Show Window", self)
        action_toggle = QAction("Enable Mouse", self)
        action_end_drag = QAction("End Drag", self)
        action_cancel = QAction("Cancel Gesture Actions", self)
        action_quit = QAction("Quit", self)
        action_show.triggered.connect(self._show_main_window)
        action_toggle.triggered.connect(self.toggle_mouse)
        action_end_drag.triggered.connect(self._end_drag_now)
        action_cancel.triggered.connect(self._cancel_actions)
        action_quit.triggered.connect(self._quit_app)
        tray_menu.addAction(action_show)
        tray_menu.addAction(action_toggle)
        tray_menu.addAction(action_end_drag)
        tray_menu.addAction(action_cancel)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)

        tray.setContextMenu(tray_menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self._tray = tray
        self._tray_action_toggle = action_toggle

    def _show_dimmer(self) -> None:
        if self._dimmer is not None:
            self._dimmer.deleteLater()
        dimmer = QWidget(self)
        dimmer.setObjectName("windowDimmer")
        dimmer.setGeometry(self.rect())
        dimmer.setStyleSheet("#windowDimmer { background: rgba(5, 8, 14, 170); }")
        dimmer.show()
        dimmer.raise_()
        self._dimmer = dimmer

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._dimmer is not None:
            self._dimmer.setGeometry(self.rect())

    def _refresh_camera_cache(self, force: bool = False) -> list[CameraDevice]:
        now = time.monotonic()
        if not force and self._camera_cache and now - self._camera_cache_ts < 8.0:
            return self._camera_cache
        self._camera_cache = self.camera.enumerate_cameras()
        self._camera_cache_ts = now

        if self._camera_cache:
            n = len(self._camera_cache)
            self.cam_status.setText(f"{n} camera{'s' if n != 1 else ''} found")
        else:
            self.cam_status.setText("No cameras found")

        if settings.get("auto_start_camera", False) and not self.running and self._camera_cache:
            saved_index = _as_int(settings.get("camera_index", 0), 0)
            available = {dev.index for dev in self._camera_cache}
            self.camera.camera_index = saved_index if saved_index in available else self._camera_cache[0].index
            QTimer.singleShot(200, self.start_camera)

        return self._camera_cache

    def _populate_cameras(self) -> list[CameraDevice]:
        return self._refresh_camera_cache(force=False)

    def _open_settings_dialog(self) -> None:
        cameras = self._populate_cameras()
        self._show_dimmer()
        dlg = SettingsDialog(self, cameras, self.camera.camera_index)
        dlg.exec()

        if self._dimmer is not None:
            self._dimmer.hide()
            self._dimmer.deleteLater()
            self._dimmer = None

    def _on_camera_selected(self, camera_index) -> None:
        if camera_index is None:
            return
        index = int(camera_index)
        settings.set("camera_index", index)

        if not self.running:
            self.camera.camera_index = index
            return

        ok = self.camera.switch_camera(index)
        if not ok:
            detail = self.camera.last_error or f"Cannot open selected camera index {index}"
            self.cam_status.setText("Camera switch failed")
            self.preview.setText(detail)

    def _launch_keyboard(self) -> None:
        now = time.monotonic()
        if now < self._kbd_lock_until:
            return

        self._kbd_lock_until = now + 0.8
        self.mouse.show_osk()

    def _set_control_margin(self, value: int) -> None:
        v = int(value)
        max_margin = max(40, self.mapper.max_effective_margin_px())
        self.mapper.set_frame_margin(max(10, min(max_margin, v)))
        clamped = self.mapper.frame_r
        self._region_label.setText(f"Field Margin: {self.mapper.frame_r}")
        if self._region_slider.maximum() != max_margin:
            self._region_slider.setMaximum(max_margin)
        if self._region_slider.value() != clamped:
            self._region_slider.setValue(clamped)
        settings.set("frame_r", self.mapper.frame_r)

    def _sync_margin_controls(self) -> None:
        max_margin = max(40, self.mapper.max_effective_margin_px())
        if self._region_slider.maximum() != max_margin:
            self._region_slider.setMaximum(max_margin)
        if self.mapper.frame_r > max_margin:
            self.mapper.set_frame_margin(max_margin)
            settings.set("frame_r", self.mapper.frame_r)
        if self._region_slider.value() != self.mapper.frame_r:
            self._region_slider.setValue(self.mapper.frame_r)
        self._region_label.setText(f"Field Margin: {self.mapper.frame_r}")

    def _apply_performance_mode(self, enabled: bool) -> None:
        settings.set("performance_mode", bool(enabled))
        try:
            old = self.tracker
            self.tracker = HandTracker()
            if enabled:
                self.tracker.set_processing_size((320, 240))
            else:
                self.tracker.set_processing_size(None)
            if old is not None:
                old.close()
        except Exception as exc:
            self._mediapipe_error = str(exc)
            self.cam_status.setText("MediaPipe Error")
            self.preview.setText(self._mediapipe_error)

    def start_camera(self) -> None:
        if self.running:
            return
        if self._start_worker is not None and self._start_worker.is_alive():  # type: ignore
            return
        if self._mediapipe_error:
            self.preview.setText(self._mediapipe_error)
            return

        if self.tracker is not None:
            self.tracker.close()
        try:
            self.tracker = HandTracker()
        except Exception as exc:
            self.tracker = None
            self._mediapipe_error = str(exc)
            self.cam_status.setText("MediaPipe Error")
            self.preview.setText(self._mediapipe_error)
            self.start_btn.setEnabled(False)
            return

        self.gestures = GestureDetector()
        self.gestures._confirm_hold_s = _as_float(settings.get("confirm_hold_s", 0.06), 0.06)
        self.gestures._pinch_enter = _as_float(settings.get("pinch_sensitivity", 0.30), 0.30)
        self.gestures._pinch_exit = max(self.gestures._pinch_enter + 0.08, _as_float(settings.get("pinch_exit_sensitivity", 0.45), 0.45))
        self.gestures._z_tap_enabled = _as_bool(settings.get("z_tap_enabled", False), False)
        self.gestures.reset_cooldowns()
        self._drag_active = False

        if _as_bool(settings.get("performance_mode", False), False):
            if self.tracker is not None:
                self.tracker.set_processing_size((320, 240))
        else:
            if self.tracker is not None:
                self.tracker.set_processing_size(None)

        cameras = self._refresh_camera_cache(force=True)
        if not cameras:
            msg = "No camera detected. Start DroidCam video feed, then try again."
            self.preview.setText(msg)
            self.cam_status.setText(msg)
            self.start_btn.setEnabled(True)
            self.start_btn.setText(" Initialize")
            return

        self.camera.camera_index = _as_int(settings.get("camera_index", self.camera.camera_index), self.camera.camera_index)
        available = {dev.index for dev in cameras}
        if self.camera.camera_index not in available:
            self.camera.camera_index = cameras[0].index
            settings.set("camera_index", self.camera.camera_index)

        self.start_btn.setEnabled(False)
        self.start_btn.setText("Opening camera...")
        self.cam_status.setText("Opening camera...")

        def _worker() -> None:
            ok = self.camera.start()
            self._camera_start_result.emit(ok)

        self._start_worker = threading.Thread(target=_worker, daemon=True)
        self._start_worker.start()  # type: ignore

    @Slot(bool)
    def _on_camera_start_done(self, ok: bool) -> None:
        self.start_btn.setText(" Initialize")
        self._start_worker = None

        if not ok:
            detail = self.camera.last_error or "Cannot open camera"
            self.preview.setText(detail)
            self.cam_status.setText(detail)
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return

        self.running = True
        self.proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.proc_thread.start()  # type: ignore

        self.cam_status.setText("Camera Active")
        self._status_dot.setObjectName("statusOnline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self.preview.setProperty("active", "true")
        self.preview.style().unpolish(self.preview)
        self.preview.style().polish(self.preview)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

    def stop_camera(self) -> None:
        self.running = False
        if self.proc_thread and self.proc_thread.is_alive():  # type: ignore
            self.proc_thread.join(timeout=1.5)  # type: ignore
        self.proc_thread = None

        self.camera.stop()
        if self.mouse.is_dragging:
            self.mouse.end_drag()
        self._drag_active = False

        self.mapper.reset()
        with self._lock:
            self._frame = None
            self._gesture = GestureType.PAUSE
            self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
            self._fingers = 0
            self._hand_proto = None
            self._hand_data = None

        self.preview.setPixmap(QPixmap())
        self.preview.setText("NO SIGNAL")
        self.preview.setProperty("active", "false")
        self.preview.style().unpolish(self.preview)
        self.preview.style().polish(self.preview)
        self.cam_status.setText("Camera Offline")
        self._status_dot.setObjectName("statusOffline")
        self._status_dot.style().unpolish(self._status_dot)
        self._status_dot.style().polish(self._status_dot)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if self._overlay is not None:
            settings.set("overlay_x", self._overlay.x())  # type: ignore
            settings.set("overlay_y", self._overlay.y())  # type: ignore
            self._overlay.close()  # type: ignore
            self._overlay = None

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.raise_()

    @Slot()
    def toggle_mouse(self) -> None:
        self.mouse_enabled = not self.mouse_enabled

        if self._tray_action_toggle is not None:
            self._tray_action_toggle.setText("Disable Mouse" if self.mouse_enabled else "Enable Mouse")

        if self.mouse_enabled:
            self.mouse_btn.setText("Disable Mouse")
            self.mouse_lbl.setText("Mouse: ON")

            if self._overlay is None:
                self._overlay = StatusOverlay(self.icons)
                self._overlay.open_btn.clicked.connect(self._show_main_window)  # type: ignore
                self._overlay.disable_btn.clicked.connect(self._disable_mouse_from_overlay)  # type: ignore
                try:
                    screen = QApplication.primaryScreen()
                    if screen:
                        sg = screen.availableGeometry()
                        self._overlay.move(  # type: ignore
                            max(10, sg.right() - self._overlay.width() - 20),  # type: ignore
                            sg.top() + 20,
                        )
                    else:
                        self._overlay.move(20, 20)  # type: ignore
                except Exception:
                    self._overlay.move(20, 20)  # type: ignore

                ox = _as_int(settings.get("overlay_x", -1), -1)
                oy = _as_int(settings.get("overlay_y", -1), -1)
                if ox >= 0 and oy >= 0:
                    self._overlay.move(ox, oy)  # type: ignore

                self._overlay.show()  # type: ignore

            self.showMinimized()
        else:
            self.mouse_btn.setText("Enable Mouse")
            self.mouse_lbl.setText("Mouse: OFF")
            if self._overlay is not None:
                settings.set("overlay_x", self._overlay.x())  # type: ignore
                settings.set("overlay_y", self._overlay.y())  # type: ignore
                self._overlay.close()  # type: ignore
                self._overlay = None
            self.showNormal()
            self.raise_()

    def _show_main_window(self) -> None:
        self.showNormal()
        self.raise_()

    def _end_drag_now(self) -> None:
        if self.mouse.is_dragging:
            self.mouse.end_drag()

    def _cancel_actions(self) -> None:
        self._end_drag_now()
        self._drag_active = False
        self.mapper.reset()
        self.gestures._state = GestureType.PAUSE

    def _disable_mouse_from_overlay(self) -> None:
        if self.mouse_enabled:
            self.toggle_mouse()

    def _start_hotkey_listener(self) -> None:
        try:
            from pynput import keyboard as kb  # type: ignore[import-not-found]

            def on_activate():
                QMetaObject.invokeMethod(self, "toggle_mouse", Qt.ConnectionType.QueuedConnection)

            hotkey = kb.GlobalHotKeys({"<ctrl>+<shift>+h": on_activate})
            hotkey.daemon = True
            hotkey.start()
            self._hotkey = hotkey
        except Exception:
            self._hotkey = None
            print("Hotkey unavailable")

    def _process_loop(self) -> None:
        last_overlay = GestureType.NONE
        last_action = GestureType.NONE
        last_task_view_action = 0.0
        last_hand_time = time.monotonic()

        _boost_runtime_priority()
        # cv2.setUseOptimized is configured globally; skip per-thread call.

        while self.running:  # type: ignore
            if time.monotonic() - last_hand_time > 5.0:
                time.sleep(0.005)

            try:
                frame = self.camera.latest()  # type: ignore
                if frame is None:
                    time.sleep(0.001)
                    continue

                if self._mirror_camera:  # type: ignore
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                self.mapper.set_camera_size(w, h)  # type: ignore

                tracker = self.tracker  # type: ignore
                if tracker is None:
                    time.sleep(0.01)
                    continue

                hand_data, hand_proto, is_grace = tracker.detect(frame, is_mirrored=self._mirror_camera)  # type: ignore

                if hand_proto is not None:
                    last_hand_time = time.monotonic()
                    wrist = hand_data["xy"][0]
                    middle_mcp = hand_data["xy"][9]
                    scale = ((wrist[0] - middle_mcp[0]) ** 2 + (wrist[1] - middle_mcp[1]) ** 2) ** 0.5
                    self.mapper.set_hand_scale(scale)  # type: ignore
                    self._camera_error_text = ""  # type: ignore
                else:
                    self._camera_error_text = self.camera.last_error  # type: ignore

                result = self.gestures.detect(hand_data, is_grace_frame=is_grace)  # type: ignore
                if result is None:
                    result = GestureResult(GestureType.PAUSE, 0)
                # Safety: verify confidence before allowing actions
                if hand_data and hand_data.get("confidence", 0) < 0.55:
                    if result.gesture in {GestureType.LEFT_CLICK, GestureType.RIGHT_CLICK,
                                         GestureType.DOUBLE_CLICK}:
                        result = GestureResult(GestureType.MOVE, 0)
                gesture = result.gesture
                gesture_changed = gesture != last_action
                self._last_debug_label = gesture
                # Debug print disabled for production

                if self.mouse_enabled and gesture == GestureType.KEYBOARD and gesture_changed:
                    self._launch_keyboard()

                if self.mouse_enabled and gesture == GestureType.TASK_VIEW and gesture_changed:
                    now = time.monotonic()
                    if now - last_task_view_action >= 1.0:
                        last_task_view_action = now
                        self.mouse.open_task_view()

                if self.mouse_enabled and gesture in {
                    GestureType.MEDIA_VOL_UP,
                    GestureType.MEDIA_VOL_DOWN,
                    GestureType.MEDIA_NEXT,
                    GestureType.MEDIA_PREV,
                }:
                    if gesture_changed or gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN):
                        if gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN) and result.scroll_delta == 0:
                            pass
                        else:
                            self._execute_media(gesture, result.scroll_delta)

                if self.mouse_enabled and hand_data and hand_data.get("label") == "Right" and gesture not in {
                    GestureType.NONE,
                    GestureType.PAUSE,
                    GestureType.TASK_VIEW,
                    GestureType.KEYBOARD,
                    GestureType.MEDIA_VOL_UP,
                    GestureType.MEDIA_VOL_DOWN,
                    GestureType.MEDIA_NEXT,
                    GestureType.MEDIA_PREV,
                }:
                    tip = hand_data["xy"][8]
                    cam_x = int(tip[0])
                    cam_y = int(tip[1])
                    sx, sy = self.mapper.map_point(cam_x, cam_y)

                    if gesture == GestureType.MOVE:
                        self.mouse.move(sx, sy)
                    elif gesture == GestureType.LEFT_CLICK and gesture_changed:
                        self.mouse.move(sx, sy)
                        self.mouse.left_click()
                    elif gesture == GestureType.DOUBLE_CLICK and gesture_changed:
                        self.mouse.move(sx, sy)
                        self.mouse.double_click()
                    elif gesture == GestureType.RIGHT_CLICK and gesture_changed:
                        self.mouse.right_click()
                    elif gesture == GestureType.SCROLL:
                        self.mouse.scroll(int(result.scroll_delta * self._scroll_multiplier))
                    elif gesture == GestureType.DRAG:
                        if not self._drag_active:
                            self.mouse.move(sx, sy)
                            self.mouse.start_drag()
                            self._drag_active = True
                        else:
                            self.mouse.move(sx, sy)

                    if gesture != GestureType.DRAG and self.mouse.is_dragging:
                        self.mouse.end_drag()
                        self._drag_active = False
                elif self.mouse.is_dragging:
                    self.mouse.end_drag()
                    self._drag_active = False

                if not self.mouse_enabled and self.mouse.is_dragging:
                    self.mouse.end_drag()
                    self._drag_active = False

                if gesture != last_overlay:
                    overlay = _OVERLAY_LABELS.get(gesture, "")
                    last_overlay = gesture
                else:
                    overlay = self._overlay_text

                if gesture != last_action:
                    ts = time.strftime("%H:%M:%S")
                    self._gesture_history.appendleft((gesture, ts))

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
                    self._hand_proto = hand_proto
                    self._hand_data = hand_data
            except Exception as exc:
                import logging
                logging.exception(f"Process loop error: {exc}")
                time.sleep(0.005)
                continue

    def _render(self) -> None:
        with self._lock:
            frame = self._frame
            gesture = self._gesture
            overlay = self._overlay_text
            fingers = self._fingers
            hand_proto = self._hand_proto
            hand_data = self._hand_data

        self.fps_lbl.setText(f"FPS {self.fps:.0f}")
        if self.running and self._camera_error_text:
            self.cam_status.setText(self._camera_error_text)
        self.gesture_lbl.setText(gesture.value)
        if gesture != self._last_badge_gesture:
            self._last_badge_gesture = gesture
            color = _gesture_accent(gesture)
            if gesture == GestureType.PAUSE:
                self.gesture_lbl.setStyleSheet("border-radius: 16px; padding: 8px 14px; font-weight: 800; background: #18181B; color: #F1F5F9;")
            else:
                self.gesture_lbl.setStyleSheet(
                    f"border-radius: 16px; padding: 8px 14px; font-weight: 800;"
                    f"background: {color}33; border: 1px solid {color}66; color: {color};"
                )
        self.fingers_lbl.setText(f"Fingers: {fingers}")
        self.hand_lbl.setText("Hand: Detected" if hand_proto is not None else "Hand: Not Detected")
        if hand_data and "confidence" in hand_data:
            conf = hand_data["confidence"]
            self.confidence_lbl.setText(f"Confidence: {conf * 100:.0f}%")
        else:
            self.confidence_lbl.setText("Confidence: —")

        for i, lbl in enumerate(self._history_labels):
            if i < len(self._gesture_history):
                g, ts = self._gesture_history[i]
                color = _gesture_accent(g)
                lbl.setText(f"  {g.value}  {ts}")
                lbl.setStyleSheet(
                    f"background: transparent; color: {color}; border-radius: 6px;"
                    f"padding: 2px 0px; font-size: 13px; font-weight: 600;"
                )
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

        if self._overlay is not None:
            try:
                self._overlay.update_status(gesture, self.fps, hand_proto is not None)  # type: ignore
            except Exception:
                pass

        if self.isMinimized() or frame is None:
            return

        self._sync_margin_controls()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if self._show_control_region:
            left, top, right, bottom = self.mapper.control_region()
            cv2.rectangle(rgb, (left, top), (right, bottom), (34, 211, 238), 2, cv2.LINE_AA)

        tracker = self.tracker
        if self.debug and hand_proto is not None and tracker is not None:
            label = hand_data["label"] if hand_data else "Right"
            tracker.draw(rgb, hand_proto, label)

        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qimg)
        self.preview.setPixmap(
            pix.scaled(
                self.preview.contentsRect().size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _execute_media(self, gesture: GestureType, delta: int) -> None:
        action = ""
        if gesture == GestureType.MEDIA_VOL_UP:
            action = "vol_up"
        elif gesture == GestureType.MEDIA_VOL_DOWN:
            action = "vol_down"
        elif gesture == GestureType.MEDIA_NEXT:
            action = "next"
        elif gesture == GestureType.MEDIA_PREV:
            action = "prev"

        if not action:
            return

        count = max(1, abs(int(delta))) if gesture in (GestureType.MEDIA_VOL_UP, GestureType.MEDIA_VOL_DOWN) else 1
        self.mouse.send_media_key(action, count)

    def _save_window_geometry(self) -> None:
        settings.set("window_x", self.x())
        settings.set("window_y", self.y())
        settings.set("window_w", self.width())
        settings.set("window_h", self.height())

    def _quit_app(self) -> None:
        self._quitting = True
        self._save_window_geometry()
        if self._overlay is not None:
            settings.set("overlay_x", self._overlay.x())  # type: ignore
            settings.set("overlay_y", self._overlay.y())  # type: ignore
        if self._tray is not None:
            self._tray.hide()  # type: ignore
        self.stop_camera()
        if self.tracker is not None:
            self.tracker.close()  # type: ignore
        self.mouse.stop()
        QApplication.instance().quit()  # type: ignore

    def closeEvent(self, event) -> None:
        if self._tray is not None and self._tray.isVisible() and not self._quitting:  # type: ignore
            self.hide()
            event.ignore()
            return

        self._save_window_geometry()
        if self._overlay is not None:
            settings.set("overlay_x", self._overlay.x())  # type: ignore
            settings.set("overlay_y", self._overlay.y())  # type: ignore

        try:
            self.stop_camera()
        except Exception:
            pass
        try:
            if self.tracker is not None:
                self.tracker.close()  # type: ignore
        except Exception:
            pass
        try:
            self.mouse.stop()
        except Exception:
            pass
        if self._dimmer is not None:
            self._dimmer.deleteLater()  # type: ignore
            self._dimmer = None
        event.accept()
