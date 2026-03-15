# AI-HollowGraphic-Like-Touch

A real-time, webcam-based AI hand-gesture mouse controller built with Python, OpenCV, MediaPipe, PyAutoGUI, and NumPy.

This starter project creates a "holographic touch" feel: move your hand in front of the camera to move the cursor, then pinch to click.

## Project Overview

AI-HollowGraphic-Like-Touch captures webcam frames, detects one hand with MediaPipe, extracts 21 landmarks, detects gestures, and maps index fingertip movement to your desktop cursor.

The app is designed for local CPU execution on Windows 11 and targets smooth interaction around 20-30 FPS on mid-range laptops.

## How Gesture Mouse Works

Pipeline:

1. Webcam captures 640x480 frames.
2. MediaPipe Hands detects one hand and tracks 21 landmarks.
3. Landmark processor extracts key tips (thumb, index, middle).
4. Cursor mapper interpolates camera coordinates to screen coordinates.
5. Cursor smoother reduces jitter.
6. Gesture detector recognizes pinch gestures.
7. Mouse controller sends cursor and click commands via PyAutoGUI.
8. OpenCV preview displays landmarks, gesture state, and FPS.

## Project Structure

```text
AI-HollowGraphic-Like-Touch/
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

## Installation

1. Open PowerShell in the project folder.
2. (Optional but recommended) Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Running the Program

Run the app from the project root:

```powershell
python src/main.py
```

Press `q` in the preview window to exit.

## Gesture Controls

| Gesture | Action |
|---|---|
| Index finger up | Move cursor |
| Thumb + index pinch | Left click |
| Thumb + middle pinch | Right click |

## Configuration Defaults

Configured in `src/config.py`:

- Camera: 640x480
- max_num_hands: 1
- min_detection_confidence: 0.7
- min_tracking_confidence: 0.7
- Click cooldown to avoid repeated click spam
- Smoothing window + interpolation for stable movement

## Notes for Best Results

- Keep your hand inside the webcam frame.
- Use good lighting for better landmark stability.
- Avoid cluttered backgrounds when possible.
- Start with a relaxed distance from camera, then fine-tune thresholds in `src/config.py`.

## Testing

Run gesture logic tests:

```powershell
pytest tests/test_gestures.py
```

## Future Improvements

- Drag-and-drop gesture
- Scroll gesture
- Multi-hand shortcuts
- Per-user calibration mode
- Dynamic gesture thresholds based on hand size
- Optional UI overlay panel for live tuning
