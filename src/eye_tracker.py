"""Iris-based cursor tracker using MediaPipe Face Mesh (experimental).

Uses refine_landmarks=True to access iris landmarks 468/473.
GAIN amplifies tiny eye movements so user doesn't need to move their whole head.
"""
from __future__ import annotations

import cv2

try:
    import mediapipe as mp
    _OK = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
except Exception:
    mp = None
    _OK = False


class EyeTracker:
    LEFT_IRIS = 468
    RIGHT_IRIS = 473

    def __init__(self, gain: float = 1.8) -> None:
        self._mesh = None
        self._eye_x = -1.0
        self._eye_y = -1.0
        self._init = False
        self.available = False
        self._last_results = None
        self._gain = max(1.0, min(3.0, gain))

        if not _OK or mp is None:
            return
        try:
            self._mesh = mp.solutions.face_mesh.FaceMesh( # type: ignore
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.4,
            )
            self.available = True
            print("[EYE] Iris tracker ready (experimental)")
        except Exception:
            pass

    def detect(self, frame_bgr) -> tuple[int, int] | None:
        if not self.available or self._mesh is None:
            return None
        try:
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self._mesh.process(rgb)
            self._last_results = res

            if not res.multi_face_landmarks:
                self._init = False
                return None

            face = res.multi_face_landmarks[0]
            l_iris = face.landmark[self.LEFT_IRIS]
            r_iris = face.landmark[self.RIGHT_IRIS]

            # Average both irises for stability
            rx = ((l_iris.x + r_iris.x) / 2.0) * w
            ry = ((l_iris.y + r_iris.y) / 2.0) * h

            # Apply gain: amplify movement from center
            cx, cy = w / 2.0, h / 2.0
            rx = cx + (rx - cx) * self._gain
            ry = cy + (ry - cy) * self._gain

            if not self._init:
                self._eye_x, self._eye_y = rx, ry
                self._init = True
            else:
                # 1.2px deadzone kills webcam micro-jitter
                if abs(rx - self._eye_x) >= 1.2:
                    self._eye_x = rx
                if abs(ry - self._eye_y) >= 1.2:
                    self._eye_y = ry

            return int(self._eye_x), int(self._eye_y)
        except Exception:
            return None

    def draw(self, frame_rgb) -> None:
        if not self.available or self._last_results is None:
            return
        try:
            res = self._last_results
            if not res.multi_face_landmarks:
                return
            face = res.multi_face_landmarks[0]
            h, w = frame_rgb.shape[:2]
            for iris_idx in (self.LEFT_IRIS, self.RIGHT_IRIS):
                pt = face.landmark[iris_idx]
                cv2.circle(frame_rgb, (int(pt.x * w), int(pt.y * h)), 4, (0, 255, 255), -1)
        except Exception:
            pass

    def close(self) -> None:
        if self._mesh is not None:
            try:
                self._mesh.close()
            except Exception:
                pass
