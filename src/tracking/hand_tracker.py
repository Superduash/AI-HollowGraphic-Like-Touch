"""MediaPipe hand tracker — optimized with error handling and debug overlay."""

import cv2
import mediapipe as mp
from config import (
    MAX_NUM_HANDS,
    MIN_DETECTION_CONFIDENCE,
    MIN_TRACKING_CONFIDENCE,
    PROCESS_HEIGHT,
    PROCESS_WIDTH,
)

_CONNECTIONS = [
    (0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
    (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
    (13,17),(17,18),(18,19),(19,20),(0,17),
]

# Pre-compute target size tuple once
_PROC_SIZE = (PROCESS_WIDTH, PROCESS_HEIGHT)


class HandTracker:
    def __init__(self):
        self._mp_hands = mp.solutions.hands
        self._draw_utils = mp.solutions.drawing_utils
        self._draw_styles = mp.solutions.drawing_styles
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self._pw = PROCESS_WIDTH
        self._ph = PROCESS_HEIGHT
        self._landmark_style = self._draw_styles.get_default_hand_landmarks_style()
        self._connection_style = self._draw_styles.get_default_hand_connections_style()

    def process_frame(self, frame_bgr):
        """Resize to 320x240, run MediaPipe, return (landmarks_list, hand_landmarks_proto)."""
        try:
            small = cv2.resize(frame_bgr, _PROC_SIZE, interpolation=cv2.INTER_NEAREST)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            result = self._hands.process(rgb)
        except Exception:
            return None, None
        if not result.multi_hand_landmarks:
            return None, None
        hand = result.multi_hand_landmarks[0]
        pw, ph = self._pw, self._ph
        pts = [(int(lm.x * pw), int(lm.y * ph)) for lm in hand.landmark]
        return pts, hand

    def draw_landmarks(self, frame_bgr, hand_landmarks):
        """Draw landmarks and connections onto full frame using mp.drawing_utils."""
        if not hand_landmarks:
            return
        self._draw_utils.draw_landmarks(
            frame_bgr,
            hand_landmarks,
            self._mp_hands.HAND_CONNECTIONS,
            self._landmark_style,
            self._connection_style,
        )

    def close(self):
        try:
            self._hands.close()
        except Exception:
            pass
