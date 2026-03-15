"""
main.py - AI Holographic Touch: entry point.

Captures webcam frames, detects hand landmarks, interprets gestures, and
drives the mouse cursor in real time.  Press **Q** while the preview window
is focused to quit cleanly.

Usage::

    python main.py

The preview window shows:
  * Live webcam feed with hand-skeleton overlay
  * FPS counter (top-left)
  * Gesture status bar (bottom-left): pinch distances and active click events
"""

import sys
import cv2
import pyautogui

from hand_tracker     import HandTracker
from gesture_detector import GestureDetector
from mouse_controller import MouseController
from utils            import EMAFilter, FPSCounter, map_coordinates


# ---------------------------------------------------------------------------
# Configuration – tweak these to match your hardware / preferences
# ---------------------------------------------------------------------------

# Webcam device index (0 = built-in / default camera)
CAMERA_INDEX = 0

# Capture resolution; 640×480 is a good balance of accuracy and performance
CAPTURE_WIDTH  = 640
CAPTURE_HEIGHT = 480

# EMA smoothing factor: lower = smoother but laggier (range 0 < α ≤ 1)
SMOOTHING_ALPHA = 0.25

# Pinch-to-click sensitivity: fraction of the frame diagonal
# Increase to make the gesture easier to trigger; decrease for more precision
PINCH_THRESHOLD_RATIO = 0.07

# Minimum seconds between consecutive clicks of the same type
CLICK_COOLDOWN = 0.5

# Fraction of the frame edge to crop as "dead zone" so the cursor can
# comfortably reach screen corners without extreme hand positions
COORDINATE_MARGIN = 0.05

# Window title for the preview feed
WINDOW_TITLE = "AI Holographic Touch – press Q to quit"


# ---------------------------------------------------------------------------
# Overlay drawing helpers
# ---------------------------------------------------------------------------

def _draw_fps(frame, fps):
    """Render the FPS counter in the top-left corner of *frame*."""
    cv2.putText(
        frame,
        f"FPS: {fps:.1f}",
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


def _draw_status(frame, result, frame_h):
    """
    Render a one-line status bar near the bottom of *frame*.

    Shows:
      * Left pinch distance vs threshold (turns red when active)
      * Right pinch distance vs threshold (turns red when active)
      * "LEFT CLICK" / "RIGHT CLICK" labels when clicks fire
    """
    y = frame_h - 15  # position just above the bottom edge

    # --- Left pinch indicator ---
    left_active = result.pinch_dist_left < result.pinch_threshold
    left_colour = (0, 0, 255) if left_active else (200, 200, 200)
    cv2.putText(
        frame,
        f"L-pinch: {result.pinch_dist_left:.0f}/{result.pinch_threshold:.0f}",
        (10, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        left_colour,
        1,
        cv2.LINE_AA,
    )

    # --- Right pinch indicator ---
    right_active = result.pinch_dist_right < result.pinch_threshold
    right_colour = (0, 0, 255) if right_active else (200, 200, 200)
    cv2.putText(
        frame,
        f"R-pinch: {result.pinch_dist_right:.0f}/{result.pinch_threshold:.0f}",
        (250, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        right_colour,
        1,
        cv2.LINE_AA,
    )

    # --- Click event flash ---
    if result.left_click:
        cv2.putText(
            frame, "LEFT CLICK", (10, y - 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA,
        )
    if result.right_click:
        cv2.putText(
            frame, "RIGHT CLICK", (250, y - 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2, cv2.LINE_AA,
        )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main():
    # --- Initialise subsystems ---
    tracker  = HandTracker(
        max_hands=1,
        detection_confidence=0.7,
        tracking_confidence=0.5,
    )
    detector = GestureDetector(
        pinch_threshold_ratio=PINCH_THRESHOLD_RATIO,
        click_cooldown=CLICK_COOLDOWN,
    )
    mouse    = MouseController()
    smoother = EMAFilter(alpha=SMOOTHING_ALPHA)
    fps_ctr  = FPSCounter(window=30)

    # Retrieve screen dimensions once for coordinate mapping
    screen_w, screen_h = pyautogui.size()

    # --- Open webcam ---
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print(
            f"[ERROR] Cannot open camera at index {CAMERA_INDEX}. "
            "Check that a webcam is connected and not used by another app.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Request the desired capture resolution from the driver
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

    # Read back the actual resolution (the driver may not honour the request)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[INFO] Camera opened at {actual_w}×{actual_h}")
    print(f"[INFO] Screen resolution: {screen_w}×{screen_h}")
    print("[INFO] Hold your hand in front of the camera.")
    print("[INFO]   • Move index finger  → move cursor")
    print("[INFO]   • Pinch thumb+index  → left click")
    print("[INFO]   • Pinch thumb+middle → right click")
    print("[INFO] Press Q in the preview window to quit.")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[WARNING] Dropped frame – skipping.", file=sys.stderr)
                continue

            # Mirror the frame horizontally so the view matches a mirror –
            # moving your right hand moves the cursor to the right on screen.
            frame = cv2.flip(frame, 1)

            # Detect landmarks and draw skeleton overlay on *frame* in-place
            landmarks = tracker.process(frame)

            if landmarks:
                # Interpret gestures from landmarks
                result = detector.detect(landmarks, actual_w, actual_h)

                # Map index finger tip from webcam space → screen space
                raw_sx, raw_sy = map_coordinates(
                    result.cursor_x, result.cursor_y,
                    actual_w, actual_h,
                    screen_w, screen_h,
                    margin=COORDINATE_MARGIN,
                )

                # Apply EMA smoothing to suppress jitter
                sx, sy = smoother.update(raw_sx, raw_sy)
                sx, sy = int(sx), int(sy)

                # Execute mouse actions
                mouse.handle_gesture(
                    sx, sy,
                    left_click=result.left_click,
                    right_click=result.right_click,
                )

                # Draw gesture status bar
                _draw_status(frame, result, actual_h)
            else:
                # No hand detected – reset smoother so the cursor doesn't
                # slide back in from the last known position next time.
                smoother.reset()

            # Draw FPS counter
            fps = fps_ctr.tick()
            _draw_fps(frame, fps)

            # Show preview window
            cv2.imshow(WINDOW_TITLE, frame)

            # Quit on Q key (waitKey returns the ASCII code)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                print("[INFO] Quit requested – shutting down.")
                break

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted – shutting down.")
    finally:
        cap.release()
        cv2.destroyAllWindows()
        tracker.release()


if __name__ == "__main__":
    main()
