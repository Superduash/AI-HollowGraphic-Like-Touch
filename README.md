<div align="center">

<img src="https://capsule-render.vercel.app/api?type=venom&height=280&color=0:0b1220,50:111827,100:06b6d4&text=HoloTouch&fontSize=86&fontColor=ffffff&animation=fadeIn&fontAlignY=42&desc=Touchless%20AI%20Hand%20Gesture%20Control&descAlignY=63&descColor=67e8f9&descSize=22"/>

<br/>

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Hand%20Tracking-06b6d4?style=for-the-badge&logo=google&logoColor=white)](https://mediapipe.dev)
[![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-22c55e?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![PySide6](https://img.shields.io/badge/PySide6-Desktop%20UI-7c3aed?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython)
[![Windows](https://img.shields.io/badge/Windows-Supported-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Superduash/HoloTouch/releases)
[![License](https://img.shields.io/badge/License-MIT-f97316?style=for-the-badge)](LICENSE)

<br/>

**Control your PC with natural hand gestures — no mouse, no trackpad, no contact.**

[**⬇ Download .exe**](#-installation) · [**📖 How It Works**](#-how-it-works) · [**🎯 Features**](#-features) · [**🛠 Tech Stack**](#-tech-stack)

<br/>

</div>

---

## 📸 Demo

<div align="center">

<img width="1919" height="1029" alt="Screenshot 2026-06-23 141315-overlay" src="https://github.com/user-attachments/assets/9e304727-5bfe-4357-981a-263c4fe4d80e" />

| Cursor Control | Left Click | Right Click | Scroll |
|:-:|:-:|:-:|:-:|
| ☝️ Index up | 👌 Pinch index | 🤏 Pinch middle | ✌️ Two fingers |

</div>

---

## 🧠 What Is HoloTouch?

HoloTouch turns any standard webcam into a **zero-touch computer controller**.

It processes the live camera feed, detects **21 hand landmarks per frame** using MediaPipe's neural network, maps that geometry to cursor coordinates in real time, and fires OS-level mouse events — all at interactive framerates on consumer hardware.

The result: you move, click, drag, and scroll entirely through gesture — no physical input device required.

> Built as an exploration of real-time computer vision pipelines, human-computer interaction, and desktop application architecture using modern Python.

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🖱 Virtual Mouse
Smooth, low-latency cursor movement driven entirely by index finger position. Configurable sensitivity and smoothing curves.

### 👆 Gesture Actions
- **Left click** — index + thumb pinch
- **Right click** — middle + thumb pinch
- **Double click** — rapid index pinch
- **Click & drag** — hold pinch + move
- **Scroll** — two-finger vertical swipe

</td>
<td width="50%">

### ⚡ Optimized Pipeline
Frame processing uses NumPy vectorization and Numba JIT compilation to minimize latency. Landmark detection runs asynchronously from the UI thread.

### 🖥 Desktop Control Panel
Floating PySide6 overlay with:
- Live camera preview
- Real-time gesture feedback
- Sensitivity and smoothing sliders
- Enable/disable toggle (hotkey supported)

</td>
</tr>
</table>

---

## 🔬 How It Works

```
Webcam Frame
     │
     ▼
┌─────────────────────────────┐
│   OpenCV — Frame Capture    │  Reads frames, flips + converts BGR→RGB
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  MediaPipe — Hand Landmark  │  21 3D keypoints per hand @ real-time fps
│        Detection            │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Gesture Classifier         │  Euclidean distance + angle heuristics
│  (src/gesture_engine.py)    │  to map landmark geometry → gesture label
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Mouse Controller           │  Maps normalized [0,1] coords → screen px
│  (src/mouse_controller.py)  │  Fires win32api / pyautogui OS events
└─────────────┬───────────────┘
              │
              ▼
       System Cursor / Click
```

**Coordinate mapping** uses a calibrated dead-zone and exponential smoothing (`α = 0.35`) to reduce jitter without introducing perceptible lag.

---

## 🛠 Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Hand Tracking | **MediaPipe Hands** | 21-landmark ML model, runs CPU-only at 30+ fps |
| Frame Pipeline | **OpenCV** | Industry-standard camera I/O and frame processing |
| Math / Coords | **NumPy** | Vectorized landmark math with zero Python loops |
| JIT Optimization | **Numba** | Hot path compilation for landmark-to-coord transforms |
| OS Mouse Events | **PyAutoGUI / win32api** | Native Windows cursor + click injection |
| Desktop UI | **PySide6** | Qt-based overlay panel, no browser runtime needed |
| Distribution | **PyInstaller** | Single `.exe` bundle, no Python required for end users |

---

## 📂 Project Structure

```
HoloTouch/
├── app.py                    # Entry point — initializes camera, UI, and pipeline
├── src/
│   ├── gesture_engine.py     # Landmark geometry → gesture label classifier
│   ├── mouse_controller.py   # Gesture → OS mouse event translation
│   ├── hand_tracker.py       # MediaPipe wrapper, frame preprocessing
│   ├── smoother.py           # Exponential smoothing for cursor coordinates
│   └── overlay.py            # PySide6 floating control panel
├── assets/
│   └── icons/
├── tests/
│   ├── test_gesture_engine.py
│   └── test_smoother.py
├── requirements.txt
└── README.md
```

---

## 🚀 Installation

### Option A — Run from Source

```bash
# Clone and enter
git clone https://github.com/Superduash/HoloTouch.git
cd HoloTouch

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

**Requirements:** Python 3.12+, webcam, Windows 10/11

### Option B — Windows Executable (No Python needed)

```
1. Go to Releases → download HoloTouch.exe
2. Run it — allow camera access when prompted
3. The control panel appears; press Start
```

> **Note:** Windows Defender may flag the `.exe` on first run (unsigned binary). Click *More Info → Run Anyway* to proceed.

---

## 🎮 Gesture Reference

| Gesture | Action | How |
|---|---|---|
| ☝️ Index finger up, others folded | **Move cursor** | Tracks index fingertip |
| 👌 Index tip meets thumb tip | **Left click** | Pinch and release |
| 🤏 Middle tip meets thumb tip | **Right click** | Pinch and release |
| 👌 Hold pinch + move | **Click & drag** | Maintain contact while moving |
| ✌️ Index + middle up, move vertically | **Scroll** | Up/down displacement |
| ✊ Fist | **Pause tracking** | No cursor movement while fist held |

---

## 🔮 Roadmap

- [ ] Custom gesture binding (map any gesture → any key/shortcut)
- [ ] Multi-hand support (two-hand gestures)
- [ ] User gesture profiles (save/load per user)
- [ ] GPU acceleration via CUDA MediaPipe
- [ ] Linux support (X11 / Wayland)
- [ ] macOS support (Accessibility API)
- [ ] CLI mode (headless, no UI overlay)

---

## 🤝 Contributing

Contributions welcome. For significant changes, open an issue first to discuss what you'd like to change. Please add or update tests as appropriate.

```bash
# Run tests
python -m pytest tests/
```

---

## 📜 License

MIT License — free to use, modify, and distribute. See [LICENSE](LICENSE) for full text.

---

<div align="center">

**Built with Python, MediaPipe, and OpenCV**

*HoloTouch is a portfolio project exploring real-time computer vision and human-computer interaction.*

⭐ If this project interests you, a star helps others find it.

<img src="https://capsule-render.vercel.app/api?type=waving&height=120&section=footer&color=0:06b6d4,50:111827,100:0b1220"/>

</div>
