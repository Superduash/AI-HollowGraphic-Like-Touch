"""Basic tests for pinch gesture detection."""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType


def _build_landmarks(thumb=(100, 100), index=(160, 100), middle=(220, 100)):
    # Build a 21-landmark list with only needed landmarks set.
    landmarks = [(0, 0)] * 21
    landmarks[4] = thumb
    landmarks[8] = index
    landmarks[12] = middle
    return landmarks


def test_detect_left_click_pinch() -> None:
    detector = GestureDetector(left_pinch_threshold=40, right_pinch_threshold=40)
    landmarks = _build_landmarks(thumb=(100, 100), index=(120, 100), middle=(200, 100))

    result = detector.detect(landmarks)

    assert result.gesture == GestureType.LEFT_CLICK


def test_detect_right_click_pinch() -> None:
    detector = GestureDetector(left_pinch_threshold=30, right_pinch_threshold=40)
    landmarks = _build_landmarks(thumb=(100, 100), index=(170, 100), middle=(130, 100))

    result = detector.detect(landmarks)

    assert result.gesture == GestureType.RIGHT_CLICK


def test_detect_move_cursor_when_no_pinch() -> None:
    detector = GestureDetector(left_pinch_threshold=30, right_pinch_threshold=30)
    landmarks = _build_landmarks(thumb=(100, 100), index=(180, 100), middle=(220, 100))

    result = detector.detect(landmarks)

    assert result.gesture == GestureType.MOVE_CURSOR
