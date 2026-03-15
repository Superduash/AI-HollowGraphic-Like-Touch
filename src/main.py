"""Entry point for AI-HollowGraphic-Like-Touch."""

import cv2
import pyautogui

from config import CAMERA_HEIGHT, CAMERA_INDEX, CAMERA_WIDTH, SMOOTHING_ALPHA, SMOOTHING_WINDOW, WINDOW_NAME
from controller.cursor_mapper import CursorMapper
from controller.mouse_controller import MouseController
from gestures.gesture_detector import GestureDetector
from gestures.gesture_types import GestureType
from tracking.hand_tracker import HandTracker
from tracking.landmark_processor import get_index_tip
from utils.fps_counter import FPSCounter
from utils.smoothing import CursorSmoother


def run() -> None:
    """Run the webcam loop and control the mouse from hand gestures."""
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    if not cap.isOpened():
        print("Error: Could not open webcam.")
        return

    screen_width, screen_height = pyautogui.size()

    hand_tracker = HandTracker()
    gesture_detector = GestureDetector()
    mouse_controller = MouseController()
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
        cv2.putText(frame, f"Gesture: {gesture_state_text}", (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
        cv2.putText(frame, "Press q to quit", (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200, 200, 200), 2)

        cv2.imshow(WINDOW_NAME, frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    hand_tracker.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run()
