#!/usr/bin/env python3
"""Quick test script for camera enumeration and detection."""

import sys
sys.path.insert(0, '.')

from src.camera_thread import CameraThread

def test_enumeration():
    print("=" * 60)
    print(" CAMERA ENUMERATION TEST")
    print("=" * 60)
    
    cam = CameraThread(640, 480)
    
    # Test enumeration
    print("\n[1] Enumerating cameras...")
    devices = cam.enumerate_cameras(max_index=8)
    
    if not devices:
        print("   ❌ NO CAMERAS FOUND")
        return False
    
    print(f"   ✓ Found {len(devices)} camera(s):")
    for dev in devices:
        print(f"     - Index {dev.index}: {dev.name}")
    
    # Test find_working_camera
    print("\n[2] Testing find_working_camera (auto-scan)...")
    result = cam.find_working_camera(preferred_index=None, min_index=0, max_index=5)
    
    if result is None:
        print("   ❌ No working camera found")
        print(f"   Error: {cam.last_error}")
        return False
    
    idx, backend, cap = result
    print(f"   ✓ Found working camera:")
    print(f"     - Index: {idx}")
    print(f"     - Backend: {cam._backend_name(backend)}")
    print(f"     - Resolution: {cam.actual_width}x{cam.actual_height}")
    
    if cap:
        cap.release()
    
    # Test actual startup
    print("\n[3] Testing camera startup...")
    success = cam.start(camera_index=idx)
    
    if not success:
        print("   ❌ Failed to start camera")
        print(f"   Error: {cam.last_error}")
        return False
    
    print(f"   ✓ Camera started successfully")
    print(f"   Resolution: {cam.actual_width}x{cam.actual_height}")
    
    # Read a frame
    import time
    print("\n[4] Reading first frame...")
    time.sleep(0.5)
    frame = cam.latest()
    
    if frame is None:
        print("   ⚠ No frame yet (give it a moment...)")
    else:
        print(f"   ✓ Frame received: {frame.shape}")
    
    cam.stop()
    print("\n" + "=" * 60)
    print(" ✓ ALL TESTS PASSED")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_enumeration()
    sys.exit(0 if success else 1)
