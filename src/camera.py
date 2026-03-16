import platform
import threading
import time

import cv2


class CameraSource:
    def __init__(self, width: int = 640, height: int = 480) -> None:
        self.width = width
        self.height = height
        self._cap: cv2.VideoCapture | None = None
        self._running = False
        self._thread = None
        self._frame = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        if self._running:
            return True

        indexes = list(range(10))  # Increase indexes to find Droidcam
        backend = cv2.CAP_ANY

        for idx in indexes:
            cap = cv2.VideoCapture(idx, backend)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            ok = False
            for _ in range(10):
                r, f = cap.read()
                if r and f is not None:
                    ok = True
                    break
                time.sleep(0.02)

            if ok:
                self._cap = cap
                self._running = True
                self._thread = threading.Thread(target=self._loop, daemon=True)
                self._thread.start()
                return True

            cap.release()

        return False

    def _loop(self) -> None:
        while self._running:
            cap = self._cap
            if cap is None:
                time.sleep(0.005)
                continue
            ok, frame = cap.read()
            if not ok or frame is None:
                time.sleep(0.005)
                continue
            with self._lock:
                self._frame = frame

    def latest(self):
        with self._lock:
            if self._frame is None:
                return None
            return self._frame

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        with self._lock:
            self._frame = None
