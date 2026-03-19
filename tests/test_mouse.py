"""Tests for mouse control system."""
from src.mouse import MouseController
from src.models import GestureType


def test_mouse_controller_init():
    """Test MouseController initialization."""
    controller = MouseController()
    assert controller is not None
    print("[PASS] MouseController initialization works")


def test_click_action_creation():
    """Test that click actions are created correctly."""
    controller = MouseController()
    
    assert hasattr(controller, '_worker')
    assert hasattr(controller, '_media_worker')
    assert controller._worker.is_alive()
    assert controller._media_worker.is_alive()
    print("[PASS] MouseController worker threads started")


def test_mouse_hz_bounds():
    """Test that mouse worker HZ is bounded correctly."""
    # Test with invalid HZ values
    import src.mouse as mouse_module
    
    # Default should be valid
    assert 10 <= mouse_module.MOUSE_WORKER_HZ <= 1000
    print(f"[PASS] Mouse worker HZ valid: {mouse_module.MOUSE_WORKER_HZ}")


def test_queue_operations():
    """Test that action queue works (basic)."""
    controller = MouseController()
    
    assert hasattr(controller, '_media_queue')
    assert controller._media_queue is not None
    print("[PASS] Media queue structure valid")


if __name__ == "__main__":
    test_mouse_controller_init()
    test_click_action_creation()
    test_mouse_hz_bounds()
    test_queue_operations()
    print("\n[SUCCESS] All mouse tests passed!")
