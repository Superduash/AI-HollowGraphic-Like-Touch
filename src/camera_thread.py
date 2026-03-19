from __future__ import annotations

import platform
import threading
import time
from dataclasses import dataclass

import cv2

from .tuning import (
    CAMERA_FAIL_SLEEP_S,
    CAMERA_LOOP_IDLE_S,
    CAMERA_READ_RETRY_LIMIT,
    CAMERA_REOPEN_COOLDOWN_S,
    CAMERA_TARGET_SIZES,
)

FilterGraph = None  # type: ignore[assignment]
wmi = None  # type: ignore[assignment]
if platform.system() == "Windows":
    try:
        from pygrabber.dshow_graph import FilterGraph  # type: ignore
    except Exception:
        FilterGraph = None  # type: ignore[assignment]

    try:
        import wmi  # type: ignore
    except Exception:
        wmi = None  # type: ignore[assignment]


@dataclass
class CameraDevice:
    index: int
    name: str


class CameraThread:
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self.camera_index = 0
        self.actual_width = width
        self.actual_height = height

        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._last_error = ""
        self._is_windows = platform.system() == "Windows"

    def _backend_candidates(self) -> list[int]:
        if self._is_windows:
            return [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
        return [cv2.CAP_ANY]

    @staticmethod
    def _try_read_frames(cap: cv2.VideoCapture, count: int = 8) -> bool:
        for _ in range(count):
            ok, frame = cap.read()
            if ok and frame is not None:
                return True
            time.sleep(0.01)
        return False

    @staticmethod
    def _drain_and_read(cap: cv2.VideoCapture):
        # Best-effort stale-frame drop so processing sees the newest image.
        for _ in range(2):
            try:
                if not cap.grab():
                    break
            except Exception:
                break

        try:
            ok, frame = cap.retrieve()
            if ok and frame is not None:
                return ok, frame
        except Exception:
            pass

        return cap.read()

    def _configure_capture(self, cap: cv2.VideoCapture, width: int, height: int, prefer_mjpg: bool = True) -> None:
        if self._is_windows and prefer_mjpg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    @staticmethod
    def _backend_name(backend: int) -> str:
        if backend == cv2.CAP_MSMF:
            return "MSMF"
        if backend == cv2.CAP_DSHOW:
            return "DSHOW"
        if backend == cv2.CAP_ANY:
            return "ANY"
        return str(backend)

    def _open_capture(self, camera_index: int) -> cv2.VideoCapture | None:
        idx = int(camera_index)
        for backend in self._backend_candidates():
            for width, height in CAMERA_TARGET_SIZES:
                # Attempt MJPG first on Windows; fallback to default format if rejected.
                for prefer_mjpg in ([True, False] if self._is_windows else [False]):
                    cap = cv2.VideoCapture(idx, backend)
                    if not cap.isOpened():
                        cap.release()
                        continue

                    self._configure_capture(cap, width, height, prefer_mjpg=prefer_mjpg)

                    if prefer_mjpg and self._is_windows:
                        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
                        if fourcc != cv2.VideoWriter_fourcc(*"MJPG"):
                            cap.release()
                            time.sleep(0.01)
                            continue

                    if not self._try_read_frames(cap):
                        cap.release()
                        time.sleep(0.03)
                        continue

                    self.actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
                    self.actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
                    fmt = "MJPG" if (prefer_mjpg and self._is_windows) else "DEFAULT"
                    self._last_error = (
                        f"Camera #{idx} opened at {self.actual_width}x{self.actual_height}"
                        f" backend={self._backend_name(backend)} format={fmt}"
                    )
                    return cap

        self._last_error = f"Cannot open camera index {idx} on MSMF/DSHOW/ANY at 1280x720 or 640x480"
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
        """Probe camera indices with the same backend policy as runtime open."""
        open_indices: list[int] = []
        for idx in range(max_index):
            found = False
            for backend in self._backend_candidates():
                if found:
                    break
                for width, height in CAMERA_TARGET_SIZES:
                    for prefer_mjpg in ([True, False] if self._is_windows else [False]):
                        cap = cv2.VideoCapture(idx, backend)
                        try:
                            if not cap.isOpened():
                                continue
                            self._configure_capture(cap, width, height, prefer_mjpg=prefer_mjpg)
                            if prefer_mjpg and self._is_windows:
                                fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
                                if fourcc != cv2.VideoWriter_fourcc(*"MJPG"):
                                    continue
                            if self._try_read_frames(cap, count=4):
                                found = True
                                break
                        finally:
                            cap.release()
                    if found:
                        break
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
        consecutive_failures = 0
        while self._running:
            with self._cap_lock:
                cap = self._cap
                if cap is None:
                    time.sleep(CAMERA_LOOP_IDLE_S)
                    continue
                ok, frame = self._drain_and_read(cap)
            if not ok or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= CAMERA_READ_RETRY_LIMIT:
                    self._last_error = "Camera stream stalled, attempting reopen"
                    new_cap = self._open_capture(self.camera_index)
                    if new_cap is not None:
                        with self._cap_lock:
                            old_cap = self._cap
                            self._cap = new_cap
                        try:
                            if old_cap is not None:
                                old_cap.release()
                        except Exception:
                            pass
                        consecutive_failures = 0
                    else:
                        self._last_error = "Camera stream lost and reopen failed"
                    time.sleep(CAMERA_REOPEN_COOLDOWN_S)
                    continue
                time.sleep(CAMERA_FAIL_SLEEP_S)
                continue

            consecutive_failures = 0
            self.actual_height, self.actual_width = frame.shape[:2]
            with self._frame_lock:
                self._frame = frame.copy()

            time.sleep(CAMERA_LOOP_IDLE_S)

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