from __future__ import annotations

import os
from collections import deque

import cv2

try:
    import mediapipe as mp
except Exception:
    mp = None

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

from .utils import _ensure_mediapipe_solutions


class HandTracker:
    @staticmethod
    def _map_label(raw_label: str, is_mirrored: bool) -> str:
        raw = str(raw_label)
        if raw not in ("Left", "Right"):
            return raw
        if is_mirrored:
            return "Right" if raw == "Left" else "Left"
        return raw

    def __init__(self) -> None:
        self._process_size: tuple[int, int] | None = None
        self._last_rgb_frame = None
        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands
        self._draw_utils = mp.solutions.drawing_utils
        self._draw_styles = mp.solutions.drawing_styles

        self._hands = self._mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.50,
            min_tracking_confidence=0.30,
        )

        self._frames_no_hand = 0
        self._grace_frames = 3
        self._last_valid_result: tuple[dict, list] | None = None

    def set_processing_size(self, size: tuple[int, int] | None) -> None:
        if size is None:
            self._process_size = None
            return
        w, h = size
        self._process_size = (max(64, int(w)), max(64, int(h)))

    def detect(self, frame_bgr, is_mirrored: bool = False):
        """Returns (hands_dict, hand_protos_list, is_grace_frame)."""
        src_h, src_w = frame_bgr.shape[:2]

        detect_frame = frame_bgr
        if self._process_size is not None:
            detect_frame = cv2.resize(frame_bgr, self._process_size,
                                       interpolation=cv2.INTER_LINEAR)

        dh, dw = detect_frame.shape[:2]
        rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        self._last_rgb_frame = rgb
        result = self._hands.process(rgb)

        hands_dict = {}
        protos = []

        if result.multi_hand_landmarks and result.multi_handedness:
            sx = float(src_w) / max(1, dw)
            sy = float(src_h) / max(1, dh)

            for idx, hand in enumerate(result.multi_hand_landmarks):
                if idx >= len(result.multi_handedness):
                    break
                raw_label = result.multi_handedness[idx].classification[0].label
                label = self._map_label(raw_label, is_mirrored)
                conf = float(result.multi_handedness[idx].classification[0].score)

                if conf < 0.30:
                    continue

                xy = [(int(lm.x * dw * sx), int(lm.y * dh * sy))
                      for lm in hand.landmark]
                z = [float(lm.z) for lm in hand.landmark]

                # If we already have this label, keep the higher-confidence one
                if label in hands_dict:
                    if conf <= hands_dict[label]["confidence"]:
                        continue

                hands_dict[label] = {
                    "xy": xy,
                    "z": z,
                    "label": label,
                    "confidence": conf,
                    "frame_size": (dw, dh),
                }
                protos.append((hand, label))

        if hands_dict:
            self._frames_no_hand = 0
            self._last_valid_result = (hands_dict, protos)
            return hands_dict, protos, False
        else:
            self._frames_no_hand += 1
            if (self._frames_no_hand < self._grace_frames
                    and self._last_valid_result is not None):
                cached_dict, cached_protos = self._last_valid_result
                return cached_dict, cached_protos, True
            self._last_valid_result = None
            return {}, [], False

    def draw(self, frame_rgb, hand_protos, label: str = "Right") -> None:
        """Draw hand landmarks. Accepts either:
        - A list of (proto, label) tuples (new dual-hand format)
        - A single proto object (legacy single-hand format)
        """
        if hand_protos is None:
            return

        # Handle legacy single-proto call: draw(rgb, proto, label_str)
        if not isinstance(hand_protos, list):
            pairs = [(hand_protos, label)]
        else:
            pairs = hand_protos

        for proto, lbl in pairs:
            if proto is None:
                continue
            color = (0, 255, 120) if lbl == "Right" else (255, 180, 50)
            try:
                conn_spec = self._draw_utils.DrawingSpec(
                    color=color, thickness=2, circle_radius=2)
                lmk_spec = self._draw_styles.get_default_hand_landmarks_style()
                self._draw_utils.draw_landmarks(
                    frame_rgb, proto, self._mp_hands.HAND_CONNECTIONS,
                    lmk_spec, conn_spec)
            except Exception:
                pass

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
        except Exception:
            pass
