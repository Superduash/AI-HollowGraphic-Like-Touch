from __future__ import annotations

import cv2

from .utils import _ensure_mediapipe_solutions

try:
    import mediapipe as mp  # type: ignore
except Exception:
    mp = None  # type: ignore[assignment]


class HandTracker:
    def __init__(self, process_w: int = 320, process_h: int = 240) -> None:
        self.process_w = process_w
        self.process_h = process_h

        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
        self._draw = mp.solutions.drawing_utils  # type: ignore[attr-defined]

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.35,
            min_tracking_confidence=0.35,
        )

    def detect(self, frame_bgr):
        small = cv2.resize(frame_bgr, (self.process_w, self.process_h), interpolation=cv2.INTER_NEAREST)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        if not result.multi_hand_landmarks or not result.multi_handedness:
            return None, None

        hand = result.multi_hand_landmarks[0]
        label = result.multi_handedness[0].classification[0].label

        # Mirror correction for selfie-style camera feed.
        corrected_label = "Right" if label == "Left" else "Left"
        xy = [(int(lm.x * self.process_w), int(lm.y * self.process_h)) for lm in hand.landmark]
        z = [float(lm.z) for lm in hand.landmark]
        return {"xy": xy, "z": z, "label": corrected_label}, hand

    def draw(self, frame_rgb, hand_proto, label: str = "Right") -> None:
        if hand_proto is None:
            return

        # Right hand -> bright green, left hand -> cyan.
        color = (0, 255, 0) if label == "Right" else (0, 255, 255)
        lm_spec = self._draw.DrawingSpec(color=color, thickness=2, circle_radius=2)
        conn_spec = self._draw.DrawingSpec(color=color, thickness=2)
        self._draw.draw_landmarks(
            frame_rgb,
            hand_proto,
            self._mp_hands.HAND_CONNECTIONS,
            lm_spec,
            conn_spec,
        )

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
                del self._hands
        except Exception:
            pass