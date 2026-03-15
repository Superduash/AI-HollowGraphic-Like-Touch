# AI Holographic Touch 🖐️

Control your computer mouse using only your hands — no physical contact required.
Point your index finger at the screen to move the cursor; pinch your fingers together
to click.  The webcam becomes your holographic touchpad.

---

## How It Works

1. **Webcam capture** – OpenCV reads frames from your built-in or USB webcam at
   approximately 640 × 480 resolution for low CPU usage.
2. **Hand landmark detection** – MediaPipe Hands locates 21 key points on your hand
   in every frame (fingertips, knuckles, wrist).
3. **Gesture interpretation** – Distances between fingertips are measured each frame
   to classify the current gesture (cursor position or click).
4. **Coordinate mapping** – The index finger tip position in the webcam frame is
   mapped to screen coordinates with a small edge margin so you can reach every
   corner comfortably.
5. **Smoothing** – An Exponential Moving Average (EMA) filter removes jitter so the
   cursor feels stable even on a low-end machine.
6. **Mouse control** – PyAutoGUI moves the OS cursor and fires click events.

---

## Gestures

| Gesture | Action |
|---|---|
| Move index finger | Move cursor |
| Pinch thumb ↔ index finger | Left click |
| Pinch thumb ↔ middle finger | Right click |

---

## Project Structure

```
ai-holographic-touch/
│
├── main.py             # Entry point – main capture and control loop
├── hand_tracker.py     # MediaPipe Hands wrapper
├── gesture_detector.py # Pinch / gesture recognition
├── mouse_controller.py # PyAutoGUI mouse movement and click injection
├── utils.py            # Coordinate mapping, EMA smoother, FPS counter
├── requirements.txt    # Python dependencies
└── README.md           # This file
```

### Module responsibilities

| File | Responsibility |
|---|---|
| `hand_tracker.py` | Initialise MediaPipe Hands; detect 21 landmarks per frame; draw skeleton overlay |
| `gesture_detector.py` | Measure fingertip distances; detect pinch gestures; apply per-gesture cooldown |
| `mouse_controller.py` | Move the OS mouse cursor; fire left / right click events via PyAutoGUI |
| `utils.py` | `map_coordinates` (webcam → screen), `EMAFilter` (smoothing), `FPSCounter` |
| `main.py` | Camera loop, flip mirror, integrate all modules, draw FPS & status overlay |

---

## Requirements

- Python 3.8 or newer
- A working webcam
- macOS or Windows (Linux works too but may require additional system packages for
  PyAutoGUI's screen-capture dependency)

Tested on:
- macOS 13 (Ventura) – MacBook Air 2015, Intel Core i5
- Windows 11 – Intel Core i5-8th Gen

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Superduash/ai-holographic-touch.git
cd ai-holographic-touch

# 2. (Optional but recommended) create a virtual environment
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### macOS note
PyAutoGUI requires *Accessibility* and *Screen Recording* permissions on macOS.
Go to **System Settings → Privacy & Security** and grant both permissions to your
terminal application (e.g. Terminal.app or iTerm2).

### Windows note
No extra steps are required.  If the webcam is not recognised at index 0, edit
`CAMERA_INDEX` in `main.py`.

---

## Running the Program

```bash
python main.py
```

A preview window opens showing:
- The live webcam feed with the hand skeleton drawn on it.
- An **FPS** counter in the top-left corner.
- A **status bar** at the bottom showing the current pinch distances vs the
  detection threshold, and a flash label when a click fires.

Press **Q** while the preview window is focused to quit cleanly.

> **Safety tip:** PyAutoGUI's *fail-safe* is enabled by default.  Moving your
> physical mouse to the **top-left corner** of the screen will raise an exception
> and exit the program immediately — handy if the cursor ever runs away.

---

## Configuration

All tuneable parameters are at the top of `main.py`:

| Constant | Default | Description |
|---|---|---|
| `CAMERA_INDEX` | `0` | Webcam device index |
| `CAPTURE_WIDTH` / `CAPTURE_HEIGHT` | `640` / `480` | Requested webcam resolution |
| `SMOOTHING_ALPHA` | `0.25` | EMA smoothing (lower = smoother, more lag) |
| `PINCH_THRESHOLD_RATIO` | `0.07` | Fraction of frame diagonal for click trigger |
| `CLICK_COOLDOWN` | `0.5` | Seconds between repeated clicks of the same type |
| `COORDINATE_MARGIN` | `0.05` | Dead-zone margin at frame edges (fraction) |

---

## Performance Tips

- **Lower resolution** (`320×240`) reduces CPU load if FPS drops below 15.
- **Increase `SMOOTHING_ALPHA`** towards `0.5` for snappier cursor response on a
  fast machine.
- **Close unnecessary background apps** – MediaPipe's neural network is CPU-heavy
  on machines without a GPU or Apple Neural Engine.
- On macOS, **disable Spotlight indexing** temporarily if CPU usage is very high.

---

## Future Improvements

- [ ] Scroll gesture (two-finger vertical swipe)
- [ ] Double-click detection (rapid pinch twice)
- [ ] Drag-and-drop (hold pinch while moving)
- [ ] Multi-hand support (two-hand gestures)
- [ ] Configurable gesture profiles (JSON / YAML config file)
- [ ] System-tray icon and overlay HUD
- [ ] GPU acceleration via ONNX Runtime or CoreML (Apple Silicon)
- [ ] Virtual touchpad mode with gesture zones

---

## License

[MIT License](LICENSE)

