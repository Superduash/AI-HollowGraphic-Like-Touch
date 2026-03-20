"""ONNX Runtime hand landmark detector.

Drop-in backend for hand_tracker.py. Uses the community-converted MediaPipe
hand landmark model (float32, input 224x224 RGB, output 21x3 normalized coords).

Model source: PINTO0309/PINTO_model_zoo — hand_landmark_lite.onnx
Download: place hand_landmark_lite.onnx in the project root or set
          HOLO_HAND_MODEL env var to the full path.

Falls back to None (disables ONNX path) if model file not found or
onnxruntime not installed — hand_tracker.py will use MediaPipe instead.
"""
from __future__ import annotations

import os
import platform
import time
from pathlib import Path
from collections import deque

import cv2
import numpy as np

_ONNX_SESSION = None
_ONNX_AVAILABLE = False
_INPUT_SIZE = 224


def _get_model_path() -> Path | None:
    env = os.environ.get("HOLO_HAND_MODEL", "").strip()
    if env and Path(env).exists():
        return Path(env)
    candidates = [
        Path("hand_landmark_lite.onnx"),
        Path(__file__).parent.parent / "hand_landmark_lite.onnx",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def init_onnx() -> bool:
    """Initialize ONNX Runtime session. Returns True if successful."""
    global _ONNX_SESSION, _ONNX_AVAILABLE
    if _ONNX_AVAILABLE:
        return True
    try:
        import onnxruntime as ort  # type: ignore
        model_path = _get_model_path()
        if model_path is None:
            return False
        providers = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if platform.system() == "Windows"
            else ["CPUExecutionProvider"]
        )
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _ONNX_SESSION = ort.InferenceSession(str(model_path), opts, providers=providers)
        _ONNX_AVAILABLE = True
        return True
    except Exception:
        return False


def _preprocess(frame_bgr: np.ndarray) -> np.ndarray:
    """Resize to 224x224, convert BGR→RGB, normalize to [0,1], add batch dim."""
    img = cv2.resize(frame_bgr, (_INPUT_SIZE, _INPUT_SIZE), interpolation=cv2.INTER_LINEAR)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return img[np.newaxis]  # (1, 224, 224, 3)


def _postprocess(raw_landmarks: np.ndarray, frame_w: int, frame_h: int) -> list[tuple[float, float, float]]:
    """Convert model output to list of 21 (x, y, z) in pixel coords."""
    pts = raw_landmarks.reshape(21, 3)
    xy = []
    for lm in pts:
        x = float(lm[0]) * frame_w / _INPUT_SIZE
        y = float(lm[1]) * frame_h / _INPUT_SIZE
        z = float(lm[2])
        xy.append((x, y, z))
    return xy


def detect_onnx(frame_bgr: np.ndarray) -> tuple[list | None, float]:
    """Run ONNX hand landmark detection.

    Returns:
        (landmarks_xy, confidence) where landmarks_xy is list of 21 (x,y,z) tuples
        or (None, 0.0) if no hand detected or ONNX not available.
    """
    if not _ONNX_AVAILABLE or _ONNX_SESSION is None:
        return None, 0.0
    try:
        h, w = frame_bgr.shape[:2]
        inp = _preprocess(frame_bgr)
        outputs = _ONNX_SESSION.run(None, {_ONNX_SESSION.get_inputs()[0].name: inp})
        landmarks = outputs[0]           # shape: (1, 63) or (21, 3)
        score = float(outputs[1]) if len(outputs) > 1 else 0.85
        if score < 0.5:
            return None, score
        xy = _postprocess(landmarks, w, h)
        return xy, score
    except Exception:
        return None, 0.0
