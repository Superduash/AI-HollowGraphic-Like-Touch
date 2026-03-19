from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

try:
    from pygrabber.dshow_graph import FilterGraph  # type: ignore
except Exception:
    FilterGraph = None  # type: ignore[assignment]

try:
    import wmi  # type: ignore
except Exception:
    wmi = None  # type: ignore[assignment]


# Backend fallback chain used by both _open_capture() and enumerate_cameras().
# Each entry is (backend_constant, label, try_mjpg).
_BACKEND_CHAIN = [
    (cv2.CAP_DSHOW, "CAP_DSHOW", True),   # fast path, real webcams on Windows
    (cv2.CAP_DSHOW, "CAP_DSHOW", False),   # DShow without MJPG
    (cv2.CAP_MSMF,  "CAP_MSMF",  False),  # Windows Media Foundation (OBS Virtual Cam)
    (cv2.CAP_ANY,   "CAP_ANY",   False),   # universal fallback
]


@dataclass
class CameraDevice:
    index: int
    name: str


class CameraThread:
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self.camera_index = 0

        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._last_error = ""

    # ------------------------------------------------------------------
    # Capture helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _configure_capture(
        cap: cv2.VideoCapture,
        width: int,
        height: int,
        use_fourcc: bool = True,
    ) -> None:
        """Configure resolution, FPS, and buffer.  Optionally set MJPG FOURCC."""
        if use_fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    @staticmethod
    def _try_read_frames(cap: cv2.VideoCapture, count: int = 5) -> bool:
        """Read *count* frames; return True if at least one is valid."""
        for _ in range(count):
            ok, frame = cap.read()
            if ok and frame is not None:
                return True
            time.sleep(0.02)
        return False

    def _open_capture(self, camera_index: int) -> cv2.VideoCapture | None:
        """Try each backend in _BACKEND_CHAIN until one delivers frames."""
        idx = int(camera_index)

        for backend, label, try_mjpg in _BACKEND_CHAIN:
            cap = cv2.VideoCapture(idx, backend)
            if not cap.isOpened():
                cap.release()
                continue

            self._configure_capture(cap, self.width, self.height, use_fourcc=try_mjpg)

            if self._try_read_frames(cap, count=5):
                mjpg_note = "MJPG" if try_mjpg else "MJPG not set"
                self._last_error = (
                    f"Camera #{idx} opened via {label} ({mjpg_note})"
                )
                return cap

            cap.release()
            time.sleep(0.05)

        self._last_error = (
            f"Cannot open camera index {idx} with any backend "
            f"(tried {', '.join(l for _, l, _ in _BACKEND_CHAIN)})"
        )
        return None

    # ------------------------------------------------------------------
    # Enumeration helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _dshow_camera_names() -> list[str]:
        if FilterGraph is None:
            return []

        try:
            graph = FilterGraph()
            names = [str(n).strip() for n in graph.get_input_devices() if str(n).strip()]
            return names
        except Exception:
            return []

    @staticmethod
    def _system_camera_names() -> list[str]:
        names: list[str] = []
        if wmi is None:
            return names

        try:
            conn = wmi.WMI()
            devices = conn.Win32_PnPEntity()
            for dev in devices:
                name = str(getattr(dev, "Name", "") or "").strip()
                if not name:
                    continue
                low = name.lower()
                if any(k in low for k in ("camera", "webcam", "droidcam", "capture")):
                    if name not in names:
                        names.append(name)
        except Exception:
            return names
        return names

    def enumerate_cameras(self, max_index: int = 8) -> list[CameraDevice]:
        """Probe indices 0‥max_index using the backend fallback chain."""
        open_indices: list[int] = []
        for idx in range(max_index):
            found = False
            for backend, _label, try_mjpg in _BACKEND_CHAIN:
                cap = cv2.VideoCapture(idx, backend)
                try:
                    if not cap.isOpened():
                        continue
                    self._configure_capture(
                        cap, self.width, self.height, use_fourcc=try_mjpg,
                    )
                    if self._try_read_frames(cap, count=5):
                        found = True
                        break
                finally:
                    cap.release()
            if found:
                open_indices.append(idx)

        system_names = self._dshow_camera_names() or self._system_camera_names()
        devices: list[CameraDevice] = []
        for pos, idx in enumerate(open_indices):
            if pos < len(system_names):
                name = f"{system_names[pos]} [#{idx}]"
            else:
                name = f"Camera #{idx}"
            devices.append(CameraDevice(index=idx, name=name))

        if not devices:
            devices.append(CameraDevice(index=0, name="Camera #0"))
        return devices

    # ------------------------------------------------------------------
    # Thread lifecycle (unchanged)
    # ------------------------------------------------------------------
    def start(self, camera_index: int | None = None) -> bool:
        if camera_index is not None:
            self.camera_index = int(camera_index)

        if self._running:
            return True

        cap = self._open_capture(self.camera_index)
        if cap is None:
            return False

        with self._cap_lock:
            self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def switch_camera(self, camera_index: int) -> bool:
        self.camera_index = int(camera_index)

        if not self._running:
            cap = self._open_capture(self.camera_index)
            if cap is None:
                return False
            cap.release()
            return True

        # Hard release before re-init to avoid stale DirectShow handles.
        with self._cap_lock:
            old_cap = self._cap
            self._cap = None
        if old_cap is not None:
            try:
                old_cap.release()
            except Exception:
                pass
        time.sleep(0.08)

        cap = self._open_capture(self.camera_index)
        if cap is None:
            return False

        with self._cap_lock:
            self._cap = cap
        return True

    def _loop(self) -> None:
        while self._running:
            with self._cap_lock:
                cap = self._cap
                if cap is None:
                    time.sleep(0.005)
                    continue
                ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue

            with self._frame_lock:
                self._frame = frame

    def latest(self):
        with self._frame_lock:
            return self._frame

    def stop(self) -> None:
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

        with self._cap_lock:
            cap = self._cap
            self._cap = None
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

        with self._frame_lock:
            self._frame = None

    @property
    def last_error(self) -> str:
        return self._last_error