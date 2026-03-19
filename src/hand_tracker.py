from __future__ import annotations

import cv2

from .utils import _ensure_mediapipe_solutions

try:
    import mediapipe as mp  # type: ignore
except Exception:
    mp = None  # type: ignore[assignment]

DrawingSpec = None
if mp is not None:
    DrawingSpec = mp.solutions.drawing_utils.DrawingSpec  # type: ignore[attr-defined]


class HandTracker:
    def __init__(self) -> None:

        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
        self._draw = mp.solutions.drawing_utils  # type: ignore[attr-defined]
        self._styles = mp.solutions.drawing_styles  # type: ignore[attr-defined]

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.45,
            min_tracking_confidence=0.45,
        )

    def detect(self, frame_bgr):
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        if not result.multi_hand_landmarks or not result.multi_handedness:
            return None, None

        hand = result.multi_hand_landmarks[0]
        label = result.multi_handedness[0].classification[0].label

        confidence = result.multi_handedness[0].classification[0].score
        xy = [(int(lm.x * w), int(lm.y * h)) for lm in hand.landmark]
        z = [float(lm.z) for lm in hand.landmark]
        return {
            "xy": xy,
            "z": z,
            "label": label,
            "confidence": confidence,
            "frame_size": (w, h),
        }, hand

    def draw(self, frame_rgb, hand_proto, label: str = "Right") -> None:
        if hand_proto is None:
            return

        if label == "Right":
            conn_color = (0, 255, 0)
        else:
            conn_color = (255, 255, 0)

        conn_spec = DrawingSpec(color=conn_color, thickness=3, circle_radius=1) if DrawingSpec is not None else None
        lmk_spec = self._styles.get_default_hand_landmarks_style()

        self._draw.draw_landmarks(
            frame_rgb,
            hand_proto,
            self._mp_hands.HAND_CONNECTIONS,
            lmk_spec,
            conn_spec,
        )

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
                del self._hands
        except Exception:
            pass