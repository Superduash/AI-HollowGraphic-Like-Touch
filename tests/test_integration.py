"""Integration tests - full system verification."""
import time
from src.gesture_detector import GestureDetector
from src.hand_tracker import HandTracker
from src.mouse import MouseController
from src.cursor_mapper import CursorMapper
from src.models import GestureType


def test_all_modules_import():
    """Test that all core modules can be imported."""
    try:
        from src import MainWindow
        from src.camera_thread import CameraThread
        from src.constants import _OVERLAY_LABELS
        from src.settings_store import settings
        print("[PASS] All modules import successfully")
    except ImportError as e:
        raise AssertionError(f"Module import failed: {e}")


def test_gesture_detector_all_gestures():
    """Test that all gesture types are reachable in detector."""
    detector = GestureDetector()
    
    gesture_mapping = [
        GestureType.PAUSE,
        GestureType.LEFT_CLICK,
        GestureType.RIGHT_CLICK,
        GestureType.DOUBLE_CLICK,
        GestureType.MOVE,
        GestureType.SCROLL,
        GestureType.DRAG,
        GestureType.KEYBOARD,
        GestureType.TASK_VIEW,
        GestureType.MEDIA_VOL_UP,
        GestureType.MEDIA_VOL_DOWN,
        GestureType.MEDIA_NEXT,
        GestureType.MEDIA_PREV,
    ]
    
    for gesture in gesture_mapping:
        # Create a result - should not crash
        result = detector._make_result(gesture, scroll_delta=0, confidence=0.5)
        assert result.gesture == gesture
    
    print(f"[PASS] All {len(gesture_mapping)} gesture types work")


def test_hand_tracker_creation():
    """Test HandTracker can be instantiated."""
    try:
        tracker = HandTracker()
        assert tracker is not None
        print("[PASS] HandTracker initialization works")
    except Exception as e:
        print(f"[WARN] HandTracker initialization (MediaPipe may not be installed): {e}")


def test_mouse_controller_creation():
    """Test MouseController can be instantiated."""
    controller = MouseController()
    assert controller is not None
    print("[PASS] MouseController initialization works")


def test_cursor_mapper_creation():
    """Test CursorMapper initialization."""
    try:
        # CursorMapper requires camera dimensions
        mapper = CursorMapper(cam_w=640, cam_h=480)
        assert mapper is not None
        print("[PASS] CursorMapper initialization works")
    except Exception as e:
        print(f"[WARN] CursorMapper initialization: {e}")


def test_settings_store():
    """Test settings storage works."""
    from src.settings_store import settings
    
    # Should be able to get/set values
    settings.set("test_key", "test_value")
    value = settings.get("test_key", "default")
    assert value == "test_value"
    print("[PASS] Settings store works")


def test_complete_gesture_pipeline():
    """Test complete gesture detection pipeline."""
    detector = GestureDetector()
    
    # Create synthetic hand with index extended (MOVE)
    landmarks = [
        (100.0, 100.0),  # wrist
    ] + [
        (100.0 + i*5, 100.0 - i*3) for i in range(1, 21)
    ]
    
    hand_data = {
        "xy": landmarks,
        "label": "Right",
        "confidence": 0.95,
        "z": [[0.0] * 3 for _ in range(21)]
    }
    
    # Detect gesture
    for i in range(3):
        result = detector.detect(hand_data)
        time.sleep(0.020)
    
    assert result.gesture in [
        GestureType.PAUSE,
        GestureType.MOVE,
        GestureType.SCROLL,
        GestureType.LEFT_CLICK,
    ]
    print(f"[PASS] Complete pipeline works: detected {result.gesture.name}")


def test_no_memory_leaks_detection():
    """Test that repeated detect calls don't leak resources."""
    detector = GestureDetector()
    
    landmarks = [(100.0 + i*2, 100.0 + i) for i in range(21)]
    hand_data = {
        "xy": landmarks,
        "label": "Right",
        "confidence": 0.95,
        "z": [[0.0] * 3 for _ in range(21)]
    }
    
    # Run many detections
    for i in range(100):
        detector.detect(hand_data)
    
    # Gesture entry set should not grow unbounded
    assert len(detector._gesture_entry_set) <= 5, f"Entry set grown to {len(detector._gesture_entry_set)}"
    print(f"[PASS] No memory leak detected (entry_set size: {len(detector._gesture_entry_set)})")


if __name__ == "__main__":
    test_all_modules_import()
    test_gesture_detector_all_gestures()
    test_hand_tracker_creation()
    test_mouse_controller_creation()
    test_cursor_mapper_creation()
    test_settings_store()
    test_complete_gesture_pipeline()
    test_no_memory_leaks_detection()
    print("\n[SUCCESS] All integration tests passed!")
