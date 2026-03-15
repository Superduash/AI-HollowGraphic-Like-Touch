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
    lm[17] = (260, 140)      # pinky MCP (for hand scale)
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
    result = None
    for _ in range(4):
        result = detector.detect(lm)
    assert result is not None
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
    """Thumb+index pinch fires a click (edge-triggered)."""
    detector = GestureDetector()
    # Thumb and index very close = pinch
    lm = _landmarks(
        thumb=(100, 100), index=(105, 100),
        index_pip=(160, 120), middle=(220, 150), middle_pip=(220, 100),
        ring=(250, 150), ring_pip=(250, 100),
        pinky=(270, 150), pinky_pip=(270, 100),
        thumb_ip=(90, 110), index_mcp=(150, 130),
    )
    r1 = None
    for _ in range(4):
        r1 = detector.detect(lm)
    assert r1 is not None
    assert r1.gesture == GestureType.LEFT_CLICK


def test_right_click_thumb_middle_pinch() -> None:
    """Thumb + middle pinch with index down -> RIGHT_CLICK after brief hold."""
    detector = GestureDetector()
    lm = _landmarks(
        # Make index "down" to avoid thumb-index pinch triggering left click.
        index=(160, 160), index_pip=(160, 120),
        middle=(220, 100), middle_pip=(220, 120),
        ring=(250, 160), ring_pip=(250, 120),
        pinky=(270, 160), pinky_pip=(270, 120),
        thumb=(222, 102), thumb_ip=(210, 115),
    )
    r1 = None
    for _ in range(4):
        r1 = detector.detect(lm)
    assert r1 is not None
    assert r1.gesture in {GestureType.RIGHT_CLICK, GestureType.MOVE, GestureType.PAUSE}
    r2 = detector.detect(lm)
    assert r2.gesture == GestureType.RIGHT_CLICK


def test_task_view_open_palm() -> None:
    detector = GestureDetector()
    lm = _landmarks(
        thumb=(50, 80), thumb_ip=(90, 110),
        index=(160, 50), index_pip=(160, 100),
        middle=(220, 50), middle_pip=(220, 100),
        ring=(250, 50), ring_pip=(250, 100),
        pinky=(270, 50), pinky_pip=(270, 100),
    )
    result = None
    # Task View requires a sustained open palm for stability.
    for _ in range(6):
        result = detector.detect(lm)
    assert result is not None
    assert result.gesture == GestureType.TASK_VIEW


def test_scroll_peace_sign() -> None:
    detector = GestureDetector()
    # Index + middle up, ring + pinky down => SCROLL mode.
    lm = _landmarks(
        index=(160, 50), index_pip=(160, 100),
        middle=(220, 50), middle_pip=(220, 100),
        ring=(250, 160), ring_pip=(250, 120),
        pinky=(270, 160), pinky_pip=(270, 120),
        thumb=(100, 130), thumb_ip=(90, 110),
    )
    r1 = None
    for _ in range(4):
        r1 = detector.detect(lm)
    assert r1 is not None
    assert r1.gesture == GestureType.SCROLL
    # Move tips upward to produce a scroll delta.
    lm2 = _landmarks(
        index=(160, 40), index_pip=(160, 100),
        middle=(220, 40), middle_pip=(220, 100),
        ring=(250, 160), ring_pip=(250, 120),
        pinky=(270, 160), pinky_pip=(270, 120),
        thumb=(100, 130), thumb_ip=(90, 110),
    )
    r2 = detector.detect(lm2)
    assert r2.gesture == GestureType.SCROLL
    assert isinstance(r2.scroll_delta, int)
