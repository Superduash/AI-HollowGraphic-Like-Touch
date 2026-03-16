import cv2
import platform

def test_cameras():
    backend = cv2.CAP_MSMF if platform.system() == "Windows" else cv2.CAP_ANY
    print(f"Using backend: {'MSMF' if backend == cv2.CAP_MSMF else 'ANY'}")
    
    working_indexes = []
    
    for i in range(10):
        print(f"Testing index {i} without constraints...")
        cap = cv2.VideoCapture(i, backend)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"  [SUCCESS] Index {i} works (Vanilla)")
                working_indexes.append(i)
            else:
                print(f"  [FAIL] Index {i} opened but failed to read frame.")
        else:
            print(f"  [FAIL] Index {i} failed to open.")
        cap.release()
        
    for i in working_indexes:
        print(f"\nTesting constraints on working index {i}...")
        cap = cv2.VideoCapture(i, backend)
        
        # Test MJPG constraint
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 60)
        
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                print(f"  [SUCCESS] Index {i} works with MJPG and 60 FPS constraints.")
            else:
                print(f"  [FAIL] Index {i} fails when constrained to MJPG or 60 FPS.")
        cap.release()

if __name__ == "__main__":
    test_cameras()
