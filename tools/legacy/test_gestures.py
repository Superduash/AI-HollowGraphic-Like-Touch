#!/usr/bin/env python3
"""Gesture Detection Test & Debug Tool."""

import sys
import time
sys.path.insert(0, '.')

from src.gesture_detector import GestureDetector, FingerStates
from src.models import GestureType

def test_gesture_detections():
    """Test all gesture detection paths."""
    detector = GestureDetector()
    
    # Simulate hand data
    def make_hand(xy, label="Right", confidence=0.9):
        return {
            "xy": xy,
            "z": [0.0] * 21,
            "label": label,
            "confidence": confidence,
        }
    
    # MediaPipe hand landmarks (right hand):
    # 0: wrist, 1-4: thumb, 5-8: index, 9-12: middle, 13-16: ring, 17-20: pinky
    
    print("=" * 60)
    print("GESTURE DETECTION TEST")
    print("=" * 60)
    
    # Test 1: Pointer upright (MOVE gesture)
    print("\n[TEST 1] Index extended only = MOVE gesture")
    detector = GestureDetector()
    # Right hand with index pointing up, other fingers curled IN TOWARD PALM
    hand_xy = [
        (250, 400),  # 0: wrist
        (220, 390), (200, 370), (190, 350), (180, 340),  # 1-4: thumb (tucked into palm)
        (280, 350), (300, 300), (315, 200), (320, 120),  # 5-8: index (EXTENDED UP)
        (290, 390), (300, 400), (305, 395), (306, 392),  # 9-12: middle (CURLED - tip very close to MCP)
        (280, 390), (285, 400), (288, 395), (289, 392),  # 13-16: ring (CURLED - tip very close to MCP)
        (270, 390), (270, 400), (271, 395), (271, 392),  # 17-20: pinky (CURLED - tip very close to MCP)
    ]
    
    hand = make_hand(hand_xy)
    for _ in range(5):
        result = detector.detect(hand)
        time.sleep(0.020)  # 20ms per frame = ~50 fps
    print(f"   Expected: MOVE, Got: {result.gesture}")
    
    # Debug finger states
    fs = detector._finger_states(hand_xy)
    print(f"   Finger states: thumb={fs.thumb}, index={fs.index}, middle={fs.middle}, ring={fs.ring}, pinky={fs.pinky}")
    print(f"   Hand scale: {detector._hand_scale:.1f}")
    print(f"   Pose checks: move={fs.index and (not fs.middle) and (not fs.ring) and (not fs.pinky)}")
    
    # Test 2: Thumb-Index pinch (LEFT_CLICK)
    print("\n[TEST 2] Thumb-Index pinch = LEFT_CLICK gesture")
    detector = GestureDetector()
    # Thumb and index tips VERY close together (pinch) - < 30% of hand scale
    hand_xy = [
        (250, 400),  # 0: wrist
        (260, 350), (265, 330), (268, 310), (270, 295),  # 1-4: thumb tip
        (280, 350), (290, 330), (300, 310), (278, 295),  # 5-8: index tip (VERY CLOSE to thumb ~8px)
        (290, 360), (300, 380), (305, 375), (306, 372),  # 9-12: middle (CURLED - tip close to MCP)
        (280, 365), (285, 380), (288, 375), (289, 372),  # 13-16: ring (CURLED - tip close to MCP)
        (270, 370), (270, 385), (271, 380), (271, 377),  # 17-20: pinky (CURLED - tip close to MCP)
    ]
    
    hand = make_hand(hand_xy)
    for i in range(5):
        result = detector.detect(hand)
        print(f"   Frame {i+1}: gesture={result.gesture}, state={detector._state}, cand={detector._candidate}")
        time.sleep(0.020)  # 20ms per frame = ~50 fps
    print(f"   Expected: LEFT_CLICK, Got: {result.gesture}")
    
    # Debug
    fs = detector._finger_states(hand_xy)
    print(f"   Finger states: thumb={fs.thumb}, index={fs.index}, middle={fs.middle}, ring={fs.ring}, pinky={fs.pinky}")
    print(f"   Pinch states: left={detector._left_pinch_active}, right={detector._right_pinch_active}")
    
    # Test 3: Index + Middle extended (SCROLL)
    print("\n[TEST 3] Index + Middle extended = SCROLL gesture")
    detector = GestureDetector()
    hand_xy = [
        (250, 400),  # 0: wrist
        (220, 380), (200, 350), (190, 300), (180, 270),  # 1-4: thumb (tucked)
        (280, 350), (300, 300), (315, 200), (320, 120),  # 5-8: index (EXTENDED)
        (290, 350), (310, 300), (325, 200), (330, 120),  # 9-12: middle (EXTENDED)
        (280, 365), (285, 380), (288, 375), (289, 372),  # 13-16: ring (CURLED - tip close to MCP)
        (270, 370), (270, 385), (271, 380), (271, 377),  # 17-20: pinky (CURLED - tip close to MCP)
    ]
    
    hand = make_hand(hand_xy)
    for _ in range(5):
        result = detector.detect(hand)
        time.sleep(0.020)  # 20ms per frame = ~50 fps
    print(f"   Expected: SCROLL, Got: {result.gesture}")
    if result.gesture == GestureType.SCROLL:
        print("   ✓ PASS")
    else:
        print(f"   ⚠ Got {result.gesture} instead")
    
    print("\n" + "=" * 60)
    print("✅ Gesture detection test complete!")
    print("=" * 60)
    
if __name__ == "__main__":
    try:
        test_gesture_detections()
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        result = detector.detect(hand)
        time.sleep(0.020)
    print(f"   Expected: RIGHT_CLICK, Got: {result.gesture}")
    if result.gesture == GestureType.RIGHT_CLICK:
        print("   [PASS]")
    else:
        print(f"   [FAIL] Expected RIGHT_CLICK")

    print("\n" + "=" * 60)
    print("Gesture detection test complete!")
    print("=" * 60)
    
if __name__ == "__main__":
    try:
        test_gesture_detections()
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR]: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
