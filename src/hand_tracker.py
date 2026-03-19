from __future__ import annotations

from collections import deque

import cv2  # type: ignore

from .tuning import HAND_LABEL_MAJORITY_RATIO, HAND_LOCK_CONFIDENCE_THRESHOLD, HAND_LOCKED_DROP_THRESHOLD  # type: ignore
from .utils import _ensure_mediapipe_solutions  # type: ignore

try:
    import mediapipe as mp  # type: ignore
except Exception:
    mp = None  # type: ignore[assignment]

DrawingSpec = None
if mp is not None:
    DrawingSpec = mp.solutions.drawing_utils.DrawingSpec  # type: ignore[attr-defined]


class HandTracker:
    def __init__(self) -> None:
        self._process_size: tuple[int, int] | None = None
        self._label_history: deque[str] = deque(maxlen=9)
        self._stable_label = "Right"
        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
        self._draw = mp.solutions.drawing_utils  # type: ignore[attr-defined]
        self._styles = mp.solutions.drawing_styles  # type: ignore[attr-defined]

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._frames_no_hand = 0
        self._grace_frames = 4
        self._last_valid_result: tuple[dict, object] | None = None

        self._hand_lock_frames = 0
        self._hand_locked = False
        self._low_conf_drop_frames = 0

    def set_processing_size(self, size: tuple[int, int] | None) -> None:
        if size is None:
            self._process_size = None
            return
        w, h = size
        self._process_size = (max(64, int(w)), max(64, int(h)))

    def _resolve_label(self, label: str) -> str:
        self._label_history.append(label)
        history = list(self._label_history)
        total = len(history)
        threshold = max(6, int(total * HAND_LABEL_MAJORITY_RATIO))

        right_count = history.count("Right")
        left_count = history.count("Left")

        if right_count >= threshold:
            self._stable_label = "Right"
        elif left_count >= threshold:
            self._stable_label = "Left"

        return self._stable_label

    def _passes_confidence_gate(self, confidence: float) -> bool:
        if self._hand_locked:
            if confidence < HAND_LOCKED_DROP_THRESHOLD:
                self._low_conf_drop_frames += 1
            else:
                self._low_conf_drop_frames = 0

            if self._low_conf_drop_frames >= 5:
                self._hand_locked = False
                self._hand_lock_frames = 0
                self._low_conf_drop_frames = 0
                return False
            return True

        if confidence >= HAND_LOCK_CONFIDENCE_THRESHOLD:
            self._hand_lock_frames += 1
            if self._hand_lock_frames >= 3:
                self._hand_locked = True
                self._low_conf_drop_frames = 0
            return True

        self._hand_lock_frames = 0
        return False

    def detect(self, frame_bgr, is_mirrored: bool = False):
        src_h, src_w = frame_bgr.shape[:2]

        detect_frame = frame_bgr
        if self._process_size is not None:
            detect_frame = cv2.resize(frame_bgr, self._process_size, interpolation=cv2.INTER_LINEAR)

        h, w = detect_frame.shape[:2]
        rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        if not result.multi_hand_landmarks or not result.multi_handedness:
            self._frames_no_hand += 1
            if self._frames_no_hand < self._grace_frames and self._last_valid_result is not None:
                hand_data, hand_proto = self._last_valid_result
                return hand_data, hand_proto, True
            self._label_history.clear()
            self._hand_lock_frames = 0
            self._hand_locked = False
            self._low_conf_drop_frames = 0
            self._last_valid_result = None
            return None, None, False

        self._frames_no_hand = 0

        hand = result.multi_hand_landmarks[0]
        raw_label = result.multi_handedness[0].classification[0].label
        if is_mirrored:
            label = raw_label
        else:
            label = "Right" if raw_label == "Left" else "Left"

        label = self._resolve_label(label)
        confidence = float(result.multi_handedness[0].classification[0].score)

        if not self._passes_confidence_gate(confidence):
            return None, None, False

        if self._process_size is None:
            xy = [(max(0, min(src_w - 1, int(lm.x * src_w))), max(0, min(src_h - 1, int(lm.y * src_h)))) for lm in hand.landmark]
        else:
            sx = float(src_w) / float(max(1, w))
            sy = float(src_h) / float(max(1, h))
            xy = [(max(0, min(src_w - 1, int(lm.x * w * sx))), max(0, min(src_h - 1, int(lm.y * h * sy)))) for lm in hand.landmark]

        z = [float(lm.z) for lm in hand.landmark]
        hand_data = {
            "xy": xy,
            "z": z,
            "label": label,
            "confidence": confidence,
            "frame_size": (w, h),
        }

        self._last_valid_result = (hand_data, hand)
        return hand_data, hand, False

    def draw(self, frame_rgb, hand_proto, label: str = "Right") -> None:
        if hand_proto is None:
            return

        if label == "Right":
            conn_color = (0, 255, 0)
        else:
            conn_color = (255, 255, 0)

        conn_spec = DrawingSpec(color=conn_color, thickness=3, circle_radius=1) if DrawingSpec is not None else None
        lmk_spec = self._styles.get_default_hand_landmarks_style()

        self._draw.draw_landmarks(
            frame_rgb,
            hand_proto,
            self._mp_hands.HAND_CONNECTIONS,
            lmk_spec,
            conn_spec,
        )

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
                del self._hands
        except Exception:
            pass
