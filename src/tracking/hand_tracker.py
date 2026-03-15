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
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=MAX_NUM_HANDS,
            min_detection_confidence=MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        )
        self._pw = PROCESS_WIDTH
        self._ph = PROCESS_HEIGHT

    def process_frame(self, frame_bgr):
        """Resize to 320×240, run MediaPipe, return 21 landmarks or None."""
        try:
            small = cv2.resize(frame_bgr, _PROC_SIZE, interpolation=cv2.INTER_NEAREST)
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
            result = self._hands.process(rgb)
        except Exception:
            return None
        if not result.multi_hand_landmarks:
            return None
        hand = result.multi_hand_landmarks[0]
        pw, ph = self._pw, self._ph
        return [(int(lm.x * pw), int(lm.y * ph)) for lm in hand.landmark]

    def draw_debug(self, frame_bgr, landmarks):
        """Draw landmark overlay on full frame from cached coords. No reprocessing."""
        if not landmarks:
            return
        h, w = frame_bgr.shape[:2]
        sx, sy = w / self._pw, h / self._ph
        pts = [(int(lm[0] * sx), int(lm[1] * sy)) for lm in landmarks]
        for i, j in _CONNECTIONS:
            if i < len(pts) and j < len(pts):
                cv2.line(frame_bgr, pts[i], pts[j], (0, 255, 0), 1)
        for pt in pts:
            cv2.circle(frame_bgr, pt, 3, (0, 255, 0), -1)

    def close(self):
        try:
            self._hands.close()
        except Exception:
            pass
