from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import cv2

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

        self._cap: cv2.VideoCapture | None = None
        self._frame = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._cap_lock = threading.Lock()
        self._frame_lock = threading.Lock()

    @staticmethod
    def _configure_capture(cap: cv2.VideoCapture, width: int, height: int) -> None:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def _open_capture(self, camera_index: int) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(int(camera_index), cv2.CAP_DSHOW)
        self._configure_capture(cap, self.width, self.height)

        for _ in range(12):
            ok, frame = cap.read()
            if ok and frame is not None:
                return cap
            time.sleep(0.02)

        cap.release()
        return None

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

    def enumerate_cameras(self, max_index: int = 10) -> list[CameraDevice]:
        open_indices: list[int] = []
        for idx in range(max_index):
            cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            try:
                self._configure_capture(cap, self.width, self.height)
                ok = cap.isOpened()
                if ok:
                    read_ok, frame = cap.read()
                    ok = bool(read_ok and frame is not None)
                if ok:
                    open_indices.append(idx)
            finally:
                cap.release()

        system_names = self._system_camera_names()
        devices: list[CameraDevice] = []
        for pos, idx in enumerate(open_indices):
            if pos < len(system_names):
                name = system_names[pos]
            else:
                name = f"Camera {idx}"
            devices.append(CameraDevice(index=idx, name=name))

        if not devices:
            devices.append(CameraDevice(index=0, name="Camera 0"))
        return devices

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

        # Hard release before re-init to avoid stale DirectShow handles.
        with self._cap_lock:
            old_cap = self._cap
            self._cap = None
        if old_cap is not None:
            try:
                old_cap.release()
            except Exception:
                pass

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