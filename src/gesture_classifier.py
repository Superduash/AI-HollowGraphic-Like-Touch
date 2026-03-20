"""ML-based gesture classifier.

Replaces threshold rules with a RandomForest trained on 63 landmark features.
Falls back gracefully to None if model not trained yet.

TRAINING: Run `python train_gesture_classifier.py` after collecting samples.
INFERENCE: ~0.1ms per prediction (sklearn on 63 floats).
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

try:
    import sklearn  # type: ignore  # noqa: F401
    _SKLEARN_AVAILABLE = True
except Exception:
    _SKLEARN_AVAILABLE = False

if TYPE_CHECKING:
    from .models import GestureType

MODEL_PATH = Path(__file__).parent.parent / "gesture_model.pkl"
LABEL_PATH = Path(__file__).parent.parent / "gesture_labels.json"

_clf = None
_labels: list[str] = []
_LOADED = False


def load_model() -> bool:
    """Load trained classifier. Returns True if successful."""
    global _clf, _labels, _LOADED
    if _LOADED:
        return _clf is not None
    _LOADED = True
    try:
        if not _SKLEARN_AVAILABLE:
            return False
        if not MODEL_PATH.exists():
            return False
        with open(MODEL_PATH, "rb") as f:
            _clf = pickle.load(f)
        if LABEL_PATH.exists():
            _labels = json.loads(LABEL_PATH.read_text())
        return True
    except Exception:
        _clf = None
        return False


def predict_gesture(xy: list, label: str = "Right") -> tuple[str | None, float]:
    """Predict gesture from 21 landmarks.

    Args:
        xy: list of 21 (x, y) or (x, y, z) tuples - hand_data['xy']
        label: "Right" or "Left" hand

    Returns:
        (gesture_name, confidence) or (None, 0.0) if model not loaded
    """
    if _clf is None:
        return None, 0.0
    try:
        pts = np.asarray(xy[:21], dtype=np.float32).flatten()
        if len(pts) < 42:
            return None, 0.0

        # Normalize: translate wrist to origin, scale by wrist-to-middle_mcp dist
        wrist = pts[:2].copy()
        pts_2d = pts[:42].reshape(21, 2)
        pts_2d -= wrist
        scale = float(np.linalg.norm(pts_2d[9] - pts_2d[0]) + 1e-6)
        pts_2d /= scale

        features = pts_2d.flatten().reshape(1, -1)
        proba = _clf.predict_proba(features)[0]
        idx = int(np.argmax(proba))
        confidence = float(proba[idx])

        if confidence < 0.70:   # Low confidence -> defer to rules engine
            return None, confidence

        gesture_name = _labels[idx] if idx < len(_labels) else None
        return gesture_name, confidence
    except Exception:
        return None, 0.0
