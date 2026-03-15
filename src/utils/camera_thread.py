"""Thread-safe camera capture with robust backend/index probing."""

import platform
import threading
import time

import cv2

from config import CAMERA_HEIGHT, CAMERA_INDEX, CAMERA_INDEXES, CAMERA_WIDTH


class CameraThread:
    def __init__(self):
        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._last_error = ""

    def start(self):
        if self._running:
            return True
        self._last_error = ""
        self._cap = self._open()
        if self._cap is None:
            return False
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        with self._lock:
            self._frame = None
        self._last_error = ""

    def get_frame(self):
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    @property
    def is_running(self):
        return self._running

    @property
    def last_error(self):
        return self._last_error

    def _loop(self):
        consecutive_fails = 0
        while self._running:
            try:
                ok, frame = self._cap.read()
            except Exception:
                ok = False
                frame = None
            if ok and frame is not None:
                consecutive_fails = 0
                with self._lock:
                    self._frame = frame
            else:
                consecutive_fails += 1
                if consecutive_fails > 30:
                    # Camera likely disconnected
                    self._last_error = "Camera disconnected or frame capture failed"
                    self._running = False
                    break
                time.sleep(0.01)

    def _open(self):
        last_error = ""
        sys_name = platform.system().lower()
        if sys_name == "darwin":
            backends = [getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY), cv2.CAP_ANY]
        elif sys_name == "windows":
            backends = [getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY), cv2.CAP_ANY]
        else:
            backends = [getattr(cv2, "CAP_V4L2", cv2.CAP_ANY), cv2.CAP_ANY]

        idxs = [CAMERA_INDEX] + [i for i in CAMERA_INDEXES if i != CAMERA_INDEX]

        for be in backends:
            for idx in idxs:
                cap = None
                try:
                    cap = cv2.VideoCapture(idx, be)
                    if cap is None:
                        last_error = f"Failed to create capture for index {idx}"
                        continue

                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

                    if not cap.isOpened():
                        last_error = f"Camera index {idx} not opened"
                        cap.release()
                        continue

                    # Warm-up read to ensure backend/index is actually usable.
                    ok = False
                    for _ in range(12):
                        ok, frame = cap.read()
                        if ok and frame is not None:
                            break
                        time.sleep(0.02)

                    if ok:
                        return cap

                    last_error = (
                        f"Backend {be} opened index {idx} but returned no frames"
                    )
                    cap.release()
                except Exception as exc:
                    last_error = str(exc)
                    if cap is not None:
                        try:
                            cap.release()
                        except Exception:
                            pass
                    continue

        self._last_error = last_error or "Unable to open any camera backend/index"
        return None
