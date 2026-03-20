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
        self._last_results = None  # FIX: cache results so draw() can use them

        if not _OK or mp is None:
            print("[FACE] MediaPipe face_mesh unavailable — head tracking disabled")
            return
        try:
            self._mesh = mp.solutions.face_mesh.FaceMesh(  # type: ignore
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
            self._last_results = res  # FIX: cache so draw() can render the skeleton

            if not res.multi_face_landmarks:
                self._init = False
                return None
            lm = res.multi_face_landmarks[0].landmark[self.NOSE_TIP]
            rx, ry = lm.x * w, lm.y * h
            if not self._init:
                self._nose_x, self._nose_y = rx, ry
                self._init = True
            else:
                # FIX: reduced deadzone from 1.5 → 0.5px so micro-movements register
                # CursorMapper handles all smoothing — we just need raw movement here
                dx = rx - self._nose_x
                dy = ry - self._nose_y
                if abs(dx) >= 0.5:
                    self._nose_x = rx
                if abs(dy) >= 0.5:
                    self._nose_y = ry
            return int(self._nose_x), int(self._nose_y)
        except Exception:
            return None

    def draw(self, frame_rgb) -> None:
        """FIX: Draw face mesh skeleton + nose tip dot on the given RGB frame.
        Call this from _render() right after the control region rectangle is drawn.
        """
        if not self.available or self._mesh is None:
            return
        if not _OK or mp is None:
            return
        if self._last_results is None:
            return
        try:
            res = self._last_results
            if not res.multi_face_landmarks:
                return

            mp_drawing = mp.solutions.drawing_utils  # type: ignore
            mp_face_mesh = mp.solutions.face_mesh  # type: ignore

            # Subtle grey lines so the skeleton is visible but not blinding
            spec = mp_drawing.DrawingSpec(color=(120, 120, 120), thickness=1, circle_radius=1)

            for face_landmarks in res.multi_face_landmarks:
                mp_drawing.draw_landmarks(
                    image=frame_rgb,
                    landmark_list=face_landmarks,
                    connections=mp_face_mesh.FACEMESH_TESSELATION,
                    landmark_drawing_spec=None,
                    connection_drawing_spec=spec,
                )
                # Bright cyan dot on the exact nose tip that drives the cursor
                nose = face_landmarks.landmark[self.NOSE_TIP]
                nx = int(nose.x * frame_rgb.shape[1])
                ny = int(nose.y * frame_rgb.shape[0])
                cv2.circle(frame_rgb, (nx, ny), 7, (0, 255, 255), -1)
                cv2.circle(frame_rgb, (nx, ny), 9, (0, 180, 180), 2)  # outer ring
        except Exception:
            pass

    def close(self) -> None:
        try:
            if self._mesh is not None:
                self._mesh.close()
        except Exception:
            pass
