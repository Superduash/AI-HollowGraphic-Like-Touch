"""Helpers to extract specific landmarks from 21-point hand data."""

from typing import List, Optional, Tuple


Landmark = Tuple[int, int]

THUMB_TIP_ID = 4
INDEX_TIP_ID = 8
MIDDLE_TIP_ID = 12


def get_landmark(landmarks: Optional[List[Landmark]], index: int) -> Optional[Landmark]:
    """Safely fetch a landmark by index."""
    if landmarks is None:
        return None
    if index < 0 or index >= len(landmarks):
        return None
    return landmarks[index]


def get_index_tip(landmarks: Optional[List[Landmark]]) -> Optional[Landmark]:
    return get_landmark(landmarks, INDEX_TIP_ID)


def get_thumb_tip(landmarks: Optional[List[Landmark]]) -> Optional[Landmark]:
    return get_landmark(landmarks, THUMB_TIP_ID)


def get_middle_tip(landmarks: Optional[List[Landmark]]) -> Optional[Landmark]:
    return get_landmark(landmarks, MIDDLE_TIP_ID)
