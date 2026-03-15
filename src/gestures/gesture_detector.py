"""Gesture detection logic for pinch-based mouse clicks."""

from dataclasses import dataclass
from typing import List, Tuple

from config import LEFT_CLICK_PINCH_THRESHOLD, RIGHT_CLICK_PINCH_THRESHOLD
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_index_tip, get_middle_tip, get_thumb_tip
from utils.math_utils import distance_between_points


@dataclass
class GestureState:
    """Detected gesture and optional debug distances."""

    gesture: GestureType
    thumb_index_distance: float | None = None
    thumb_middle_distance: float | None = None


class GestureDetector:
    """Detect movement and pinch gestures from hand landmarks."""

    def __init__(
        self,
        left_pinch_threshold: float = LEFT_CLICK_PINCH_THRESHOLD,
        right_pinch_threshold: float = RIGHT_CLICK_PINCH_THRESHOLD,
    ) -> None:
        self.left_pinch_threshold = left_pinch_threshold
        self.right_pinch_threshold = right_pinch_threshold

    def detect(self, landmarks: List[Tuple[int, int]] | None) -> GestureState:
        """Return the current gesture from the 21-point hand landmarks."""
        if not landmarks or len(landmarks) < 13:
            return GestureState(gesture=GestureType.NONE)

        thumb_tip = get_thumb_tip(landmarks)
        index_tip = get_index_tip(landmarks)
        middle_tip = get_middle_tip(landmarks)

        if not thumb_tip or not index_tip or not middle_tip:
            return GestureState(gesture=GestureType.NONE)

        thumb_index_distance = distance_between_points(thumb_tip, index_tip)
        thumb_middle_distance = distance_between_points(thumb_tip, middle_tip)

        if thumb_index_distance <= self.left_pinch_threshold:
            return GestureState(
                gesture=GestureType.LEFT_CLICK,
                thumb_index_distance=thumb_index_distance,
                thumb_middle_distance=thumb_middle_distance,
            )

        if thumb_middle_distance <= self.right_pinch_threshold:
            return GestureState(
                gesture=GestureType.RIGHT_CLICK,
                thumb_index_distance=thumb_index_distance,
                thumb_middle_distance=thumb_middle_distance,
            )

        return GestureState(
            gesture=GestureType.MOVE_CURSOR,
            thumb_index_distance=thumb_index_distance,
            thumb_middle_distance=thumb_middle_distance,
        )
