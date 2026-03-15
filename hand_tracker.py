"""
hand_tracker.py - MediaPipe-based hand landmark detector.

Wraps the MediaPipe Hands solution so the rest of the application only needs
to call HandTracker.process(frame) and receive a plain list of (x, y) pixel
coordinates for each detected landmark.
"""

import cv2
import mediapipe as mp


# MediaPipe landmark index constants for easy readability
WRIST           = 0
THUMB_TIP       = 4
INDEX_TIP       = 8
MIDDLE_TIP      = 12
RING_TIP        = 16
PINKY_TIP       = 20

# All 21 landmark indices (0-20) – useful if the caller wants the full set
ALL_LANDMARKS   = list(range(21))


class HandTracker:
    """
    Detects hand landmarks in a single BGR video frame using MediaPipe Hands.

    Example usage::

        tracker = HandTracker()
        landmarks = tracker.process(frame)   # list of (x, y) or None
        tracker.release()
    """

    def __init__(
        self,
        max_hands=1,
        detection_confidence=0.7,
        tracking_confidence=0.5,
    ):
        """
        Initialise the MediaPipe Hands pipeline.

        Args:
            max_hands (int): Maximum number of hands to detect (default 1).
            detection_confidence (float): Minimum confidence for hand
                detection to be considered successful (0–1).
            tracking_confidence (float): Minimum confidence for hand
                landmarks to be considered tracked in subsequent frames (0–1).
        """
        self._mp_hands = mp.solutions.hands
        self._mp_drawing = mp.solutions.drawing_utils
        self._mp_drawing_styles = mp.solutions.drawing_styles

        # Initialise the Hands solution context
        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=max_hands,
            min_detection_confidence=detection_confidence,
            min_tracking_confidence=tracking_confidence,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame):
        """
        Run hand landmark detection on *frame* and draw results in-place.

        The frame is converted to RGB internally before passing to MediaPipe;
        the original BGR frame is annotated with the skeleton overlay.

        Args:
            frame (numpy.ndarray): BGR image from OpenCV VideoCapture.

        Returns:
            list[tuple[int, int]] | None:
                A list of 21 (x, y) pixel coordinates, one per landmark,
                for the **first** detected hand.  Returns *None* when no
                hand is visible.
        """
        h, w = frame.shape[:2]

        # MediaPipe expects RGB; avoid a permanent colour-space change by
        # converting a view rather than modifying the original frame.
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Disable writeable flag for a small performance gain (no copy)
        rgb.flags.writeable = False
        results = self._hands.process(rgb)
        rgb.flags.writeable = True

        if not results.multi_hand_landmarks:
            return None

        # Use the first detected hand
        hand_landmarks = results.multi_hand_landmarks[0]

        # Draw the skeleton on the original BGR frame for visual feedback
        self._mp_drawing.draw_landmarks(
            frame,
            hand_landmarks,
            self._mp_hands.HAND_CONNECTIONS,
            self._mp_drawing_styles.get_default_hand_landmarks_style(),
            self._mp_drawing_styles.get_default_hand_connections_style(),
        )

        # Convert normalised [0,1] coordinates to pixel coordinates
        landmarks = [
            (int(lm.x * w), int(lm.y * h))
            for lm in hand_landmarks.landmark
        ]
        return landmarks

    def release(self):
        """Release MediaPipe resources."""
        self._hands.close()
