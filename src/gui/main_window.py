"""Main application window — customtkinter GUI with threaded processing."""

import threading
import time
import traceback

import cv2
import customtkinter as ctk
import numpy as np
import pyautogui
from PIL import Image, ImageTk

from config import PROCESS_HEIGHT, PROCESS_WIDTH, TARGET_FPS
from controller.cursor_mapper import CursorMapper
from controller.mouse_controller import MouseController
from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType
from gui.gesture_help_panel import GestureHelpPanel
from tracking.hand_tracker import HandTracker
from utils.camera_thread import CameraThread
from utils.fps_counter import FPSCounter
from utils.smoothing import AdaptiveSmoother

_PREVIEW_W, _PREVIEW_H = 640, 480
_PAUSE_GESTURES = frozenset({GestureType.PAUSE, GestureType.NONE})

# Overlay display names (shorter, user-friendly)
_OVERLAY_LABELS = {
    GestureType.NONE: "",
    GestureType.MOVE: "MOVE",
    GestureType.LEFT_CLICK: "LEFT CLICK",
    GestureType.DOUBLE_CLICK: "DOUBLE CLICK",
    GestureType.RIGHT_CLICK: "RIGHT CLICK",
    GestureType.SCROLL: "SCROLL",
    GestureType.DRAG: "DRAG",
    GestureType.PAUSE: "PAUSED",
    GestureType.VOLUME: "VOLUME",
    GestureType.SWITCH_WINDOW: "SWITCH",
    GestureType.OPEN_PALM: "OPEN PALM",
}


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("AI Holographic Touch")
        self.geometry("1060x640")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # --- Components ---
        self._camera = CameraThread()
        self._tracker = HandTracker()
        self._detector = GestureDetector()
        self._smoother = AdaptiveSmoother()
        self._fps = FPSCounter(target_fps=TARGET_FPS)
        try:
            sw, sh = pyautogui.size()
        except Exception:
            sw, sh = 1920, 1080
        self._mapper = CursorMapper(PROCESS_WIDTH, PROCESS_HEIGHT, sw, sh)
        self._mouse = MouseController()

        # --- Runtime state ---
        self._processing = False
        self._proc_thread = None
        self._mouse_enabled = False
        self._debug_mode = False
        self._perf_mode = False
        self._was_dragging = False
        self._closing = False

        # --- Thread-safe results ---
        self._lock = threading.Lock()
        self._disp_frame = None
        self._gesture = GestureType.NONE
        self._hand_ok = False
        self._fps_val = 0.0
        self._error_msg = ""

        self._tk_img = None
        self._prev_overlay_text = ""
        self._build_ui()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        # --- Top bar ---
        top = ctk.CTkFrame(self, height=44, corner_radius=0)
        top.pack(fill="x")
        ctk.CTkLabel(top, text="  🖐️ AI Holographic Touch",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(side="left", padx=8)
        self._fps_lbl = ctk.CTkLabel(top, text="FPS: —", font=ctk.CTkFont(size=13))
        self._fps_lbl.pack(side="right", padx=14)

        # --- Body ---
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=6, pady=(4, 0))

        # Preview
        pf = ctk.CTkFrame(body)
        pf.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._preview = ctk.CTkLabel(pf, text="Camera Off\n\nPress  ▶ Start Camera",
                                     font=ctk.CTkFont(size=15))
        self._preview.pack(expand=True, fill="both")

        # Right panel
        rp = ctk.CTkFrame(body, width=270)
        rp.pack(side="right", fill="y")
        rp.pack_propagate(False)

        # Status section
        sf = ctk.CTkFrame(rp)
        sf.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(sf, text="Status", font=ctk.CTkFont(size=13, weight="bold")).pack(pady=(6, 2))
        self._gest_lbl = ctk.CTkLabel(sf, text="NONE", font=ctk.CTkFont(size=16, weight="bold"),
                                      text_color="#3B8ED0")
        self._gest_lbl.pack(pady=2)
        self._hand_lbl = ctk.CTkLabel(sf, text="Hand: —", font=ctk.CTkFont(size=11))
        self._hand_lbl.pack(pady=1)
        self._mouse_lbl = ctk.CTkLabel(sf, text="Mouse: OFF", font=ctk.CTkFont(size=11))
        self._mouse_lbl.pack(pady=(1, 6))

        # Gesture guide
        GestureHelpPanel(rp).pack(fill="both", expand=True, padx=8, pady=4)

        # --- Bottom bar ---
        bot = ctk.CTkFrame(self, height=52, corner_radius=0)
        bot.pack(fill="x", pady=(2, 0))
        bc = {"height": 32, "width": 130, "font": ctk.CTkFont(size=12)}

        self._btn_start = ctk.CTkButton(bot, text="▶  Start", command=self._start, **bc)
        self._btn_start.pack(side="left", padx=4, pady=8)
        self._btn_stop = ctk.CTkButton(bot, text="⬛  Stop", command=self._stop,
                                       state="disabled", **bc)
        self._btn_stop.pack(side="left", padx=4, pady=8)
        self._btn_mouse = ctk.CTkButton(bot, text="🖱  Mouse ON", command=self._toggle_mouse, **bc)
        self._btn_mouse.pack(side="left", padx=4, pady=8)
        self._btn_perf = ctk.CTkButton(bot, text="⚡ Perf", command=self._toggle_perf, **bc)
        self._btn_perf.pack(side="left", padx=4, pady=8)
        self._btn_debug = ctk.CTkButton(bot, text="🔧 Debug", command=self._toggle_debug, **bc)
        self._btn_debug.pack(side="left", padx=4, pady=8)

    # ==================================================================
    # Button handlers
    # ==================================================================

    def _start(self):
        if not self._camera.start():
            self._preview.configure(text="❌ Cannot open camera\nCheck permissions")
            return
        self._processing = True
        self._proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._proc_thread.start()
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._update_gui()

    def _stop(self):
        self._processing = False
        if self._proc_thread:
            self._proc_thread.join(timeout=2.0)
            self._proc_thread = None
        self._camera.stop()
        if self._mouse.is_dragging:
            self._mouse.end_drag()
        self._was_dragging = False
        self._smoother.reset()
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._tk_img = None
        self._preview.configure(image=None, text="Camera Off")

    def _toggle_mouse(self):
        self._mouse_enabled = not self._mouse_enabled
        t = "🖱  Mouse OFF" if self._mouse_enabled else "🖱  Mouse ON"
        self._btn_mouse.configure(text=t)

    def _toggle_perf(self):
        self._perf_mode = not self._perf_mode
        c = "#2FA572" if self._perf_mode else "#3B8ED0"
        self._btn_perf.configure(fg_color=c)

    def _toggle_debug(self):
        self._debug_mode = not self._debug_mode
        c = "#2FA572" if self._debug_mode else "#3B8ED0"
        self._btn_debug.configure(fg_color=c)

    def _on_close(self):
        self._closing = True
        self._stop()
        self._tracker.close()
        self.destroy()

    # ==================================================================
    # Processing thread
    # ==================================================================

    def _process_loop(self):
        skip = False
        while self._processing:
            # Camera disconnected?
            if not self._camera.is_running:
                with self._lock:
                    self._error_msg = "Camera disconnected"
                self._processing = False
                break

            frame = self._camera.get_frame()
            if frame is None:
                time.sleep(0.005)
                continue

            frame = cv2.flip(frame, 1)

            # Frame skipping in performance mode
            if skip and self._perf_mode:
                skip = False
                # Use motion prediction during skipped frames
                if self._mouse_enabled:
                    px, py = self._smoother.predict()
                    if px >= 0:
                        self._mouse.move_cursor(px, py)
                with self._lock:
                    self._disp_frame = frame
                continue

            try:
                landmarks = self._tracker.process_frame(frame)
                result = self._detector.detect(landmarks)
            except Exception:
                landmarks = None
                result = self._detector.detect(None)

            gesture = result.gesture

            # Mouse control
            if self._mouse_enabled and landmarks and gesture not in _PAUSE_GESTURES:
                tip = landmarks[8]
                tx, ty = self._mapper.map_to_screen(tip[0], tip[1])
                sx, sy = self._smoother.smooth(tx, ty)

                if gesture == GestureType.MOVE:
                    self._mouse.move_cursor(sx, sy)
                elif gesture == GestureType.LEFT_CLICK:
                    self._mouse.move_cursor(sx, sy)
                    self._mouse.left_click()
                elif gesture == GestureType.DOUBLE_CLICK:
                    self._mouse.move_cursor(sx, sy)
                    self._mouse.double_click()
                elif gesture == GestureType.RIGHT_CLICK:
                    self._mouse.right_click()
                elif gesture == GestureType.SCROLL:
                    if result.scroll_delta != 0:
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

            # Debug overlay (landmarks)
            if self._debug_mode and landmarks:
                self._tracker.draw_debug(frame, landmarks)

            # Gesture action overlay (always shown)
            _draw_action_overlay(frame, gesture)

            fps_v = self._fps.update()
            with self._lock:
                self._disp_frame = frame
                self._gesture = gesture
                self._hand_ok = landmarks is not None
                self._fps_val = fps_v

            if self._fps.should_skip():
                skip = True

    # ==================================================================
    # GUI update (runs on main thread via after())
    # ==================================================================

    def _update_gui(self):
        if self._closing or not self._processing:
            # Check for error to display
            with self._lock:
                err = self._error_msg
            if err:
                try:
                    self._preview.configure(image=None, text=f"⚠ {err}")
                    self._btn_start.configure(state="normal")
                    self._btn_stop.configure(state="disabled")
                except Exception:
                    pass
            return

        with self._lock:
            frame = self._disp_frame
            gesture = self._gesture
            hand = self._hand_ok
            fps = self._fps_val

        if frame is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb).resize((_PREVIEW_W, _PREVIEW_H), Image.NEAREST)
                self._tk_img = ImageTk.PhotoImage(image=pil)
                self._preview.configure(image=self._tk_img, text="")
            except Exception:
                pass

        self._fps_lbl.configure(text=f"FPS: {fps:.0f}")
        self._gest_lbl.configure(text=gesture.value)
        hc = "#2FA572" if hand else "#E74C3C"
        self._hand_lbl.configure(text=f"Hand: {'Detected ✓' if hand else 'Not Found'}",
                                 text_color=hc)
        mc = "#2FA572" if self._mouse_enabled else "#888888"
        self._mouse_lbl.configure(text=f"Mouse: {'ON' if self._mouse_enabled else 'OFF'}",
                                  text_color=mc)

        self.after(33, self._update_gui)


def _draw_action_overlay(frame, gesture: GestureType) -> None:
    """Draw a semi-transparent action badge near the top-right of the frame."""
    label = _OVERLAY_LABELS.get(gesture, "")
    if not label:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.65
    thickness = 2
    (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)

    pad_x, pad_y = 14, 10
    box_w = tw + pad_x * 2
    box_h = th + baseline + pad_y * 2

    fh, fw = frame.shape[:2]
    margin = 16
    x1 = fw - box_w - margin
    y1 = margin
    x2 = x1 + box_w
    y2 = y1 + box_h

    # Clamp to frame bounds
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, fw), min(y2, fh)

    # Semi-transparent dark background (~65% opacity)
    roi = frame[y1:y2, x1:x2]
    overlay = np.zeros_like(roi, dtype=np.uint8)
    overlay[:] = (30, 30, 30)
    cv2.addWeighted(overlay, 0.65, roi, 0.35, 0, roi)

    # Text (white)
    text_x = x1 + pad_x
    text_y = y1 + pad_y + th
    cv2.putText(frame, label, (text_x, text_y), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
