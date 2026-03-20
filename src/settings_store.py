from __future__ import annotations

import json
from pathlib import Path


class SettingsStore:
    DEFAULTS = {
        "camera_index": 0,
        "frame_r": 90,
        "smoothening": 4.8,
        "debug_overlay": False,
        "scroll_multiplier": 1.0,
        "pinch_sensitivity": 0.22,
        "pinch_exit_sensitivity": 0.38,
        "confirm_hold_s": 0.03,
        "auto_start_camera": False,
        "minimize_to_tray": False,
        "show_control_region": True,
        "mirror_camera": True,
        "performance_mode": False,
        "cursor_mode": "dual_hand",
        "eye_tracking_gain": 1.8,
        "hand_only_mode": True,
        "overlay_x": -1,
        "overlay_y": -1,
        "window_x": -1,
        "window_y": -1,
        "window_w": 1280,
        "window_h": 820,
    }

    def __init__(self) -> None:
        self._dir = Path.home() / ".holographic_touch"
        self._path = self._dir / "settings.json"
        self._data: dict[str, object] = {}
        self.load()

    def get(self, key, default=None):
        if key in self._data:
            return self._data[key]
        if key in self.DEFAULTS:
            return self.DEFAULTS[key]
        return default

    def set(self, key, value):
        self._data[key] = value
        self.save()

    def load(self):
        merged = dict(self.DEFAULTS)
        try:
            if self._path.exists():
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in self.DEFAULTS:
                            merged[k] = v

                    # Migrate previously regressed gesture defaults to stable values.
                    if (
                        merged.get("pinch_sensitivity") == 0.20
                        and merged.get("pinch_exit_sensitivity") == 0.30
                    ):
                        merged["pinch_sensitivity"] = 0.22
                        merged["pinch_exit_sensitivity"] = 0.38

                    if merged.get("confirm_hold_s") == 0.22:
                        merged["confirm_hold_s"] = 0.05
        except Exception:
            pass
        self._data = merged
        return self._data

    def save(self):
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            payload = {k: self._data.get(k, v) for k, v in self.DEFAULTS.items()}
            tmp_path = self._path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_path.replace(self._path)
        except Exception:
            pass


settings = SettingsStore()