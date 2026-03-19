import cv2
import platform


def backend_list():
    if platform.system() == "Windows":
        return [cv2.CAP_MSMF, cv2.CAP_DSHOW, cv2.CAP_ANY]
    return [cv2.CAP_ANY]


def backend_name(backend):
    if backend == cv2.CAP_MSMF:
        return "MSMF"
    if backend == cv2.CAP_DSHOW:
        return "DSHOW"
    if backend == cv2.CAP_ANY:
        return "ANY"
    return str(backend)


def test_cameras():
    backends = backend_list()

    working_indexes = []

    for i in range(10):
        found = False
        for backend in backends:
            print(f"Testing index {i} with backend {backend_name(backend)}...")
            cap = cv2.VideoCapture(i, backend)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret and frame is not None:
                    print(f"  [SUCCESS] Index {i} works ({backend_name(backend)})")
                    working_indexes.append((i, backend))
                    found = True
                    cap.release()
                    break
                print(f"  [FAIL] Index {i} opened but failed to read frame.")
            else:
                print(f"  [FAIL] Index {i} failed to open.")
            cap.release()
        if not found:
            print(f"  [FAIL] Index {i} unavailable on all backends")

    for i in working_indexes:
        idx, backend = i
        print(f"\nTesting constraints on working index {idx} ({backend_name(backend)})...")
        cap = cv2.VideoCapture(idx, backend)

        if platform.system() == "Windows":
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 60)

        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                if platform.system() == "Windows":
                    fourcc = int(cap.get(cv2.CAP_PROP_FOURCC) or 0)
                    mjpg_ok = fourcc == cv2.VideoWriter_fourcc(*"MJPG")
                    if mjpg_ok:
                        print(f"  [SUCCESS] Index {idx} works with MJPG and 60 FPS constraints.")
                    else:
                        print(f"  [WARN] Index {idx} works but rejected MJPG (fallback format active).")
                else:
                    print(f"  [SUCCESS] Index {idx} works with 60 FPS constraints.")
            else:
                print(f"  [FAIL] Index {idx} fails when constrained.")
        cap.release()

if __name__ == "__main__":
    test_cameras()
