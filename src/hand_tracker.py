from __future__ import annotations

import cv2
from collections import deque

from .utils import _ensure_mediapipe_solutions

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
        self._label_history: deque = deque(maxlen=9)
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

        # ── BUG B FIX: Grace period for hand loss ──
        self._frames_no_hand = 0
        self._grace_frames = 4
        self._last_valid_result: tuple | None = None  # (hand_data, hand_proto)
        self._log_cooldown_s = 5.0
        self._last_log_ts = 0.0
        self._last_logged_label = ""

    def set_processing_size(self, size: tuple[int, int] | None) -> None:
        if size is None:
            self._process_size = None
            return
        w, h = size
        self._process_size = (max(64, int(w)), max(64, int(h)))

    def detect(self, frame_bgr, is_mirrored=False):
        src_h, src_w = frame_bgr.shape[:2]

        detect_frame = frame_bgr
        if self._process_size is not None:
            detect_frame = cv2.resize(frame_bgr, self._process_size, interpolation=cv2.INTER_LINEAR)

        h, w = detect_frame.shape[:2]
        rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        if not result.multi_hand_landmarks or not result.multi_handedness:
            # ── BUG B FIX: Grace period — emit last known hand for 8 frames ──
            self._frames_no_hand += 1
            if self._frames_no_hand < self._grace_frames and self._last_valid_result is not None:
                return self._last_valid_result
            self._label_history.clear()
            self._last_valid_result = None
            return None, None

        # Hand detected — reset grace counter
        self._frames_no_hand = 0

        hand = result.multi_hand_landmarks[0]
        raw_label = result.multi_handedness[0].classification[0].label
        # If the frame is already mirrored (cv2.flip), MediaPipe's label is correct.
        # If not mirrored, MediaPipe sees a mirror image, so we flip the label.
        if is_mirrored:
            label = raw_label
        else:
            label = "Right" if raw_label == "Left" else "Left"

        # Smooth label over last 9 frames — require 7/9 majority to switch
        self._label_history.append(label)
        right_count = list(self._label_history).count("Right")
        left_count = list(self._label_history).count("Left")
        total = len(self._label_history)
        # Only switch if strong majority (7+ of 9 frames agree)
        threshold = max(5, int(total * 0.75))
        if right_count >= threshold:
            label = "Right"
        elif left_count >= threshold:
            label = "Left"
        else:
            # No strong majority — keep previous label
            label = self._last_logged_label if self._last_logged_label else "Right"

        self._last_logged_label = label
        # Hand label logging disabled for production

        confidence = result.multi_handedness[0].classification[0].score

        # ── BUG B FIX: Confidence gate lowered from 0.6 → 0.4 ──
        if confidence < 0.55:
            # Low confidence — don't use grace period, return nothing
            return None, None

        if self._process_size is None:
            xy = [(int(lm.x * src_w), int(lm.y * src_h)) for lm in hand.landmark]
        else:
            sx = float(src_w) / float(max(1, w))
            sy = float(src_h) / float(max(1, h))
            xy = [(int(lm.x * w * sx), int(lm.y * h * sy)) for lm in hand.landmark]
        z = [float(lm.z) for lm in hand.landmark]
        hand_data = {
            "xy": xy,
            "z": z,
            "label": label,
            "confidence": confidence,
            "frame_size": (w, h),
        }

        # Save for grace period
        self._last_valid_result = (hand_data, hand)

        return hand_data, hand

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