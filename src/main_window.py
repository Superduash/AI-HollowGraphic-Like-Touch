from __future__ import annotations

import collections
import ctypes
import platform
import threading
import time
from pathlib import Path
from typing import Any, cast

import cv2  # type: ignore

import qtawesome as qta  # type: ignore
from PySide6.QtCore import QEvent, QMetaObject, QSize, Signal, Slot, Qt, QTimer  # type: ignore
from PySide6.QtGui import QAction, QIcon, QImage, QPixmap  # type: ignore
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
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(320, 150)
        self._drag_pos = None
        self._was_dragged = False
        self._last_badge_gesture: GestureType = GestureType.NONE

        root = QFrame(self)
        root.setObjectName("overlayRoot")
        root.setGeometry(0, 0, 320, 150)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

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
            #overlayRoot {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(8, 12, 20, 210), stop:1 rgba(10, 16, 28, 200));
                border: 1px solid rgba(34, 211, 238, 0.30);
                border-radius: 16px;
            }
            QLabel { color: #F1F5F9; font-size: 13px; font-weight: 600; }
            #overlayTitle { font-size: 16px; font-weight: 900; letter-spacing: 0.7px; }
            #muted { color: #8B97B0; }
            #statusOnline { color: #22D3EE; font-size: 18px; }
            #badge {
                border-radius: 11px; padding: 7px 14px; font-weight: 800;
                background: rgba(15, 18, 25, 0.78); color: #E2E8F0;
                text-transform: uppercase; letter-spacing: 1.5px;
                border: 1px solid rgba(34, 211, 238, 0.20);
                font-size: 12px;
            }
            QPushButton {
                border: 0; border-radius: 12px; color: #021820;
                padding: 8px 12px; font-weight: 800;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22D3EE, stop:1 #67E8F9);
            }
            QPushButton:hover { border: 1px solid rgba(103, 232, 249, 0.85); }
            #ghostButton { background: rgba(39, 39, 42, 0.9); color: #F1F5F9; }
            #ghostButton:hover { background: rgba(24, 24, 27, 0.96); }
            #redButton { background: #F87171; color: #1A0505; }
            #redButton:hover { border: 1px solid rgba(252, 165, 165, 0.95); }
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
            self._was_dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def was_dragged(self) -> bool:
        return self._was_dragged


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow", cameras: list[CameraDevice], selected_index: int) -> None:
        super().__init__(parent)  # type: ignore
        self._mw = parent
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.resize(640, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setFixedSize(26, 26)
        title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_icon.setPixmap(self._mw.icons["settings"].pixmap(QSize(20, 20)))
        title = QLabel("Settings")
        title.setObjectName("title")
        title_row.addWidget(title_icon)
        title_row.addWidget(title)
        title_row.addStretch(1)
        root.addLayout(title_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(10)
        scroll.setWidget(content)

        camera_box = QFrame()
        camera_box.setObjectName("sectionBox")
        camera_layout = QVBoxLayout(camera_box)
        camera_layout.setContentsMargins(14, 14, 14, 14)
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
        self.minimize_to_tray_chk = QCheckBox("Minimize to tray on close")
        self.minimize_to_tray_chk.setChecked(bool(settings.get("minimize_to_tray", False)))
        self.mouse_start_chk = QCheckBox("Enable mouse on startup")
        self.mouse_start_chk.setChecked(bool(settings.get("mouse_on_startup", False)))
        self.maximized_chk = QCheckBox("Launch app maximized")
        self.maximized_chk.setChecked(bool(settings.get("start_maximized", True)))
        self.mirror_chk = QCheckBox("Mirror camera feed")
        self.mirror_chk.setChecked(bool(settings.get("mirror_camera", True)))
        self.region_chk = QCheckBox("Show control region box")
        self.region_chk.setChecked(bool(settings.get("show_control_region", True)))

        camera_layout.addWidget(cam_label)
        camera_layout.addWidget(self.camera_combo)
        camera_layout.addWidget(self.auto_start_chk)
        camera_layout.addWidget(self.minimize_to_tray_chk)
        camera_layout.addWidget(self.mouse_start_chk)
        camera_layout.addWidget(self.maximized_chk)
        camera_layout.addWidget(self.mirror_chk)
        camera_layout.addWidget(self.region_chk)
        body.addWidget(camera_box)
        body.addSpacing(20)

        cursor_box = QFrame()
        cursor_box.setObjectName("sectionBox")
        cursor_layout = QVBoxLayout(cursor_box)
        cursor_layout.setContentsMargins(14, 14, 14, 14)
        cursor_layout.setSpacing(10)

        cursor_title = QLabel("Cursor")
        cursor_title.setObjectName("section")
        self.smooth_lbl = QLabel("Smoothening")
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(10, 100)
        self.smooth_slider.setValue(int(_as_float(settings.get("smoothening", self._mw.mapper.smoothening), self._mw.mapper.smoothening) * 10))
        self.smooth_lbl.setText(f"Smoothening: {self._mw.mapper.smoothening:.1f}")
        self.margin_lbl = QLabel(f"Head/Hand Range: {_as_int(settings.get('frame_r', self._mw.mapper.frame_r), self._mw.mapper.frame_r)}")
        self.margin_slider = QSlider(Qt.Orientation.Horizontal)
        margin_max = max(40, self._mw.mapper.max_effective_margin_px())
        self.margin_slider.setRange(40, margin_max)
        self.margin_slider.setValue(min(_as_int(settings.get("frame_r", self._mw.mapper.frame_r), self._mw.mapper.frame_r), margin_max))

        cursor_layout.addWidget(cursor_title)
        cursor_layout.addWidget(self.smooth_lbl)
        cursor_layout.addWidget(self.smooth_slider)
        cursor_layout.addWidget(self.margin_lbl)
        cursor_layout.addWidget(self.margin_slider)
        body.addWidget(cursor_box)
        body.addSpacing(20)

        gesture_box = QFrame()
        gesture_box.setObjectName("sectionBox")
        gesture_layout = QVBoxLayout(gesture_box)
        gesture_layout.setContentsMargins(14, 14, 14, 14)
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
        self.swap_dual_roles_chk = QCheckBox("Swap dual-hand roles (Left cursor, Right gestures)")
        self.swap_dual_roles_chk.setChecked(not bool(settings.get("dual_right_cursor", True)))
        gesture_layout.addWidget(gesture_title)
        gesture_layout.addWidget(self.scroll_lbl)
        gesture_layout.addWidget(self.scroll_slider)
        gesture_layout.addWidget(self.pinch_lbl)
        gesture_layout.addWidget(self.pinch_slider)
        gesture_layout.addWidget(self.hold_lbl)
        gesture_layout.addWidget(self.hold_slider)
        gesture_layout.addWidget(self.swap_dual_roles_chk)
        eye_coming = QLabel("Eye Tracking: Coming Soon")
        eye_coming.setObjectName("muted")
        gesture_layout.addWidget(eye_coming)
        body.addWidget(gesture_box)
        body.addSpacing(20)

        perf_box = QFrame()
        perf_box.setObjectName("sectionBox")
        perf_layout = QVBoxLayout(perf_box)
        perf_layout.setContentsMargins(14, 14, 14, 14)
        perf_layout.setSpacing(10)

        perf_title = QLabel("Debug")
        perf_title.setObjectName("section")
        self.debug_chk = QCheckBox("Show hand skeleton")
        self.debug_chk.setChecked(bool(settings.get("debug_overlay", True)))

        perf_layout.addWidget(perf_title)
        perf_layout.addWidget(self.debug_chk)
        body.addWidget(perf_box)
        body.addStretch(1)

        footer = QHBoxLayout()
        about_btn = QPushButton("README")
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setObjectName("warnButton")
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("primaryButton")
        close_btn = QPushButton("Close")
        close_btn.setObjectName("ghostButton")
        footer.addWidget(about_btn)
        footer.addWidget(reset_btn)
        footer.addStretch(1)
        footer.addWidget(apply_btn)
        footer.addWidget(close_btn)
        root.addLayout(footer)

        self.smooth_slider.valueChanged.connect(self._on_smooth_changed)
        self.margin_slider.valueChanged.connect(self._on_margin_changed)
        self.scroll_slider.valueChanged.connect(self._on_scroll_changed)
        self.pinch_slider.valueChanged.connect(self._on_pinch_changed)
        self.hold_slider.valueChanged.connect(self._on_hold_changed)
        about_btn.clicked.connect(self._show_about)
        reset_btn.clicked.connect(self._reset_to_defaults)
        apply_btn.clicked.connect(self._apply_changes)
        close_btn.clicked.connect(self.reject)

        self.setStyleSheet(
            """
            * {
                font-family: "Segoe UI Variable Display", "Segoe UI", "Inter", sans-serif;
            }
            QDialog { background: #18181B; color: #F1F5F9; border: 1px solid #27272A; border-radius: 16px; }
            QLabel { color: #F1F5F9; font-size: 13px; font-weight: 500; }
            #title { font-size: 22px; font-weight: 900; color: #F1F5F9; letter-spacing: 0.8px; }
            #section { font-size: 15px; color: #8B97B0; font-weight: 800; text-transform: uppercase; margin-bottom: 6px; letter-spacing: 1.2px; }
            #sectionBox {
                background: rgba(15, 18, 25, 0.45);
                border: 1px solid rgba(39, 39, 42, 0.45);
                border-radius: 12px;
            }
            #muted {
                color: #94A3B8;
                font-size: 12px;
            }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
            QScrollBar::handle:vertical { background: #3F3F46; border-radius: 4px; min-height: 24px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
            
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
                color: #E2E8F0; font-weight: 700; font-size: 13px; 
                background: #27272A;
            }
            QPushButton:hover { background: #3F3F46; }
            #primaryButton {
                color: #021820;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0891B2, stop:1 #22D3EE);
            }
            #primaryButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #22D3EE, stop:1 #67E8F9);
            }
            #warnButton {
                color: #1A0505;
                background: #F59E0B;
            }
            #warnButton:hover { background: #FBBF24; }
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

        self._on_smooth_changed(self.smooth_slider.value())
        self._on_margin_changed(self.margin_slider.value())
        self._on_scroll_changed(self.scroll_slider.value())
        self._on_pinch_changed(self.pinch_slider.value())
        self._on_hold_changed(self.hold_slider.value())

    def _on_smooth_changed(self, value: int) -> None:
        smooth = value / 10.0
        self.smooth_lbl.setText(f"Smoothening: {smooth:.1f}")

    def _on_margin_changed(self, value: int) -> None:
        max_margin = max(40, self._mw.mapper.max_effective_margin_px())
        clamped = max(40, min(int(value), max_margin))
        if self.margin_slider.value() != clamped:
            self.margin_slider.setValue(clamped)
            return
        self.margin_lbl.setText(f"Head/Hand Range: {clamped}")

    def _on_scroll_changed(self, value: int) -> None:
        mult = value / 10.0
        self.scroll_lbl.setText(f"Scroll speed: {mult:.1f}x")

    def _on_pinch_changed(self, value: int) -> None:
        pinch = value / 100.0
        self.pinch_lbl.setText(f"Pinch sensitivity: {pinch:.2f}")

    def _on_hold_changed(self, value: int) -> None:
        hold_s = value / 1000.0
        self.hold_lbl.setText(f"Hold Time: {hold_s:.2f}s")

    def _collect_settings(self) -> dict[str, object]:
        cam_data = self.camera_combo.currentData()
        if cam_data is None:
            cam_data = _as_int(settings.get("camera_index", 0), 0)
        pinch_enter = self.pinch_slider.value() / 100.0
        return {
            "camera_index": int(cam_data),
            "auto_start_camera": bool(self.auto_start_chk.isChecked()),
            "minimize_to_tray": bool(self.minimize_to_tray_chk.isChecked()),
            "mouse_on_startup": bool(self.mouse_start_chk.isChecked()),
            "start_maximized": bool(self.maximized_chk.isChecked()),
            "mirror_camera": bool(self.mirror_chk.isChecked()),
            "show_control_region": bool(self.region_chk.isChecked()),
            "smoothening": self.smooth_slider.value() / 10.0,
            "frame_r": int(self.margin_slider.value()),
            "scroll_multiplier": self.scroll_slider.value() / 10.0,
            "pinch_sensitivity": pinch_enter,
            "pinch_exit_sensitivity": pinch_enter + 0.08,
            "confirm_hold_s": self.hold_slider.value() / 1000.0,
            "dual_right_cursor": not bool(self.swap_dual_roles_chk.isChecked()),
            "debug_overlay": bool(self.debug_chk.isChecked()),
        }

    def _reset_to_defaults(self) -> None:
        d = settings.DEFAULTS
        cam_idx = self.camera_combo.findData(_as_int(d.get("camera_index", 0), 0))
        if cam_idx >= 0:
            self.camera_combo.setCurrentIndex(cam_idx)
        elif self.camera_combo.count() > 0:
            self.camera_combo.setCurrentIndex(0)

        self.auto_start_chk.setChecked(bool(d.get("auto_start_camera", False)))
        self.minimize_to_tray_chk.setChecked(bool(d.get("minimize_to_tray", False)))
        self.mouse_start_chk.setChecked(bool(d.get("mouse_on_startup", False)))
        self.maximized_chk.setChecked(bool(d.get("start_maximized", True)))
        self.mirror_chk.setChecked(bool(d.get("mirror_camera", True)))
        self.region_chk.setChecked(bool(d.get("show_control_region", True)))
        self.smooth_slider.setValue(int(_as_float(d.get("smoothening", 4.8), 4.8) * 10))
        self.margin_slider.setValue(int(_as_int(d.get("frame_r", 60), 60)))
        self.scroll_slider.setValue(int(_as_float(d.get("scroll_multiplier", 1.0), 1.0) * 10))
        self.pinch_slider.setValue(int(_as_float(d.get("pinch_sensitivity", 0.22), 0.22) * 100))
        self.hold_slider.setValue(int(_as_float(d.get("confirm_hold_s", 0.03), 0.03) * 1000))
        self.swap_dual_roles_chk.setChecked(not bool(d.get("dual_right_cursor", True)))
        self.debug_chk.setChecked(bool(d.get("debug_overlay", True)))

    def _apply_changes(self) -> None:
        self._mw.apply_settings(self._collect_settings())
        self.accept()

    def _show_about(self) -> None:
        readme_path = Path(__file__).resolve().parents[1] / "README.txt"
        try:
            text = readme_path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            QMessageBox.warning(self, "README", f"Could not load README.txt\n\n{exc}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("README")
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 12, 14, 12)
        head = QLabel("Project README")
        head.setObjectName("title")
        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setPlainText(text)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(head)
        lay.addWidget(body, 1)
        lay.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)
        dlg.exec()


class MainWindow(QMainWindow):
    _camera_start_result = Signal(bool)
    _cursor_mode_request = Signal(str)
    _CURSOR_GESTURES = frozenset({
        GestureType.MOVE, GestureType.LEFT_CLICK,
        GestureType.DOUBLE_CLICK, GestureType.RIGHT_CLICK,
        GestureType.DRAG, GestureType.SCROLL,
    })
    _MODE_SWITCH_DELAY_S = 2.5

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
        self._app_icon = QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "icons" / "holographic_touch.svg"))
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)

        self.camera = CameraThread(640, 480)
        self.camera.camera_index = _as_int(settings.get("camera_index", 0), 0)

        self._mediapipe_error: str | None = None
        try:
            self.tracker: HandTracker | None = HandTracker()
        except Exception as exc:
            self.tracker = None
            self._mediapipe_error = str(exc)

        saved_mode = str(settings.get("cursor_mode", "dual_hand"))
        self._cursor_mode: str = saved_mode if saved_mode in {"dual_hand", "single_hand"} else "dual_hand"

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

        self._hand_only_mode: bool = True
        self.mapper.set_camera_size(640, 480)
        self.mapper.set_frame_margin(_as_int(settings.get("frame_r", 60), 60))
        self.mapper.set_smoothening(_as_float(settings.get("smoothening", 4.8), 4.8))
        self.mapper._hand_only_mode = self._hand_only_mode
        self.mapper.set_prediction_strength(
            float(settings.get("cursor_prediction", 0.45))
        )
        self.gestures._confirm_hold_s = _as_float(settings.get("confirm_hold_s", 0.06), 0.06)
        self.gestures._pinch_enter = _as_float(settings.get("pinch_sensitivity", 0.30), 0.30)
        self.gestures._pinch_exit = max(self.gestures._pinch_enter + 0.08, _as_float(settings.get("pinch_exit_sensitivity", 0.45), 0.45))
        self.gestures._z_tap_enabled = _as_bool(settings.get("z_tap_enabled", False), False)
        self._scroll_multiplier: float = _as_float(settings.get("scroll_multiplier", 1.0), 1.0)
        self._dual_right_cursor: bool = _as_bool(settings.get("dual_right_cursor", True), True)
        self.debug = _as_bool(settings.get("debug_overlay", True), True)
        self._mirror_camera: bool = _as_bool(settings.get("mirror_camera", True), True)
        self._show_control_region: bool = _as_bool(settings.get("show_control_region", True), True)

        self.fps = 0.0
        self._fps_prev = time.monotonic()
        self._fps_ui_last_ts = 0.0
        self._fps_ui_value = 0.0
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
        self._rgb_frame: "np.ndarray | None" = None
        self._hand_proto = None
        self._hand_data = None
        self._gesture = GestureType.PAUSE
        self._overlay_text = _OVERLAY_LABELS.get(GestureType.PAUSE, "PAUSED")
        self._fingers = 0
        self._face_tracked: bool = False
        self._kbd_lock_until = 0.0
        self._camera_cache: list[CameraDevice] = []
        self._camera_cache_ts = 0.0
        self._camera_error_text = ""
        self._last_badge_gesture: GestureType = GestureType.NONE
        self._gesture_history: collections.deque = collections.deque(maxlen=6)
        self._last_debug_print_ts = 0.0
        self._last_debug_label: str = ""
        self._drag_active = False
        self._cursor_frozen = False
        self._frozen_sx: int = -1
        self._frozen_sy: int = -1
        self._1hand_start: float | None = None
        self._2hand_start: float | None = None
        self._freeze_on: set = {
            GestureType.LEFT_CLICK,
            GestureType.RIGHT_CLICK,
            GestureType.DOUBLE_CLICK,
        }
        self._sh_cursor_history: list = []
        self._drag_progress: float = 0.0
        self._start_worker: threading.Thread | None = None

        self._build_ui()
        self._camera_start_result.connect(self._on_camera_start_done)
        self._cursor_mode_request.connect(self.set_cursor_mode)
        self._setup_tray()
        self._start_hotkey_listener()

        wx = _as_int(settings.get("window_x", -1), -1)
        wy = _as_int(settings.get("window_y", -1), -1)
        ww = _as_int(settings.get("window_w", 1280), 1280)
        wh = _as_int(settings.get("window_h", 820), 820)
        if _as_bool(settings.get("start_maximized", True), True):
            self.resize(max(ww, 1280), max(wh, 820))
            self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        else:
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
        if _as_bool(settings.get("mouse_on_startup", False), False):
            QTimer.singleShot(450, self._enable_mouse_on_startup)

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
        sl.setContentsMargins(8, 12, 8, 12)
        sl.setSpacing(8)
        status_title = QLabel("System Status")
        status_title.setObjectName("cardTitle")
        status_title.setWordWrap(True)
        
        self.gesture_lbl = QLabel("STANDBY")
        self.gesture_lbl.setObjectName("badge")
        self.gesture_lbl.setWordWrap(False)
        self.gesture_lbl.setMinimumWidth(140)
        self.mode_badge_lbl = QLabel("MODE")
        self.mode_badge_lbl.setObjectName("modeBadge")
        self.mode_badge_lbl.setWordWrap(False)

        _mode_labels = {
            "dual_hand": f"Mode: Dual Hand ({'R=Cursor L=Actions' if self._dual_right_cursor else 'L=Cursor R=Actions'})",
            "single_hand": "Mode: Single Hand",
        }
        self.mode_lbl = QLabel(_mode_labels.get(self._cursor_mode, "Mode: Dual Hand"))
        self.mode_lbl.setObjectName("secondary")
        self.mode_lbl.setWordWrap(True)
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
        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.addWidget(self.gesture_lbl)
        badge_row.addWidget(self.mode_badge_lbl)
        badge_row.addStretch(1)
        sl.addLayout(badge_row)
        sl.addSpacing(8)
        sl.addWidget(self.mode_lbl)
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
        gl.setHorizontalSpacing(12)
        gl.setVerticalSpacing(10)

        guide_title = QLabel("Protocol Guide")
        guide_title.setObjectName("cardTitle")
        guide_title.setWordWrap(True)
        gl.addWidget(guide_title, 0, 0, 1, 3)

        self._guide_grid = gl
        self._guide_icon_col = 0
        self._guide_gesture_col = 1
        self._guide_action_col = 2
        self._guide_row_widgets: list[tuple] = []

        cursor_hand = "Right" if self._dual_right_cursor else "Left"
        action_hand = "Left" if self._dual_right_cursor else "Right"
        guide_rows_dual = [
            ("move",        "Move cursor",   f"{cursor_hand} hand index finger"),
            ("left_click",  "Left click",    f"{action_hand}: Thumb+Index pinch"),
            ("double_click","Double click",  f"{action_hand}: Quick double pinch"),
            ("drag",        "Drag",          f"{action_hand}: Hold pinch"),
            ("right_click", "Right click",   f"{action_hand}: Thumb+Middle pinch"),
            ("scroll",      "Scroll",        f"{action_hand}: Peace sign up/down"),
        ]
        guide_rows_single = [
            ("move",        "Move cursor",   "Index finger up"),
            ("left_click",  "Left click",    "Thumb+Index pinch"),
            ("double_click","Double click",  "Quick double pinch"),
            ("drag",        "Drag",          "Hold pinch"),
            ("right_click", "Right click",   "Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Peace sign up/down"),
        ]
        if self._cursor_mode == "dual_hand":
            _rows = guide_rows_dual
        else:
            _rows = guide_rows_single
        for i, (icon_key, action_desc, gesture_desc) in enumerate(_rows, start=1):
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
            self._guide_row_widgets.append((il, tl, dl))

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
        side_wrap.setMinimumWidth(320)
        side_wrap.setMaximumWidth(450)
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

        self._region_label = QLabel(f"Head/Hand Range: {self.mapper.frame_r}")
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
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #07090F, stop:1 #0B1220);
                color: #F1F5F9;
            }
            
            #headerCard {
                background: rgba(15, 18, 25, 0.72);
                border: 1px solid rgba(34, 211, 238, 0.16);
                border-radius: 14px;
            }
            #floatingDock {
                background: rgba(15, 18, 25, 0.94);
                border: 1px solid rgba(34, 211, 238, 0.20);
                border-radius: 26px;
            }
            #sideCard {
                background: rgba(15, 18, 25, 0.70);
                border: 1px solid rgba(34, 211, 238, 0.15);
                border-radius: 12px;
                padding: 14px;
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
                font-size: 13px; font-weight: 800; color: #64748B; 
                text-transform: uppercase; letter-spacing: 2px; 
                padding-bottom: 4px; 
            }
            
            #statusOffline { color: #F87171; font-size: 16px; }
            #statusOnline { color: #22D3EE; font-size: 16px; }
            
            #preview {
                background: #0F1117; 
                border-radius: 14px; 
                border: 1px solid rgba(34, 211, 238, 0.14);
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
            #secondary { color: #E8EDF5; font-size: 13px; font-weight: 600;}
            #muted { color: #64748B; font-size: 13px; font-weight: 500;}
            
            #badge {
                border-radius: 12px; padding: 8px 20px; font-weight: 700;
                background: rgba(15, 18, 25, 0.8); color: #E2E8F0;
                min-width: 110px; max-width: 220px;
                font-size: 14px; letter-spacing: 1.5px;
                border: 1px solid rgba(39, 39, 42, 0.4);
                text-align: center;
            }
            #modeBadge {
                border-radius: 10px; padding: 5px 10px; font-weight: 700;
                min-width: 90px; font-size: 11px; letter-spacing: 1px;
                text-align: center; color: #E2E8F0;
                background: rgba(39, 39, 42, 0.45);
                border: 1px solid rgba(39, 39, 42, 0.4);
            }
            #historyItem { 
                font-weight: 500; 
                font-family: "Cascadia Code", "Consolas", "SF Mono", monospace;
                font-size: 13px;
                color: #94A3B8;
            }
            
            QPushButton {
                border: none; 
                border-radius: 14px; 
                padding: 12px 24px;
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
        if not getattr(self, "_app_icon", QIcon()).isNull():
            tray.setIcon(self._app_icon)
        else:
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

    def apply_settings(self, data: dict[str, object]) -> None:
        index = _as_int(data.get("camera_index", self.camera.camera_index), self.camera.camera_index)
        if index != self.camera.camera_index:
            self._on_camera_selected(index)
        else:
            settings.set("camera_index", index)

        auto_start = _as_bool(data.get("auto_start_camera", settings.get("auto_start_camera", False)), False)
        minimize_to_tray = _as_bool(data.get("minimize_to_tray", settings.get("minimize_to_tray", False)), False)
        mouse_on_startup = _as_bool(data.get("mouse_on_startup", settings.get("mouse_on_startup", False)), False)
        start_maximized = _as_bool(data.get("start_maximized", settings.get("start_maximized", True)), True)
        mirror = _as_bool(data.get("mirror_camera", self._mirror_camera), self._mirror_camera)
        show_region = _as_bool(data.get("show_control_region", self._show_control_region), self._show_control_region)
        smooth = _as_float(data.get("smoothening", self.mapper.smoothening), self.mapper.smoothening)
        margin = _as_int(data.get("frame_r", self.mapper.frame_r), self.mapper.frame_r)
        scroll_mult = _as_float(data.get("scroll_multiplier", self._scroll_multiplier), self._scroll_multiplier)
        pinch_enter = _as_float(data.get("pinch_sensitivity", self.gestures._pinch_enter), self.gestures._pinch_enter)
        pinch_exit = _as_float(data.get("pinch_exit_sensitivity", max(pinch_enter + 0.08, self.gestures._pinch_exit)), max(pinch_enter + 0.08, self.gestures._pinch_exit))
        hold_s = _as_float(data.get("confirm_hold_s", self.gestures._confirm_hold_s), self.gestures._confirm_hold_s)
        dual_right_cursor = _as_bool(data.get("dual_right_cursor", self._dual_right_cursor), self._dual_right_cursor)
        debug = _as_bool(data.get("debug_overlay", self.debug), self.debug)

        self._mirror_camera = mirror
        self._show_control_region = show_region
        self.mapper.set_smoothening(smooth)
        self._set_control_margin(margin)
        self._scroll_multiplier = scroll_mult
        self.gestures._pinch_enter = pinch_enter
        self.gestures._pinch_exit = max(pinch_enter + 0.08, pinch_exit)
        self.gestures._confirm_hold_s = hold_s
        self._dual_right_cursor = dual_right_cursor
        self.debug = debug

        settings.set("auto_start_camera", auto_start)
        settings.set("minimize_to_tray", minimize_to_tray)
        settings.set("mouse_on_startup", mouse_on_startup)
        settings.set("start_maximized", start_maximized)
        settings.set("mirror_camera", mirror)
        settings.set("show_control_region", show_region)
        settings.set("smoothening", smooth)
        settings.set("scroll_multiplier", scroll_mult)
        settings.set("pinch_sensitivity", pinch_enter)
        settings.set("pinch_exit_sensitivity", self.gestures._pinch_exit)
        settings.set("confirm_hold_s", hold_s)
        settings.set("dual_right_cursor", dual_right_cursor)
        settings.set("debug_overlay", debug)
        self._update_guide_rows()
        self._sync_margin_controls()

        if start_maximized:
            self.showMaximized()
        elif self.isMaximized():
            self.showNormal()

    @Slot()
    def _enable_mouse_on_startup(self) -> None:
        if not self.mouse_enabled:
            self.toggle_mouse()

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
        self._region_label.setText(f"Head/Hand Range: {self.mapper.frame_r}")
        if self._region_slider.maximum() != max_margin:
            self._region_slider.setMaximum(max_margin)
        if self._region_slider.value() != clamped:
            self._region_slider.setValue(clamped)
        settings.set("frame_r", self.mapper.frame_r)

    def _dual_cursor_point(self, hand_data: dict | None) -> tuple[int, int] | None:
        """Return cursor tracking point for the cursor hand in dual mode.

        Uses weighted blend of palm center (landmark 9) and index tip (landmark 8):
        - When index finger is extended: 70% index tip + 30% palm center
          (responsive to pointing direction)
        - When fingers are curled/closed: 100% palm center
          (stable, no jump when fingers touch)

        This eliminates cursor jumping when fingers contact each other during
        movement, while still allowing precise pointing when index is extended.
        """
        if hand_data is None:
            return None
        xy = hand_data.get("xy", [])
        if not xy or len(xy) < 13:
            return None

        wrist = xy[0]
        mcp9 = xy[9]  # Palm center - most stable point

        # Always have palm center as baseline
        palm_x, palm_y = float(mcp9[0]), float(mcp9[1])

        # Check if index finger is extended
        if len(xy) > 8:
            tip8 = xy[8]
            pip6 = xy[6]
            hand_scale = max(
                12.0,
                ((float(wrist[0]) - palm_x) ** 2 + (float(wrist[1]) - palm_y) ** 2) ** 0.5,
            )
            extend_margin = max(5.0, hand_scale * 0.06)
            tip_dist = ((float(tip8[0]) - float(wrist[0])) ** 2 + (float(tip8[1]) - float(wrist[1])) ** 2) ** 0.5
            pip_dist = ((float(pip6[0]) - float(wrist[0])) ** 2 + (float(pip6[1]) - float(wrist[1])) ** 2) ** 0.5

            if tip_dist > (pip_dist + extend_margin):
                # Index extended - blend toward fingertip for precision
                return int(0.7 * float(tip8[0]) + 0.3 * palm_x), int(0.7 * float(tip8[1]) + 0.3 * palm_y)

        # Fallback: pure palm center (most stable when fingers are closed/touching)
        return int(palm_x), int(palm_y)

    @Slot(str)
    def set_cursor_mode(self, mode: str) -> None:
        mode_norm = str(mode)
        if mode_norm not in {"single_hand", "dual_hand"}:
            mode_norm = "dual_hand"

        if mode_norm == self._cursor_mode:
            return

        self._cursor_mode = mode_norm
        self.gestures._reset_all(time.monotonic())
        self._frozen_sx = -1
        self._frozen_sy = -1
        self._hand_only_mode = True
        self.mapper._hand_only_mode = self._hand_only_mode
        self._sh_cursor_history.clear()
        self.mapper.reset()

        self._update_guide_rows()

    def _update_guide_rows(self) -> None:
        """Rebuild the protocol guide to reflect current mode."""
        cursor_hand = "Right" if self._dual_right_cursor else "Left"
        action_hand = "Left" if self._dual_right_cursor else "Right"
        guide_rows_dual = [
            ("move",        "Move cursor",   f"{cursor_hand} hand index finger"),
            ("left_click",  "Left click",    f"{action_hand}: Thumb+Index pinch"),
            ("double_click","Double click",  f"{action_hand}: Quick double pinch"),
            ("drag",        "Drag",          f"{action_hand}: Hold pinch"),
            ("right_click", "Right click",   f"{action_hand}: Thumb+Middle pinch"),
            ("scroll",      "Scroll",        f"{action_hand}: Peace sign up/down"),
        ]
        guide_rows_single = [
            ("move",        "Move cursor",   "Index finger up"),
            ("left_click",  "Left click",    "Thumb+Index pinch"),
            ("double_click","Double click",  "Quick double pinch"),
            ("drag",        "Drag",          "Hold pinch"),
            ("right_click", "Right click",   "Thumb+Middle pinch"),
            ("scroll",      "Scroll",        "Peace sign up/down"),
        ]
        if self._cursor_mode == "dual_hand":
            rows = guide_rows_dual
        else:
            rows = guide_rows_single

        for idx, (il, tl, dl) in enumerate(self._guide_row_widgets):
            if idx < len(rows):
                icon_key, action_desc, gesture_desc = rows[idx]
                il.setPixmap(self.icons[icon_key].pixmap(QSize(18, 18)))
                tl.setText(gesture_desc)
                dl.setText(action_desc)

        _mode_labels = {
            "dual_hand": f"Mode: Dual Hand ({'R=Cursor L=Actions' if self._dual_right_cursor else 'L=Cursor R=Actions'})",
            "single_hand": "Mode: Single Hand",
        }
        if hasattr(self, "mode_lbl"):
            self.mode_lbl.setText(
                _mode_labels.get(self._cursor_mode, "Mode: Dual Hand"))

    def _sync_margin_controls(self) -> None:
        max_margin = max(40, self.mapper.max_effective_margin_px())
        if self._region_slider.maximum() != max_margin:
            self._region_slider.setMaximum(max_margin)
        if self.mapper.frame_r > max_margin:
            self.mapper.set_frame_margin(max_margin)
            settings.set("frame_r", self.mapper.frame_r)
        if self._region_slider.value() != self.mapper.frame_r:
            self._region_slider.setValue(self.mapper.frame_r)
        self._region_label.setText(f"Head/Hand Range: {self.mapper.frame_r}")

    def start_camera(self) -> None:
        if self.running:
            return
        if self._start_worker is not None and self._start_worker.is_alive():  # type: ignore
            return
        if self._mediapipe_error:
            self.preview.setText(self._mediapipe_error)
            return

        if self.tracker is None:
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
            self.showMinimized()
            self._sync_overlay_visibility()
        else:
            self.mouse_btn.setText("Enable Mouse")
            self.mouse_lbl.setText("Mouse: OFF")
            self._hide_overlay()
            self.showNormal()
            self.raise_()

    def _show_main_window(self) -> None:
        self.showNormal()
        self.raise_()
        self._sync_overlay_visibility()

    def _ensure_overlay(self) -> None:
        if self._overlay is not None:
            return

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
        use_custom_overlay_pos = _as_bool(settings.get("overlay_custom_pos", False), False)
        if use_custom_overlay_pos and ox >= 0 and oy >= 0:
            self._overlay.move(ox, oy)  # type: ignore

    def _hide_overlay(self) -> None:
        if self._overlay is not None:
            if self._overlay.was_dragged():
                settings.set("overlay_x", self._overlay.x())  # type: ignore
                settings.set("overlay_y", self._overlay.y())  # type: ignore
                settings.set("overlay_custom_pos", True)
            self._overlay.close()  # type: ignore
            self._overlay = None

    def _sync_overlay_visibility(self) -> None:
        if self.mouse_enabled and self.isMinimized():
            self._ensure_overlay()
            if self._overlay is not None:
                self._overlay.show()  # type: ignore
        else:
            self._hide_overlay()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_overlay_visibility()

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

        while self.running:
            if time.monotonic() - last_hand_time > 5.0:
                time.sleep(0.005)

            try:
                frame = self.camera.latest()
                if frame is None:
                    continue

                if self._mirror_camera:
                    frame = cv2.flip(frame, 1)

                h, w = frame.shape[:2]
                self.mapper.set_camera_size(w, h)

                _face_tracked = False

                # ── HAND TRACKER ───────────────────────────────────
                tracker = self.tracker
                if tracker is None:
                    continue

                hands_dict, hand_protos, is_grace = tracker.detect(
                    frame, is_mirrored=self._mirror_camera)
                _face_tracked = bool(hands_dict)

                hand_count = len(hands_dict)
                now_switch = time.monotonic()
                if hand_count == 1:
                    if self._1hand_start is None:
                        self._1hand_start = now_switch
                    self._2hand_start = None
                    # Switch to single ONLY after 3 seconds of seeing just one hand
                    if (now_switch - self._1hand_start > 3.0
                            and self._cursor_mode != "single_hand"):
                        settings.set("cursor_mode", "single_hand")
                        self._cursor_mode_request.emit("single_hand")
                elif hand_count >= 2:
                    if self._2hand_start is None:
                        self._2hand_start = now_switch
                    self._1hand_start = None
                    # Switch to dual after 1.5 seconds of seeing two hands
                    if (now_switch - self._2hand_start > 1.5
                            and self._cursor_mode != "dual_hand"):
                        settings.set("cursor_mode", "dual_hand")
                        self._cursor_mode_request.emit("dual_hand")
                else:
                    self._1hand_start = None
                    self._2hand_start = None

                rgb_cached = getattr(tracker, '_last_rgb_frame', None)

                if hands_dict:
                    last_hand_time = time.monotonic()
                    # Compute hand scale from whichever hand is available
                    for _hd in hands_dict.values():
                        _xy = _hd.get("xy", [])
                        if len(_xy) >= 10:
                            _w = _xy[0]; _m = _xy[9]
                            scale = ((_w[0]-_m[0])**2 + (_w[1]-_m[1])**2)**0.5
                            self.mapper.set_hand_scale(scale)
                            break
                    self._camera_error_text = ""
                else:
                    self._camera_error_text = self.camera.last_error

                # ── GESTURE DETECTION ──────────────────────────────
                if self._cursor_mode == "dual_hand":
                    cursor_label = "Right" if self._dual_right_cursor else "Left"
                    result = self.gestures.detect_dual(hands_dict, is_grace, cursor_label=cursor_label)
                else:
                    # Single-hand mode: one hand does cursor + actions
                    action_hand = hands_dict.get("Right") or hands_dict.get("Left")
                    result = self.gestures.detect(action_hand, is_grace)

                if result is None:
                    result = GestureResult(GestureType.PAUSE, 0)

                gesture = result.gesture
                gesture_changed = gesture != last_action

                # Confidence gate
                _action_hand = hands_dict.get("Right") or hands_dict.get("Left")
                if _action_hand:
                    _conf = float(_action_hand.get("confidence", 0))
                    if _conf < 0.45 and gesture in {GestureType.LEFT_CLICK, GestureType.DOUBLE_CLICK}:
                        gesture = GestureType.MOVE
                        result = GestureResult(GestureType.MOVE, 0)
                        gesture_changed = gesture != last_action
                    elif _conf < 0.40 and gesture == GestureType.RIGHT_CLICK:
                        gesture = GestureType.MOVE
                        result = GestureResult(GestureType.MOVE, 0)
                        gesture_changed = gesture != last_action

                # ── CURSOR POSITION ────────────────────────────────
                _has_cursor = False
                sx, sy = self._frozen_sx, self._frozen_sy

                if self._cursor_mode == "dual_hand":
                    # Dual-hand: cursor hand is configurable (default right).
                    cursor_hand_label = "Right" if self._dual_right_cursor else "Left"
                    cursor_hand = hands_dict.get(cursor_hand_label)
                    _pinch_active_dual = self.gestures._left_pinch_active or self.gestures._right_pinch_active
                    if gesture in self._freeze_on or _pinch_active_dual:
                        # Freeze cursor during clicks and active pinches
                        _has_cursor = self._frozen_sx >= 0
                    else:
                        cursor_point = self._dual_cursor_point(cursor_hand)
                        if cursor_point is not None:
                            sx, sy = self.mapper.map_point(cursor_point[0], cursor_point[1])
                            _has_cursor = True
                        else:
                            _has_cursor = self._frozen_sx >= 0

                else:
                    # Single-hand legacy: index finger = cursor
                    _any_hand = hands_dict.get("Right") or hands_dict.get("Left")
                    # Pre-freeze: also freeze if pinch is physically active (before gesture confirms)
                    _pinch_active = self.gestures._left_pinch_active or self.gestures._right_pinch_active
                    if gesture in self._freeze_on or _pinch_active:
                        _has_cursor = self._frozen_sx >= 0
                    elif _any_hand and len(_any_hand.get("xy", [])) > 8:
                        tip = _any_hand["xy"][8]
                        self._sh_cursor_history.append((int(tip[0]), int(tip[1])))
                        if len(self._sh_cursor_history) > 4:
                            self._sh_cursor_history.pop(0)
                        avg_x = int(sum(p[0] for p in self._sh_cursor_history) / len(self._sh_cursor_history))
                        avg_y = int(sum(p[1] for p in self._sh_cursor_history) / len(self._sh_cursor_history))
                        sx, sy = self.mapper.map_point(avg_x, avg_y)
                        _has_cursor = True
                    else:
                        self._sh_cursor_history.clear()
                        _has_cursor = self._frozen_sx >= 0

                if _has_cursor:
                    self._frozen_sx, self._frozen_sy = sx, sy

                # ── DISPATCH ACTIONS ───────────────────────────────
                _allow_action = not is_grace

                if self.mouse_enabled and _has_cursor and gesture in self._CURSOR_GESTURES:
                    if gesture != GestureType.SCROLL:
                        self.mouse.move(sx, sy)

                    if gesture == GestureType.MOVE:
                        pass
                    elif gesture == GestureType.LEFT_CLICK and gesture_changed and _allow_action:
                        self.mouse.left_click()
                    elif gesture == GestureType.DOUBLE_CLICK and gesture_changed and _allow_action:
                        self.mouse.double_click()
                    elif gesture == GestureType.RIGHT_CLICK and gesture_changed and _allow_action:
                        self.mouse.right_click()
                    elif gesture == GestureType.SCROLL and _allow_action:
                        self.mouse.scroll(int(result.scroll_delta * self._scroll_multiplier))
                    elif gesture == GestureType.DRAG:
                        if not self._drag_active:
                            self.mouse.start_drag()
                            self._drag_active = True

                    if gesture != GestureType.DRAG and self.mouse.is_dragging:
                        self.mouse.end_drag()
                        self._drag_active = False
                else:
                    if self.mouse.is_dragging:
                        self.mouse.end_drag()
                        self._drag_active = False

                if not self.mouse_enabled and self.mouse.is_dragging:
                    self.mouse.end_drag()
                    self._drag_active = False

                # ── UPDATE UI STATE ────────────────────────────────
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

                # Finger count
                _finger_count = 0
                _count_hand = hands_dict.get("Right") or hands_dict.get("Left")
                if _count_hand:
                    try:
                        _xy = _count_hand.get("xy", [])
                        if len(_xy) >= 21:
                            _w = _xy[0]
                            for _t, _p in zip([4,8,12,16,20], [2,6,10,14,18]):
                                _td = ((_xy[_t][0]-_w[0])**2+(_xy[_t][1]-_w[1])**2)**0.5
                                _pd = ((_xy[_p][0]-_w[0])**2+(_xy[_p][1]-_w[1])**2)**0.5
                                if _td > _pd:
                                    _finger_count += 1
                    except Exception:
                        pass

                with self._lock:
                    self._frame = frame
                    self._rgb_frame = rgb_cached
                    self._gesture = gesture
                    self._overlay_text = overlay
                    self._hand_proto = hand_protos  # Now a list of (proto, label)
                    self._hand_data = _count_hand
                    self._fingers = _finger_count
                    self._face_tracked = _face_tracked
                    # Update drag progress for UI arc
                    if self.gestures._left_pinch_since is not None:
                        _dp = (time.monotonic() - self.gestures._left_pinch_since) / max(0.01, self.gestures._drag_activate_s)
                        self._drag_progress = min(1.0, _dp)
                    else:
                        self._drag_progress = 0.0

            except Exception:
                continue

    def _render(self) -> None:
        with self._lock:
            frame = self._frame
            rgb_cached = self._rgb_frame
            gesture = self._gesture
            overlay = self._overlay_text
            fingers = self._fingers
            hand_proto = self._hand_proto
            hand_data = self._hand_data

        now_ui = time.monotonic()
        if now_ui - self._fps_ui_last_ts >= 1.0:
            self._fps_ui_last_ts = now_ui
            self._fps_ui_value = self.fps
            self.fps_lbl.setText(f"FPS {self._fps_ui_value:.0f}")
        if self.running and self._camera_error_text:
            self.cam_status.setText(self._camera_error_text)
        # In cursor-driven modes, MOVE maps to mode-specific status labels.
        _badge_text = gesture.value
        if gesture == GestureType.MOVE:
            if self._cursor_mode == "dual_hand":
                _badge_text = "DUAL HAND"
            else:
                _badge_text = "TRACKING" if self._face_tracked else "ACQUIRING"
        self.gesture_lbl.setText(_badge_text)
        if gesture != self._last_badge_gesture or _badge_text != getattr(self, '_last_badge_text', ''):
            self._last_badge_gesture = gesture
            self._last_badge_text = _badge_text
            color = _gesture_accent(gesture)
            if gesture in (GestureType.PAUSE, GestureType.MOVE):
                _bg = "#18181B" if gesture == GestureType.PAUSE else "#0F2419"
                _fg = "#F1F5F9" if gesture == GestureType.PAUSE else "#34D399"
                self.gesture_lbl.setStyleSheet(
                    f"border-radius: 16px; padding: 8px 14px; font-weight: 800;"
                    f"background: {_bg}; color: {_fg};"
                )
            else:
                self.gesture_lbl.setStyleSheet(
                    f"border-radius: 16px; padding: 8px 14px; font-weight: 800;"
                    f"background: {color}33; border: 1px solid {color}66; color: {color};"
                )
        self.fingers_lbl.setText(f"Fingers: {fingers}")
        with self._lock:
            _face_on = self._face_tracked

        _mode_color = "#22D3EE" if self._cursor_mode == "dual_hand" else "#A78BFA"
        _mode_icon = "⬡" if self._cursor_mode == "dual_hand" else "◈"
        _mode_text_map = {
            "dual_hand": (
                f"{_mode_icon} DUAL HAND  R=Cursor  L=Actions"
                if self._dual_right_cursor
                else f"{_mode_icon} DUAL HAND  L=Cursor  R=Actions"
            ),
            "single_hand": f"{_mode_icon} SINGLE HAND  Any hand = cursor+actions",
        }
        if hasattr(self, "mode_lbl"):
            self.mode_lbl.setText(_mode_text_map.get(self._cursor_mode, ""))
            self.mode_lbl.setStyleSheet(f"color: {_mode_color}; font-weight: 700; font-size: 12px;")

        if hasattr(self, "mode_badge_lbl"):
            _pill = {
                "dual_hand": ("DUAL", "#22D3EE"),
                "single_hand": ("SINGLE", "#A78BFA"),
            }
            _txt, _col = _pill.get(self._cursor_mode, ("MODE", "#64748B"))
            self.mode_badge_lbl.setText(_txt)
            self.mode_badge_lbl.setStyleSheet(
                f"border-radius: 10px; padding: 5px 10px; font-weight: 700;"
                f"min-width: 90px; font-size: 11px; letter-spacing: 1px;"
                f"text-align: center; color: {_col}; background: {_col}33; border: 1px solid {_col}66;"
            )

        if self._cursor_mode == "dual_hand":
            # Show both hands status
            _left_ok = False
            _right_ok = False
            if isinstance(hand_proto, list):
                for _, lbl in hand_proto:
                    if lbl == "Left":
                        _left_ok = True
                    if lbl == "Right":
                        _right_ok = True
            self.hand_lbl.setText(
                f"L: {'●' if _left_ok else '○'}  R: {'●' if _right_ok else '○'}")
            self.hand_lbl.setStyleSheet("color: #D7E3F7; font-weight: 700;")
        else:
            if hand_proto is not None:
                self.hand_lbl.setText("Single Mode: Hand Detected")
                self.hand_lbl.setStyleSheet("color: #6EE7B7; font-weight: 800;")
            else:
                self.hand_lbl.setText("Single Mode: Hand Not Detected")
                self.hand_lbl.setStyleSheet("color: #FCA5A5; font-weight: 800;")
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
                self._overlay.update_status(gesture, self._fps_ui_value, hand_proto is not None)  # type: ignore
            except Exception:
                pass

        if self.isMinimized() or frame is None:
            return

        self._sync_margin_controls()

        tracker = self.tracker
        if rgb_cached is not None:
            rgb = rgb_cached
        elif tracker is not None and hasattr(tracker, '_last_rgb_frame') and tracker._last_rgb_frame is not None:
            rgb = tracker._last_rgb_frame
        else:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if self._show_control_region:
            left, top, right, bottom = self.mapper.control_region()
            cv2.rectangle(rgb, (left, top), (right, bottom), (34, 211, 238), 2, cv2.LINE_AA)

        # Drag progress arc
        with self._lock:
            _dp = self._drag_progress
            _drag_on = self._drag_active
        if _dp > 0.05 or _drag_on:
            try:
                h_rgb, w_rgb = rgb.shape[:2]
                cx_arc = w_rgb // 2
                cy_arc = h_rgb - 30
                if _drag_on:
                    cv2.circle(rgb, (cx_arc, cy_arc), 12, (0, 200, 255), -1, cv2.LINE_AA)
                    cv2.putText(rgb, "DRAG", (cx_arc - 18, cy_arc + 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
                else:
                    angle = int(360 * _dp)
                    cv2.ellipse(rgb, (cx_arc, cy_arc), (14, 14), -90, 0, angle,
                                (0, 200, 255), 3, cv2.LINE_AA)
            except Exception:
                pass

        if hand_proto is not None and tracker is not None:
            # hand_proto is now a list of (proto, label) tuples
            if isinstance(hand_proto, list):
                tracker.draw(rgb, hand_proto)
            else:
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
        try:
            if self.tracker is not None:
                self.tracker.close()  # type: ignore
        except Exception:
            pass
        try:
            self.mouse.stop()
        except Exception:
            pass
        QApplication.instance().quit()  # type: ignore

    def closeEvent(self, event) -> None:
        if (
            bool(settings.get("minimize_to_tray", False))
            and self._tray is not None
            and self._tray.isVisible()
            and not self._quitting
        ):  # type: ignore
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
