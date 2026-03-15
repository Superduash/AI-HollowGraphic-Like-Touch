# AI-HollowGraphic-Like-Touch

Real-time AI hand-gesture mouse controller using webcam input.

Built with Python, OpenCV, MediaPipe, PyAutoGUI, and NumPy.

## Overview

This project creates a touchless "holographic touch" interaction:

1. Detect one hand (21 landmarks) with MediaPipe.
2. Track index fingertip for cursor movement.
3. Use pinch gestures for left and right click.
4. Smooth cursor coordinates to reduce jitter.
5. Show live FPS + debug overlays in the preview window.

Runs locally on CPU and targets around 20 to 30 FPS on mid-range laptops.

## Gesture Controls

| Gesture | Action |
|---|---|
| Index finger up | Move cursor |
| Thumb + index pinch | Left click |
| Thumb + middle pinch | Right click |

## Project Structure

```text
AI-HollowGraphic-Like-Touch/
+-- main.py
+-- src/
¦   +-- main.py
¦   +-- config.py
¦   +-- tracking/
¦   ¦   +-- hand_tracker.py
¦   ¦   +-- landmark_processor.py
¦   +-- gestures/
¦   ¦   +-- gesture_detector.py
¦   ¦   +-- gesture_types.py
¦   +-- controller/
¦   ¦   +-- mouse_controller.py
¦   ¦   +-- cursor_mapper.py
¦   +-- utils/
¦       +-- smoothing.py
¦       +-- fps_counter.py
¦       +-- math_utils.py
+-- assets/
¦   +-- icons/
¦   +-- demo/
+-- tests/
¦   +-- test_gestures.py
+-- requirements.txt
+-- README.md
```

## Requirements

- Python 3.10+
- Webcam
- macOS or Windows

## Installation

### macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

macOS permissions you must allow:

1. System Settings > Privacy & Security > Camera
2. System Settings > Privacy & Security > Accessibility

Enable both for the app you use to run Python (Terminal, iTerm, VS Code).

### Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

From project root, either command works:

```bash
python main.py
```

or

```bash
python src/main.py
```

Press `q` to exit the preview window.

## Performance Defaults

Configured in src/config.py:

- Camera resolution: 640x480
- max_num_hands: 1
- min_detection_confidence: 0.7
- min_tracking_confidence: 0.7
- Click cooldown to avoid repeated clicks
- Cursor smoothing window and interpolation
- Camera fallback indexes: [0, 1, 2]

## Troubleshooting

- Webcam not opening:
  - Close Zoom/Meet/Teams/OBS and retry.
  - On macOS, confirm Camera permission.
  - The app automatically tries multiple camera indexes and backends.

- Cursor does not move/click on macOS:
  - Grant Accessibility permission to the Python host app.

- Low FPS:
  - Improve lighting, keep only one hand in frame, close heavy apps.

## Testing

```bash
pytest tests/test_gestures.py
```

## Future Improvements

- Scroll gesture
- Drag gesture
- Per-user calibration
- Runtime sensitivity UI panel
- Gesture shortcuts
