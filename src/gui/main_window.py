"""Main application window — customtkinter GUI with threaded processing."""

import threading
import time

import cv2
import customtkinter as ctk
import pyautogui
from PIL import Image, ImageDraw, ImageFont

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


def _draw_action_overlay_pil(img: Image.Image, gesture: GestureType) -> None:
    """Draw a modern rounded semi-transparent overlay inside the preview image."""
    label = _OVERLAY_LABELS.get(gesture, "")
    if not label:
        return

    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.load_default()
    try:
        # For newer pillow
        bbox = font.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for old pillow
        tw, th = draw.textsize(label, font=font)

    # Scale up dimensions artificially since default font is small
    pad_x, pad_y = 16, 12
    box_w = tw * 2 + pad_x * 2
    box_h = th * 2 + pad_y * 2
    margin = 20

    x2 = img.width - margin
    x1 = x2 - box_w
    y1 = margin
    y2 = y1 + box_h

    # Draw rounded dark background with alpha
    radius = 8
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=(20, 20, 20, 200))

    # Center text in box
    text_x = x1 + pad_x + (box_w - pad_x * 2 - tw) // 2
    text_y = y1 + pad_y + (box_h - pad_y * 2 - th) // 2
    draw.text((text_x, text_y), label, font=font, fill=(255, 255, 255, 255))


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("AI Holographic Touch")
        # Give enough space for the new layout
        self.geometry("1100x680")
        self.resizable(True, True)
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
        self._perf_mode = False
        self._debug_mode = True  # Default to True so landmarks always appear
        self._was_dragging = False
        self._closing = False

        # --- Thread-safe results ---
        self._lock = threading.Lock()
        self._disp_frame = None
        self._gesture = GestureType.NONE
        self._hand_ok = False
        self._raw_hand = None
        self._fps_val = 0.0
        self._error_msg = ""

        self._preview_image = None
        self._build_ui()

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self):
        # Top Header
        top = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color="#1E1E1E")
        top.pack(fill="x")

        title = ctk.CTkLabel(top, text="  🖐️ Holographic Touch",
                             font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(side="left", padx=16, pady=10)

        self._fps_lbl = ctk.CTkLabel(top, text="FPS: 0",
                                     font=ctk.CTkFont(size=14, weight="bold"),
                                     text_color="#2FA572")
        self._fps_lbl.pack(side="right", padx=16)

        self._cam_stat_lbl = ctk.CTkLabel(top, text="● Offline",
                                          font=ctk.CTkFont(size=14, weight="bold"),
                                          text_color="#E74C3C")
        self._cam_stat_lbl.pack(side="right", padx=16)

        # Body
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(16, 0))

        # Preview Area
        pf = ctk.CTkFrame(body, corner_radius=12, fg_color="#2B2B2B")
        pf.pack(side="left", fill="both", expand=True, padx=(0, 16))

        self._preview = ctk.CTkLabel(pf, text="Camera Offline\n\nClick 'Start Camera' below",
                                     font=ctk.CTkFont(size=16))
        self._preview.pack(expand=True, fill="both", padx=4, pady=4)

        # Sidebar
        rp = ctk.CTkFrame(body, width=320, corner_radius=12, fg_color="transparent")
        rp.pack(side="right", fill="y")
        rp.pack_propagate(False)

        # Status Panel
        sf = ctk.CTkFrame(rp, corner_radius=10, fg_color="#333333")
        sf.pack(fill="x", pady=(0, 16))

        ctk.CTkLabel(sf, text="Gesture Status", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 4))
        self._gest_lbl = ctk.CTkLabel(sf, text="NONE", font=ctk.CTkFont(size=24, weight="bold"), text_color="#3B8ED0")
        self._gest_lbl.pack(pady=(0, 8))

        self._hand_lbl = ctk.CTkLabel(sf, text="Hand: Not Found", font=ctk.CTkFont(size=13))
        self._hand_lbl.pack(pady=2)

        self._mode_lbl = ctk.CTkLabel(sf, text="Mouse: Disabled", font=ctk.CTkFont(size=13))
        self._mode_lbl.pack(pady=(2, 12))

        # Help Guide Panel
        hf = GestureHelpPanel(rp, corner_radius=10, fg_color="#333333")
        hf.pack(fill="both", expand=True)

        # Bottom Bar
        bot = ctk.CTkFrame(self, height=64, corner_radius=12, fg_color="#2B2B2B")
        bot.pack(fill="x", padx=16, pady=16)

        bc = {"height": 38, "font": ctk.CTkFont(size=14, weight="bold"), "corner_radius": 6}

        self._btn_start = ctk.CTkButton(bot, text="▶ Start Camera", command=self._start,
                                        width=150, fg_color="#2FA572", hover_color="#25835A", **bc)
        self._btn_start.pack(side="left", padx=12, pady=12)

        self._btn_stop = ctk.CTkButton(bot, text="⬛ Stop Camera", command=self._stop,
                                       width=150, fg_color="#E74C3C", hover_color="#B83C30",
                                       state="disabled", **bc)
        self._btn_stop.pack(side="left", padx=12, pady=12)

        self._btn_mouse = ctk.CTkButton(bot, text="🖱 Enable Mouse", command=self._toggle_mouse,
                                        width=150, border_width=2, fg_color="transparent",
                                        border_color="#3B8ED0", text_color="#3B8ED0",
                                        hover_color="#1E4768", **bc)
        self._btn_mouse.pack(side="left", padx=(32, 12), pady=12)

        # Switches Frame
        sw_f = ctk.CTkFrame(bot, fg_color="transparent")
        sw_f.pack(side="right", padx=12, pady=12)

        self._btn_perf = ctk.CTkSwitch(sw_f, text="⚡ Perf", command=self._toggle_perf,
                                       font=ctk.CTkFont(size=13, weight="bold"))
        self._btn_perf.pack(side="left", padx=8)

        self._btn_debug = ctk.CTkSwitch(sw_f, text="🔧 Skeleton", command=self._toggle_debug,
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self._btn_debug.pack(side="left", padx=8)
        self._btn_debug.select()  # Enable by default

    # ==================================================================
    # Button handlers
    # ==================================================================

    def _start(self):
        if self._processing or (self._proc_thread and self._proc_thread.is_alive()):
            return

        # Ensure tracker is initialized fresh each start.
        try:
            self._tracker.close()
        except Exception:
            pass
        self._tracker = HandTracker()

        if not self._camera.start():
            reason = self._camera.last_error or "Check permissions and camera availability"
            self._preview_image = None
            self._preview.configure(image=self._preview_image,
                                    text=f"❌ Cannot open camera\n{reason}")
            self._cam_stat_lbl.configure(text="● Error", text_color="#E74C3C")
            return

        with self._lock:
            self._error_msg = ""

        self._processing = True
        self._proc_thread = threading.Thread(target=self._process_loop, daemon=True)
        self._proc_thread.start()
        
        self._cam_stat_lbl.configure(text="● Live", text_color="#2FA572")
        self._btn_start.configure(state="disabled")
        self._btn_stop.configure(state="normal")
        self._update_gui()

    def _stop(self):
        was_processing = self._processing
        self._processing = False

        if self._proc_thread and self._proc_thread.is_alive():
            self._proc_thread.join(timeout=2.0)
        if self._proc_thread:
            self._proc_thread = None

        self._camera.stop()
        try:
            self._tracker.close()
        except Exception:
            pass

        if self._mouse.is_dragging:
            self._mouse.end_drag()
        self._was_dragging = False
        self._smoother.reset()

        with self._lock:
            self._disp_frame = None
            self._gesture = GestureType.NONE
            self._hand_ok = False
            self._raw_hand = None
            if not was_processing:
                self._error_msg = ""

        self._cam_stat_lbl.configure(text="● Offline", text_color="#E74C3C")
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._preview_image = None
        self._preview.configure(image=self._preview_image, text="Camera Offline")

    def _toggle_mouse(self):
        self._mouse_enabled = not self._mouse_enabled
        if self._mouse_enabled:
            self._btn_mouse.configure(text="🖱 Disable Mouse", fg_color="#3B8ED0", text_color="white")
        else:
            self._btn_mouse.configure(text="🖱 Enable Mouse", fg_color="transparent", text_color="#3B8ED0")

    def _toggle_perf(self):
        self._perf_mode = bool(self._btn_perf.get())

    def _toggle_debug(self):
        self._debug_mode = bool(self._btn_debug.get())

    def _on_close(self):
        self._closing = True
        self._stop()
        try:
            self._tracker.close()
        except Exception:
            pass
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
                landmarks, raw_hand = self._tracker.process_frame(frame)
                result = self._detector.detect(landmarks)
            except Exception:
                landmarks, raw_hand = None, None
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

            fps_v = self._fps.update()
            with self._lock:
                self._disp_frame = frame
                self._gesture = gesture
                self._hand_ok = landmarks is not None
                self._raw_hand = raw_hand
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
                    self._cam_stat_lbl.configure(text="● Error", text_color="#E74C3C")
                except Exception:
                    pass
            return

        with self._lock:
            frame = self._disp_frame
            gesture = self._gesture
            hand = self._hand_ok
            raw_hand = self._raw_hand
            fps = self._fps_val

        if frame is not None:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # Draw skeleton if requested and found
                if self._debug_mode and raw_hand:
                    self._tracker.draw_landmarks(rgb, raw_hand)

                # Resize and add overlay using PIL
                pil_img = Image.fromarray(rgb).resize((_PREVIEW_W, _PREVIEW_H), Image.BILINEAR).convert("RGBA")
                _draw_action_overlay_pil(pil_img, gesture)

                self._preview_image = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=(_PREVIEW_W, _PREVIEW_H),
                )
                self._preview.configure(image=self._preview_image, text="")
            except Exception:
                pass

        self._fps_lbl.configure(text=f"FPS: {fps:.0f}")
        self._gest_lbl.configure(text=gesture.value)
        hc = "#2FA572" if hand else "#AAAAAA"
        self._hand_lbl.configure(text=f"Hand: {'Detected ✓' if hand else 'Not Found'}",
                                 text_color=hc)
        mc = "#2FA572" if self._mouse_enabled else "#AAAAAA"
        self._mode_lbl.configure(text=f"Mouse: {'Active' if self._mouse_enabled else 'Disabled'}",
                                 text_color=mc)

        self.after(33, self._update_gui)
