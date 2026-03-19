"""Tests for data models and enums."""
from src.models import GestureType, FingerStates, GestureResult


def test_gesture_type_enum():
    """Test GestureType enum has all required gesture types."""
    required_gestures = {
        'PAUSE', 'MOVE', 'LEFT_CLICK', 'RIGHT_CLICK', 'DOUBLE_CLICK',
        'SCROLL', 'DRAG', 'KEYBOARD', 'TASK_VIEW',
        'MEDIA_VOL_UP', 'MEDIA_VOL_DOWN', 'MEDIA_NEXT', 'MEDIA_PREV'
    }
    available_gestures = {g.name for g in GestureType}
    assert required_gestures.issubset(available_gestures), f"Missing gestures: {required_gestures - available_gestures}"
    print(f"[PASS] GestureType has all {len(required_gestures)} required gestures")


def test_gesture_result():
    """Test GestureResult creation and properties."""
    result = GestureResult(GestureType.LEFT_CLICK, scroll_delta=0)
    assert result.gesture == GestureType.LEFT_CLICK
    assert result.scroll_delta == 0
    print(f"[PASS] GestureResult creation works")
    
    # Test scroll result
    scroll_result = GestureResult(GestureType.SCROLL, scroll_delta=5)
    assert scroll_result.scroll_delta == 5
    print(f"[PASS] GestureResult scroll_delta assignment works")


def test_finger_states():
    """Test FingerStates dataclass."""
    fs = FingerStates(thumb=True, index=True, middle=False, ring=False, pinky=False)
    assert fs.thumb is True
    assert fs.index is True
    assert fs.middle is False
    assert fs.ring is False
    assert fs.pinky is False
    print(f"[PASS] FingerStates creation works")
    
    # Test with all extended
    fs_all = FingerStates(True, True, True, True, True)
    extended_count = sum([fs_all.thumb, fs_all.index, fs_all.middle, fs_all.ring, fs_all.pinky])
    assert extended_count == 5
    print(f"[PASS] FingerStates all extended case works")


if __name__ == "__main__":
    test_gesture_type_enum()
    test_gesture_result()
    test_finger_states()
    print("\n[SUCCESS] All model tests passed!")
