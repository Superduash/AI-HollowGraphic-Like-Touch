═══════════════════════════════════════════════════════════════
 HOLOGRAPHIC TOUCH  —  AI Hand-Gesture Mouse Controller
═══════════════════════════════════════════════════════════════

Control your Windows PC with your hands — no physical contact.
Uses MediaPipe hand landmark detection + a custom gesture engine.

───────────────────────────────────────────────────────────────
 QUICK START
───────────────────────────────────────────────────────────────

Double-click  run.bat
  → Creates a .venv, installs requirements, launches the app.

OR manually:
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  python app.py


───────────────────────────────────────────────────────────────
 REQUIREMENTS
───────────────────────────────────────────────────────────────

• Windows 10 / 11 (64-bit)
• Python 3.10, 3.11, or 3.12  (https://python.org)
• Webcam (USB, built-in, or virtual e.g. DroidCam / iVCam)


───────────────────────────────────────────────────────────────
 GESTURE REFERENCE
───────────────────────────────────────────────────────────────

 DUAL-HAND MODE (default when 2 hands visible)
  Right hand  — Index finger raised  → moves cursor
  Left hand:
    Thumb + Index pinch              → Left Click
    Quick double pinch               → Double Click
    Hold pinch (0.5 s)               → Drag (hold until released)
    Thumb + Middle pinch (hold)      → Right Click
    Index + Middle raised together   → Scroll (move up/down)

 SINGLE-HAND MODE (auto when only 1 hand visible)
  Same hand does cursor movement AND all gestures above.

 MODE SWITCHING
  The app switches automatically:
    2 hands seen for 1.5 s  →  Dual mode
    1 hand seen for 3.0 s   →  Single mode

 GLOBAL HOTKEY
  Ctrl + Shift + H   →  Toggle mouse on/off from anywhere


───────────────────────────────────────────────────────────────
 SETTINGS
───────────────────────────────────────────────────────────────

Click the ⚙ gear icon in the main window to open Settings:

• Camera           — select camera source
• Smoothening      — cursor smoothness (1=raw, 10=very smooth)
• Head/Hand Range  — size of the active control region box
• Scroll Speed     — multiplier for scroll gesture
• Pinch Sensitivity — how close fingers must be for a click
• Confirm Hold     — minimum hold time before action fires
• Mirror Camera    — flip feed left/right (usually ON)
• Show Region Box  — display the cyan control boundary
• Debug Overlay    — show hand skeleton on the feed


───────────────────────────────────────────────────────────────
 FILE STRUCTURE
───────────────────────────────────────────────────────────────

  app.py              Entry point
  run.bat             One-click launcher (Windows)
  requirements.txt    Python dependencies
  export.py           Generate a single-file project snapshot
  src/
    main_window.py    Main GUI + processing orchestration
    camera_thread.py  OpenCV capture thread
    hand_tracker.py   MediaPipe hand landmark detection
    gesture_detector.py  Pinch/scroll/drag gesture engine
    cursor_mapper.py  Camera → screen coordinate mapping
    mouse.py          Win32 SendInput mouse controller
    settings_store.py Persistent JSON settings
    fast_math.py      Numba-compiled math kernels
    tuning.py         Performance/behaviour constants
    constants.py      Overlay label strings
    utils.py          Platform helpers
    models.py         GestureType / GestureResult dataclasses
  assets/
    icons/            App icon SVG
  tools/
    export_project_compact.py   Project snapshot exporter


───────────────────────────────────────────────────────────────
 TROUBLESHOOTING
───────────────────────────────────────────────────────────────

Camera not found:
  • Open DroidCam/iVCam BEFORE clicking Initialize.
  • Try different Camera Index in Settings (0, 1, 2…).

Hand not detected:
  • Ensure adequate lighting (avoid strong backlight).
  • Keep hand within the cyan control region box.
  • Check confidence reading in the System Status panel.

High CPU usage:
  • The app uses CPU-based MediaPipe (model_complexity=0).
  • Close other camera apps to free bandwidth.

Mouse jumps:
  • Increase Smoothening in Settings.
  • Decrease Pinch Sensitivity (raise the threshold number).

───────────────────────────────────────────────────────────────
 EXPORT PROJECT SNAPSHOT
───────────────────────────────────────────────────────────────

  python export.py

Writes project_compact_export.txt (all source files combined).
Useful for sharing context with AI tools or for archiving.
