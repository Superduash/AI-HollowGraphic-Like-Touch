"""Entry point for AI-HollowGraphic-Like-Touch."""

import platform

import cv2
import pyautogui

from config import (
    CAMERA_HEIGHT,
    CAMERA_INDEX,
    CAMERA_INDEXES,
    CAMERA_WIDTH,
    SMOOTHING_ALPHA,
    SMOOTHING_WINDOW,
    WINDOW_NAME,
)
from controller.cursor_mapper import CursorMapper
from controller.mouse_controller import MouseController
from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType
from tracking.hand_tracker import HandTracker
from tracking.landmark_processor import get_index_tip
from utils.fps_counter import FPSCounter
from utils.smoothing import CursorSmoother


def _get_capture_backends() -> list[int]:
    """Return preferred OpenCV capture backends for this operating system."""
    system_name = platform.system().lower()
    if system_name == "darwin":
        backends = [getattr(cv2, "CAP_AVFOUNDATION", cv2.CAP_ANY), cv2.CAP_ANY]
    elif system_name == "windows":
        backends = [getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY), cv2.CAP_ANY]
    else:
        backends = [getattr(cv2, "CAP_V4L2", cv2.CAP_ANY), cv2.CAP_ANY]

    unique_backends: list[int] = []
    for backend in backends:
        if backend not in unique_backends:
            unique_backends.append(backend)
    return unique_backends


def _open_camera_with_fallback() -> tuple[cv2.VideoCapture | None, int | None, int | None]:
    """Try multiple camera indexes/backends and return the first working capture."""
    indexes = [CAMERA_INDEX]
    for extra_index in CAMERA_INDEXES:
        if extra_index not in indexes:
            indexes.append(extra_index)

    for backend in _get_capture_backends():
        for index in indexes:
            cap = cv2.VideoCapture(index, backend)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

            if cap.isOpened():
                return cap, index, backend
            cap.release()

    return None, None, None


def run() -> None:
    """Run the webcam loop and control the mouse from hand gestures."""
    cap, active_camera_index, active_backend = _open_camera_with_fallback()

    if cap is None:
        print("Error: Could not open webcam with any configured camera index.")
        print(f"Tried indexes: {[CAMERA_INDEX] + [i for i in CAMERA_INDEXES if i != CAMERA_INDEX]}")
        if platform.system().lower() == "darwin":
            print("On macOS, allow Camera access for Terminal/IDE in System Settings > Privacy & Security > Camera.")
        return

    mouse_init_warning = ""
    try:
        screen_width, screen_height = pyautogui.size()
    except Exception as error:
        # Keep app running for preview/debug even when OS blocks automation APIs.
        screen_width, screen_height = 1920, 1080
        mouse_init_warning = f"Mouse API warning: {error}"

    hand_tracker = HandTracker()
    gesture_detector = GestureDetector()
    mouse_controller = MouseController()
    if mouse_init_warning:
        mouse_controller.is_available = False
        mouse_controller.last_error_message = mouse_init_warning
    cursor_mapper = CursorMapper(CAMERA_WIDTH, CAMERA_HEIGHT, screen_width, screen_height)
    smoother = CursorSmoother(window_size=SMOOTHING_WINDOW, alpha=SMOOTHING_ALPHA)
    fps_counter = FPSCounter()

    while True:
        success, frame = cap.read()
        if not success:
            break

        frame = cv2.flip(frame, 1)
        tracking_result = hand_tracker.process_frame(frame)
        hand_tracker.draw_landmarks(frame, tracking_result.mp_result)

        gesture_state_text = GestureType.NONE.value
        if tracking_result.landmarks:
            index_tip = get_index_tip(tracking_result.landmarks)
            if index_tip:
                target_x, target_y = cursor_mapper.map_to_screen(index_tip[0], index_tip[1])
                smooth_x, smooth_y = smoother.smooth(target_x, target_y)
                mouse_controller.move_cursor(smooth_x, smooth_y)
                cv2.circle(frame, index_tip, 10, (255, 0, 0), cv2.FILLED)

            gesture_state = gesture_detector.detect(tracking_result.landmarks)
            gesture_state_text = gesture_state.gesture.value

            if gesture_state.gesture == GestureType.LEFT_CLICK:
                clicked = mouse_controller.left_click()
                if clicked:
                    cv2.putText(frame, "LEFT CLICK", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
            elif gesture_state.gesture == GestureType.RIGHT_CLICK:
                clicked = mouse_controller.right_click()
                if clicked:
                    cv2.putText(frame, "RIGHT CLICK", (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)

            if gesture_state.thumb_index_distance is not None:
                cv2.putText(
                    frame,
                    f"Thumb-Index: {gesture_state.thumb_index_distance:.1f}",
                    (10, 140),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
            if gesture_state.thumb_middle_distance is not None:
                cv2.putText(
                    frame,
                    f"Thumb-Middle: {gesture_state.thumb_middle_distance:.1f}",
                    (10, 165),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )

        fps = fps_counter.update()
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.putText(
            frame,
            f"Camera: idx={active_camera_index} backend={active_backend}",
            (10, 55),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (180, 180, 180),
            1,
        )
        cv2.putText(frame, f"Gesture: {gesture_state_text}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, "Press q to quit", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        if not mouse_controller.is_available:
            cv2.putText(
                frame,
                "Mouse control unavailable: grant Accessibility permission",
                (10, 190),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 255),
                2,
            )

        cv2.imshow(WINDOW_NAME, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    hand_tracker.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
