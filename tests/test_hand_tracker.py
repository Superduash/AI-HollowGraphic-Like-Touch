"""Unit tests for hand tracker label mapping (mirror vs non-mirror)."""

from src.hand_tracker import HandTracker


def test_map_label_non_mirrored_passthrough() -> None:
    assert HandTracker._map_label("Right", is_mirrored=False) == "Right"
    assert HandTracker._map_label("Left", is_mirrored=False) == "Left"


def test_map_label_mirrored_inverts() -> None:
    assert HandTracker._map_label("Right", is_mirrored=True) == "Left"
    assert HandTracker._map_label("Left", is_mirrored=True) == "Right"


def test_map_label_unknown_passthrough() -> None:
    assert HandTracker._map_label("Unknown", is_mirrored=False) == "Unknown"
    assert HandTracker._map_label("Unknown", is_mirrored=True) == "Unknown"


if __name__ == "__main__":
    test_map_label_non_mirrored_passthrough()
    test_map_label_mirrored_inverts()
    test_map_label_unknown_passthrough()
    print("[SUCCESS] All hand tracker tests passed!")
