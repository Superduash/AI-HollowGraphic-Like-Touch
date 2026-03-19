from __future__ import annotations

import platform
import threading
import time
import os
from dataclasses import dataclass
from typing import Any, cast

import cv2  # type: ignore

try:
    cv2.setLogLevel(0)
except Exception:
    pass


def _videowriter_fourcc(*chars: str) -> int:
    fn = getattr(cv2, "VideoWriter_fourcc", None)
    if callable(fn):
        value = cast(Any, fn)(*chars)
        return int(cast(Any, value))
    writer = getattr(cv2, "VideoWriter", None)
    if writer is not None:
        fn2 = getattr(writer, "fourcc", None)
        if callable(fn2):
            value = cast(Any, fn2)(*chars)
            return int(cast(Any, value))
    return 0


_MJPG_FOURCC = _videowriter_fourcc(*"MJPG")

from .tuning import CAMERA_FAIL_SLEEP_S, CAMERA_READ_RETRY_LIMIT, CAMERA_REOPEN_COOLDOWN_S, CAMERA_TARGET_SIZES  # type: ignore

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
        self.camera_backend = cv2.CAP_ANY
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
        self._printed_camera_log = False

    def _backend_candidates(self) -> list[int]:
        if self._is_windows:
            return [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
        return [cv2.CAP_ANY]

    @staticmethod
    def _try_read_frames(cap: cv2.VideoCapture, count: int = 5) -> bool:
        for _ in range(count):
            ok, frame = cap.read()
            if ok and frame is not None:
                return True
            time.sleep(0.025)
        return False

    @staticmethod
    def _backend_name(backend: int) -> str:
        if backend == cv2.CAP_MSMF:
            return "MSMF"
        if backend == cv2.CAP_DSHOW:
            return "DSHOW"
        if backend == cv2.CAP_ANY:
            return "ANY"
        return str(backend)

    @staticmethod
    def _is_valid_frame(frame: Any) -> bool:
        if frame is None:
            return False
        shape = getattr(frame, "shape", None)
        if not shape or len(shape) < 2:
            return False
        return int(shape[0]) > 0 and int(shape[1]) > 0

    def find_working_camera(
        self,
        preferred_index: int | None = None,
        min_index: int = 0,
        max_index: int = 5,
    ) -> tuple[int, int, cv2.VideoCapture] | None:
        attempted: list[str] = []
        indices = list(range(min_index, max_index + 1))

        if preferred_index is not None and preferred_index not in indices:
            indices = [int(preferred_index)] + indices
        elif preferred_index is not None:
            indices.remove(int(preferred_index))
            indices = [int(preferred_index)] + indices

        for idx in indices:
            for backend in self._backend_candidates():
                cap = cv2.VideoCapture(int(idx), int(backend))
                attempted.append(f"{idx}:{self._backend_name(backend)}")
                if not cap.isOpened():
                    try:
                        cap.release()
                    except Exception:
                        pass
                    continue

                if self._is_windows:
                    cap.set(cv2.CAP_PROP_FOURCC, _MJPG_FOURCC)
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.width))
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.height))
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                ok, frame = cap.read()
                if ok and self._is_valid_frame(frame):
                    cap.set(cv2.CAP_PROP_FPS, 60)
                    self.actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or frame.shape[1])
                    self.actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or frame.shape[0])
                    self._last_error = f"Camera ready index={idx} backend={self._backend_name(backend)}"
                    return int(idx), int(backend), cap

                try:
                    cap.release()
                except Exception:
                    pass

            time.sleep(0.01)

        self._last_error = f"No valid camera found after scanning: {', '.join(attempted)}"
        return None

    def _open_capture(self, camera_index: int) -> cv2.VideoCapture | None:
        found = self.find_working_camera(preferred_index=int(camera_index), min_index=0, max_index=5)
        if found is None:
            return None

        idx, backend, cap = found
        self.camera_index = idx
        self.camera_backend = backend
        if not self._printed_camera_log:
            print(
                f"[CAMERA] Using index={idx} backend={self._backend_name(backend)} "
                f"resolution={self.actual_width}x{self.actual_height}"
            )
            self._printed_camera_log = True
        return cap

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
        env_max = os.environ.get("WH_CAM_MAX_INDEX", "").strip()
        if env_max.isdigit():
            max_index = max(max_index, int(env_max))

        candidate_indices = list(range(max_index))
        if self._is_windows:
            known_names = self._dshow_camera_names() or self._system_camera_names()
            if known_names:
                probe_count = max(1, min(max_index, len(known_names) + 2))
                candidate_indices = list(range(probe_count))

        env_idx = os.environ.get("WH_CAM_INDEX", "").strip()
        if env_idx.isdigit():
            idx = int(env_idx)
            if idx not in candidate_indices:
                candidate_indices.append(idx)

        open_indices: list[int] = []
        for idx in candidate_indices:
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW if self._is_windows else cv2.CAP_ANY)
            if cap.isOpened():
                open_indices.append(idx)
                cap.release()
            time.sleep(0.02)

        system_names = self._dshow_camera_names() or self._system_camera_names()
        devices: list[CameraDevice] = []
        for pos, idx in enumerate(open_indices):
            if pos < len(system_names):
                name = f"{system_names[pos]} [#{idx}]"
            else:
                name = f"Camera #{idx}"
            devices.append(CameraDevice(index=idx, name=name))

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
            print("[ERROR] No valid camera found after scanning")
            self._last_error = "No valid camera found after scanning"
            return False

        with self._cap_lock:
            self._cap = cap
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()  # type: ignore
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
            print("[ERROR] No valid camera found after scanning")
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
                    time.sleep(0.001)
                    continue
                ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= CAMERA_READ_RETRY_LIMIT:
                    self._last_error = "Camera stream stalled"
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
                        print("[ERROR] No valid camera found after scanning")
                    time.sleep(CAMERA_REOPEN_COOLDOWN_S)
                    continue
                time.sleep(0.01)
                continue

            consecutive_failures = 0
            self.actual_height, self.actual_width = frame.shape[:2]
            with self._frame_lock:
                self._frame = frame
            
            # 🔥 Fix thread loop aggression (recommended to avoid freezing)
            time.sleep(0.005)

    def latest(self):
        with self._frame_lock:
            return self._frame

    def stop(self) -> None:
        self._running = False
        if self._thread is not None and self._thread.is_alive():  # type: ignore
            self._thread.join(timeout=1.5)  # type: ignore
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