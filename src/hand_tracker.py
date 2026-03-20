from __future__ import annotations

from collections import deque
import os

import cv2  # type: ignore

try:
    from .onnx_hand_tracker import init_onnx, detect_onnx, _ONNX_AVAILABLE
except Exception:
    _ONNX_AVAILABLE = False

    def init_onnx() -> bool:
        return False

    def detect_onnx(frame_bgr):
        return None, 0.0

from .tuning import HAND_LABEL_MAJORITY_RATIO, HAND_LOCK_CONFIDENCE_THRESHOLD, HAND_LOCKED_DROP_THRESHOLD  # type: ignore
from .utils import _ensure_mediapipe_solutions  # type: ignore

os.environ.setdefault("GLOG_minloglevel", "2")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")


class _OnnxHandProto:
    """Lightweight stand-in for MediaPipe's hand proto in ONNX mode.
    Allows tracker.draw() to render landmarks from hand_data['xy']."""
    def __init__(self, xy: list):
        self.xy = xy
        # Fake MediaPipe landmark list interface
        class _Lm:
            def __init__(self, x, y, z=0.0):
                self.x = x; self.y = y; self.z = z
        self.landmark = [_Lm(*pt) if len(pt) >= 2 else _Lm(pt[0], pt[1]) for pt in xy]

try:
    import mediapipe as mp  # type: ignore
except Exception:
    mp = None  # type: ignore[assignment]

DrawingSpec = None
if mp is not None:
    DrawingSpec = mp.solutions.drawing_utils.DrawingSpec  # type: ignore[attr-defined]


class HandTracker:
    @staticmethod
    def _map_label(raw_label: str, is_mirrored: bool) -> str:
        """Map MediaPipe handedness to a stable user-facing label.

        MediaPipe's label is relative to the *image*. If we mirror the frame
        horizontally, left/right are swapped and we must invert the label.
        """
        raw = str(raw_label)
        if raw not in ("Left", "Right"):
            return raw
        if is_mirrored:
            return "Right" if raw == "Left" else "Left"
        return raw

    def __init__(self) -> None:
        self._process_size: tuple[int, int] | None = None
        self._last_rgb_frame = None
        self._label_history: deque[str] = deque(maxlen=3)
        self._stable_label = "Right"
        self._last_w: int = 640
        self._last_h: int = 480
        _ensure_mediapipe_solutions()

        self._mp_hands = mp.solutions.hands  # type: ignore[attr-defined]
        self._draw = mp.solutions.drawing_utils  # type: ignore[attr-defined]
        self._styles = mp.solutions.drawing_styles  # type: ignore[attr-defined]

        perf_mode = False
        try:
            from .settings_store import settings as _s
            perf_mode = bool(_s.get("performance_mode", False))
        except Exception:
            pass

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            model_complexity=0 if perf_mode else 1,
            min_detection_confidence=0.65,
            min_tracking_confidence=0.40,
        )

        self._frames_no_hand = 0
        self._grace_frames = 2
        self._last_valid_result: tuple[dict, object] | None = None
        self._last_valid_hand_data: dict | None = None

        self._hand_lock_frames = 0
        self._hand_locked = False
        self._low_conf_drop_frames = 0

        self._use_onnx = init_onnx()
        if self._use_onnx:
            print("[HAND] ONNX Runtime backend active (GPU accelerated)")
        else:
            print("[HAND] ONNX model not found — using MediaPipe backend")

    def set_processing_size(self, size: tuple[int, int] | None) -> None:
        if size is None:
            self._process_size = None
            return
        w, h = size
        self._process_size = (max(64, int(w)), max(64, int(h)))

    def _resolve_label(self, label: str) -> str:
        self._label_history.append(label)
        # Simple majority over last 3 frames - fast to stabilize, still noise-resistant
        counts = {}
        for l in self._label_history:
            counts[l] = counts.get(l, 0) + 1
        label = max(counts, key=counts.get)
        self._stable_label = label
        return label

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
        if self._use_onnx:
            xy_onnx, conf = detect_onnx(frame_bgr)
            if xy_onnx is not None:
                # Build hand_data compatible dict from ONNX output
                hand_data = {
                    "xy": xy_onnx,
                    "label": "Right",          # ONNX lite model is single-hand
                    "confidence": conf,
                    "fingers": 5,              # downstream code recalculates this
                }
                self._last_valid_hand_data = hand_data
                self._frames_no_hand = 0
                return hand_data, _OnnxHandProto(xy_onnx), False  # hand_data, hand_proto_truthy, is_grace
            else:
                self._frames_no_hand += 1
                if self._frames_no_hand < self._grace_frames and self._last_valid_hand_data:
                    _last_xy = self._last_valid_hand_data.get("xy", []) if self._last_valid_hand_data else []
                    return self._last_valid_hand_data, _OnnxHandProto(_last_xy) if _last_xy else None, True
                return None, None, False
        # ... existing MediaPipe code continues below unchanged ...

        src_h, src_w = frame_bgr.shape[:2]

        detect_frame = frame_bgr
        if self._process_size is not None:
            detect_frame = cv2.resize(frame_bgr, self._process_size, interpolation=cv2.INTER_LINEAR)

        h, w = frame_bgr.shape[:2] if hasattr(frame_bgr, 'shape') else (self._last_h, self._last_w)
        self._last_w = w
        self._last_h = h
        detect_h, detect_w = detect_frame.shape[:2]
        frame_rgb = cv2.cvtColor(detect_frame, cv2.COLOR_BGR2RGB)
        self._last_rgb_frame = frame_rgb   # Cache for zero-copy display in _render()
        result = self._hands.process(frame_rgb)

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

        # With max_num_hands=2, prefer the Right hand for cursor control.
        # Pick the hand whose resolved label is "Right" when available,
        # else fall back to the first detected hand.
        chosen_idx = 0
        if len(result.multi_hand_landmarks) > 1:
            for i, hedness in enumerate(result.multi_handedness):
                raw = hedness.classification[0].label
                mapped = self._map_label(raw, is_mirrored=is_mirrored)
                if mapped == "Right":
                    chosen_idx = i
                    break

        hand = result.multi_hand_landmarks[chosen_idx]
        raw_label = result.multi_handedness[chosen_idx].classification[0].label
        label = self._map_label(raw_label, is_mirrored=is_mirrored)

        label = self._resolve_label(label)
        confidence = float(result.multi_handedness[chosen_idx].classification[0].score)

        if not self._passes_confidence_gate(confidence):
            return None, None, False

        if self._process_size is None:
            xy = [(max(0, min(src_w - 1, int(lm.x * src_w))), max(0, min(src_h - 1, int(lm.y * src_h)))) for lm in hand.landmark]
        else:
            sx = float(src_w) / float(max(1, detect_w))
            sy = float(src_h) / float(max(1, detect_h))
            xy = [(max(0, min(src_w - 1, int(lm.x * detect_w * sx))), max(0, min(src_h - 1, int(lm.y * detect_h * sy)))) for lm in hand.landmark]

        z = [float(lm.z) for lm in hand.landmark]
        hand_data = {
            "xy": xy,
            "z": z,
            "label": label,
            "confidence": confidence,
            "frame_size": (detect_w, detect_h),
        }

        self._last_valid_result = (hand_data, hand)
        return hand_data, hand, False

    def draw(self, frame_rgb, hand_proto, label: str = "Right") -> None:
        if hand_proto is None:
            return
        if not hasattr(hand_proto, "landmark"):
            return

        mp_drawing = mp.solutions.drawing_utils
        mp_drawing.draw_landmarks(
            frame_rgb,
            hand_proto,
            mp.solutions.hands.HAND_CONNECTIONS,
            mp_drawing.DrawingSpec(color=(0, 255, 120), thickness=2, circle_radius=4),
            mp_drawing.DrawingSpec(color=(255, 255, 255), thickness=2, circle_radius=2),
        )

    def close(self) -> None:
        try:
            if hasattr(self, "_hands") and self._hands:
                self._hands.close()
                del self._hands
        except Exception:
            pass
