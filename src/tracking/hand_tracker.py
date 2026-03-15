"""MediaPipe hand tracker wrapper."""

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

import cv2
import mediapipe as mp

from config import (
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
)


@dataclass
class HandTrackingResult:
    """Contains image-space landmarks and MediaPipe output for drawing."""

    landmarks: Optional[List[Tuple[int, int]]]
    mp_result: Any


class HandTracker:
    """Detect one hand and convert landmarks to pixel coordinates."""

    def __init__(self) -> None:
        self.mp_hands = mp.solutions.hands
        self.mp_drawing = mp.solutions.drawing_utils
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )

    def process_frame(self, frame_bgr) -> HandTrackingResult:
        """Return 21 (x, y) landmarks for first detected hand."""
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self.hands.process(frame_rgb)

        landmarks: Optional[List[Tuple[int, int]]] = None
        if result.multi_hand_landmarks:
            h, w = frame_bgr.shape[:2]
            first_hand = result.multi_hand_landmarks[0]
            landmarks = [
                (int(lm.x * w), int(lm.y * h))
                for lm in first_hand.landmark
            ]

        return HandTrackingResult(landmarks=landmarks, mp_result=result)

    def draw_landmarks(self, frame_bgr, mp_result: Any) -> None:
        """Draw MediaPipe hand landmarks on frame for debug visualization."""
        if not mp_result or not mp_result.multi_hand_landmarks:
            return

        for hand_lms in mp_result.multi_hand_landmarks:
            self.mp_drawing.draw_landmarks(
                frame_bgr,
                hand_lms,
                self.mp_hands.HAND_CONNECTIONS,
            )

    def close(self) -> None:
        """Release MediaPipe resources."""
        self.hands.close()
