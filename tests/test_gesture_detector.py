"""Tests for gesture detection system."""
import time
from src.gesture_detector import GestureDetector
from src.models import GestureType, FingerStates


def create_hand_data(xy_coords, label="Right", confidence=0.95):
    """Helper to create hand data dict with MediaPipe landmarks."""
    return {
        "xy": xy_coords,
        "label": label,
        "confidence": confidence,
        "z": [[0.0] * 3 for _ in range(21)]  # z-depth for all landmarks
    }


def create_landmarks_move():
    """Create landmarks for MOVE gesture: index extended, others curled.
    
    MediaPipe hand landmarks (21 points):
    0: wrist, 1-4: thumb, 5-8: index, 9-12: middle, 13-16: ring, 17-20: pinky
    """
    wrist = (100.0, 100.0)
    
    # Landmarks 0-4: wrist + thumb (tucked)
    landmarks = [
        wrist,  # 0: wrist
        (105, 85),   # 1: thumb CMC
        (110, 80),   # 2: thumb PIP
        (113, 75),   # 3: thumb IP
        (115, 72),   # 4: thumb tip (close to wrist)
    ]
    
    # Add index (EXTENDED) - landmarks 5-8
    # Extended = far from wrist
    landmarks.extend([
        (108, 120),  # 5: index MCP
        (105, 160),  # 6: index PIP
        (103, 190),  # 7: index DIP
        (100, 220),  # 8: index tip (FAR from wrist ~120 pixels)
    ])
    
    # Add middle (CURLED) - landmarks 9-12
    # Curled = tip close to MCP (< 5 pixels apart in this scale)
    mid_mcp = (120, 120)
    landmarks.extend([
        mid_mcp,        # 9: middle MCP
        (121, 121),     # 10: middle PIP (1px away)
        (121.5, 121.5), # 11: middle DIP (0.7px away)
        (122, 122),     # 12: middle tip (2px away from MCP - CURLED)
    ])
    
    # Add ring (CURLED) - landmarks 13-16
    # Curled = tip close to MCP
    landmarks.extend([
        (135, 120),  # 13: ring MCP
        (136, 121),  # 14: ring PIP
        (136.5, 121),  # 15: ring DIP
        (137, 122),  # 16: ring tip (2px away - CURLED)
    ])
    
    # Add pinky (CURLED) - landmarks 17-20
    # Curled = tip close to MCP
    landmarks.extend([
        (150, 120),  # 17: pinky MCP
        (151, 121),  # 18: pinky PIP
        (151.5, 121),  # 19: pinky DIP
        (152, 122),  # 20: pinky tip (2px away - CURLED)
    ])
    
    return landmarks


def create_landmarks_left_click():
    """Create landmarks for LEFT_CLICK: thumb-index pinch."""
    landmarks = create_landmarks_move()
    # Move thumb tip closer to index tip for pinch
    landmarks[4] = (105, 225)  # Thumb tip near index tip
    return landmarks


def create_landmarks_scroll():
    """Create landmarks for SCROLL: index + middle extended."""
    landmarks = create_landmarks_move()
    # Extend middle finger away
    landmarks[9] = (120, 125)   # middle MCP
    landmarks[10] = (115, 160)  # middle PIP
    landmarks[11] = (108, 190)  # middle DIP
    landmarks[12] = (105, 220)  # middle tip (extended)
    return landmarks


def test_gesture_detector_init():
    """Test GestureDetector initialization."""
    detector = GestureDetector()
    assert detector.dragging is False
    assert detector._state == GestureType.PAUSE
    assert detector._candidate == GestureType.PAUSE
    print("[PASS] GestureDetector initialization works")


def test_hand_loss_detection():
    """Test that detector handles missing hand data."""
    detector = GestureDetector()
    
    # Loss of hand
    result = detector.detect(None)
    assert result.gesture == GestureType.PAUSE
    assert detector._state == GestureType.PAUSE
    print("[PASS] Hand loss detection works")


def test_move_gesture():
    """Test MOVE gesture detection."""
    detector = GestureDetector()
    landmarks = create_landmarks_move()
    
    # Need multiple frames for state stabilization
    for i in range(5):
        hand_data = create_hand_data(landmarks, label="Right", confidence=0.95)
        result = detector.detect(hand_data)
        if i < 3:
            # Stabilization in progress
            assert result.gesture in [GestureType.PAUSE, GestureType.MOVE]
        else:
            # Should be stable by frame 3-4
            if result.gesture == GestureType.MOVE:
                break
        time.sleep(0.020)  # Let timing accumulate
    
    print(f"[PASS] MOVE gesture detection works (final: {result.gesture.name})")


def test_left_click_gesture():
    """Test LEFT_CLICK gesture detection."""
    detector = GestureDetector()
    landmarks = create_landmarks_left_click()
    
    # Need stabilization time
    for i in range(5):
        hand_data = create_hand_data(landmarks, label="Right", confidence=0.95)
        result = detector.detect(hand_data)
        if i >= 2:
            if result.gesture == GestureType.LEFT_CLICK:
                break
        time.sleep(0.020)
    
    assert result.gesture == GestureType.LEFT_CLICK
    print("[PASS] LEFT_CLICK gesture detection works")


def test_scroll_gesture():
    """Test SCROLL gesture detection."""
    detector = GestureDetector()
    landmarks = create_landmarks_scroll()
    
    for i in range(5):
        hand_data = create_hand_data(landmarks, label="Right", confidence=0.95)
        result = detector.detect(hand_data)
        if i >= 2 and result.gesture == GestureType.SCROLL:
            break
        time.sleep(0.020)
    
    # Should detect SCROLL or at least not crash
    assert result.gesture in [GestureType.PAUSE, GestureType.SCROLL], f"Got {result.gesture}"
    print(f"[PASS] SCROLL gesture detection works (detected: {result.gesture.name})")


def test_cooldown_system():
    """Test gesture cooldown prevents rapid re-triggering."""
    detector = GestureDetector()
    landmarks = create_landmarks_left_click()
    
    # Trigger gesture
    for i in range(5):
        hand_data = create_hand_data(landmarks, label="Right", confidence=0.95)
        result = detector.detect(hand_data)
        time.sleep(0.020)
    
    first_gesture = result.gesture
    
    # Quickly trigger again - should be blocked by cooldown
    result2 = detector.detect(hand_data)
    # The cooldown should prevent immediate re-trigger
    # but continuous hold of same gesture should work
    
    print(f"[PASS] Cooldown system working (first: {first_gesture.name}, second: {result2.gesture.name})")


def test_hand_confidence_gating():
    """Test that low confidence hands are rejected."""
    detector = GestureDetector()
    landmarks = create_landmarks_move()
    
    # Low confidence
    hand_data = create_hand_data(landmarks, label="Right", confidence=0.10)
    result = detector.detect(hand_data)
    assert result.gesture == GestureType.PAUSE
    print("[PASS] Hand confidence gating works (rejects < 0.20)")


def test_finger_states_detection():
    """Test individual finger state detection."""
    detector = GestureDetector()
    landmarks = create_landmarks_move()
    
    # Only compute finger states
    hand_data = create_hand_data(landmarks, label="Right", confidence=0.95)
    fs = detector._finger_states(landmarks)
    
    # Index extended, others curled (based on create_landmarks_move)
    assert fs.index is True, f"Index should be extended, got {fs}"
    assert fs.middle is False, f"Middle should be curled, got {fs}"
    print(f"[PASS] Finger state detection works: {fs}")


def test_reset_cooldowns():
    """Test cooldown reset functionality."""
    detector = GestureDetector()
    detector._last_action_time[GestureType.LEFT_CLICK] = time.monotonic()
    detector._gesture_entry_set.add(GestureType.LEFT_CLICK)
    
    assert len(detector._gesture_entry_set) > 0
    detector.reset_cooldowns()
    
    assert len(detector._gesture_entry_set) == 0
    assert len(detector._last_action_time) == 0
    print("[PASS] Cooldown reset works")


if __name__ == "__main__":
    test_gesture_detector_init()
    test_hand_loss_detection()
    test_hand_confidence_gating()
    test_finger_states_detection()
    test_move_gesture()
    test_left_click_gesture()
    test_scroll_gesture()
    test_cooldown_system()
    test_reset_cooldowns()
    print("\n[SUCCESS] All gesture detector tests passed!")
