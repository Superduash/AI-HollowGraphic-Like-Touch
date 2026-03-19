Windows Hover (USB build)

Run on Windows:
1) Double-click run.bat

Notes:
- Uses the best available Python via the Windows 'py' launcher (prefers 3.12).
- Creates a local .venv and installs requirements automatically on first run.
- When you click "Enable Mouse", the main window minimizes and a small always-on-top status overlay stays visible.

This build is optimized for:
- 720p/640x480 camera capture with backend fallback (MSMF, DSHOW, ANY)
- full-resolution hand processing with MediaPipe Hands
- multi-monitor virtual screen mapping with inner-region overshoot
- gestures (Right hand): move, left click, double click, drag, right click, scroll, task view, keyboard
- gestures (Left hand): media volume up/down and next/previous track only
