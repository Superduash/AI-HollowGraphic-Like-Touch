"""Tests for the gesture detection engine."""

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from gestures.gesture_detector import GestureDetector, GestureResult
from gestures.gesture_types import GestureType
from tracking.landmark_processor import get_finger_states


def _landmarks(thumb=(100, 100), index=(160, 60), middle=(220, 60),
               ring=(250, 100), pinky=(270, 100),
               thumb_ip=(90, 110), index_pip=(160, 100),
               middle_pip=(220, 100), ring_pip=(250, 110),
               pinky_pip=(270, 110), index_mcp=(150, 130)):
    """Build a 21-landmark list with key landmarks positioned as given."""
    lm = [(0, 0)] * 21
    lm[0] = (130, 200)     # wrist
    lm[3] = thumb_ip        # thumb IP
    lm[4] = thumb            # thumb tip
    lm[5] = index_mcp        # index MCP
    lm[6] = index_pip        # index PIP
    lm[8] = index            # index tip
    lm[10] = middle_pip      # middle PIP
    lm[12] = middle          # middle tip
    lm[14] = ring_pip        # ring PIP
    lm[16] = ring            # ring tip
    lm[18] = pinky_pip       # pinky PIP
    lm[20] = pinky           # pinky tip
    return lm


# ---- Finger state detection ----

def test_finger_states_all_up() -> None:
    lm = _landmarks(
        thumb=(50, 80), thumb_ip=(90, 110), index_mcp=(150, 130),
        index=(160, 50), index_pip=(160, 100),
        middle=(220, 50), middle_pip=(220, 100),
        ring=(250, 50), ring_pip=(250, 100),
        pinky=(270, 50), pinky_pip=(270, 100),
    )
    fs = get_finger_states(lm)
    assert fs.index and fs.middle and fs.ring and fs.pinky


def test_finger_states_all_down() -> None:
    lm = _landmarks(
        thumb=(100, 130), thumb_ip=(90, 110), index_mcp=(150, 130),
        index=(160, 150), index_pip=(160, 100),
        middle=(220, 150), middle_pip=(220, 100),
        ring=(250, 150), ring_pip=(250, 100),
        pinky=(270, 150), pinky_pip=(270, 100),
    )
    fs = get_finger_states(lm)
    assert not fs.index and not fs.middle and not fs.ring and not fs.pinky


# ---- Gesture detection ----

def test_move_gesture() -> None:
    """Index up, others down → MOVE."""
    detector = GestureDetector()
    lm = _landmarks(
        index=(160, 50), index_pip=(160, 100),      # index UP
        middle=(220, 150), middle_pip=(220, 100),    # middle DOWN
        ring=(250, 150), ring_pip=(250, 100),        # ring DOWN
        pinky=(270, 150), pinky_pip=(270, 100),      # pinky DOWN
        thumb=(100, 130), thumb_ip=(90, 110),        # thumb (don't care)
    )
    result = detector.detect(lm)
    assert result.gesture == GestureType.MOVE


def test_pause_gesture() -> None:
    """All fingers down → PAUSE."""
    detector = GestureDetector()
    lm = _landmarks(
        index=(160, 150), index_pip=(160, 100),
        middle=(220, 150), middle_pip=(220, 100),
        ring=(250, 150), ring_pip=(250, 100),
        pinky=(270, 150), pinky_pip=(270, 100),
        thumb=(100, 130), thumb_ip=(90, 110),
    )
    result = detector.detect(lm)
    assert result.gesture == GestureType.PAUSE


def test_left_click_requires_stability() -> None:
    """Pinch must persist for GESTURE_STABILITY_FRAMES before firing click."""
    detector = GestureDetector()
    # Thumb and index very close = pinch
    lm = _landmarks(
        thumb=(100, 100), index=(105, 100),
        index_pip=(160, 120), middle=(220, 150), middle_pip=(220, 100),
        ring=(250, 150), ring_pip=(250, 100),
        pinky=(270, 150), pinky_pip=(270, 100),
        thumb_ip=(90, 110), index_mcp=(150, 130),
    )
    # First call — not yet stable
    r1 = detector.detect(lm)
    # Second call — should trigger click (stability_frames=2)
    r2 = detector.detect(lm)
    assert r2.gesture == GestureType.LEFT_CLICK


def test_right_click_two_fingers() -> None:
    """Index + middle up, ring + pinky down → RIGHT_CLICK after stability."""
    detector = GestureDetector()
    lm = _landmarks(
        index=(160, 50), index_pip=(160, 100),       # UP
        middle=(220, 50), middle_pip=(220, 100),      # UP
        ring=(250, 150), ring_pip=(250, 100),         # DOWN
        pinky=(270, 150), pinky_pip=(270, 100),       # DOWN
        thumb=(100, 130), thumb_ip=(90, 110),
    )
    # Call enough times for stability + decision
    result = None
    for _ in range(5):
        result = detector.detect(lm)
        if result.gesture == GestureType.RIGHT_CLICK:
            break
    assert result.gesture == GestureType.RIGHT_CLICK
