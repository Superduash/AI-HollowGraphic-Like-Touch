"""Nose-tip cursor tracker using MediaPipe Face Mesh.

Nose tip (landmark 1) is the most stable facial point for cursor
control — large target, fine motor control, zero arm fatigue.
"""
from __future__ import annotations

import cv2

try:
    import mediapipe as mp  # type: ignore
    _OK = hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh")
except Exception:
    mp = None  # type: ignore
    _OK = False


class FaceTracker:
    NOSE_TIP = 1  # Face Mesh landmark index

    def __init__(self) -> None:
        self._mesh = None
        self._nose_x = -1.0
        self._nose_y = -1.0
        self._init = False
        self._alpha = 0.50   # EMA — raise for faster response, lower for smoother
        self.available = False

        if not _OK or mp is None:
            print("[FACE] MediaPipe face_mesh unavailable — head tracking disabled")
            return
        try:
            self._mesh = mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.4,
            )
            self.available = True
            print("[FACE] Face Mesh ready — nose tip cursor active")
        except Exception as e:
            print(f"[FACE] Face Mesh init failed: {e}")

    def detect(self, frame_bgr) -> tuple[int, int] | None:
        """Return smoothed (cam_x, cam_y) of nose tip, or None."""
        if not self.available or self._mesh is None:
            return None
        try:
            h, w = frame_bgr.shape[:2]
            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            res = self._mesh.process(rgb)
            if not res.multi_face_landmarks:
                self._init = False
                return None
            lm = res.multi_face_landmarks[0].landmark[self.NOSE_TIP]
            rx, ry = lm.x * w, lm.y * h
            if not self._init:
                self._nose_x, self._nose_y = rx, ry
                self._init = True
            else:
                dx = rx - self._nose_x
                dy = ry - self._nose_y
                if abs(dx) < 1.5: dx = 0.0
                if abs(dy) < 1.5: dy = 0.0
                a = self._alpha
                self._nose_x += a * dx
                self._nose_y += a * dy
            return int(self._nose_x), int(self._nose_y)
        except Exception:
            return None

    def close(self) -> None:
        try:
            if self._mesh is not None:
                self._mesh.close()
        except Exception:
            pass
