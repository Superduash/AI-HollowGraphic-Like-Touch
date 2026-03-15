"""Gesture guide panel for the GUI."""

import customtkinter as ctk

_GESTURES = [
    ("☝️  Index finger up", "Move cursor"),
    ("🤏  Thumb + index pinch", "Left click"),
    ("🤏🤏  Two pinches (fast)", "Double click"),
    ("✌️  Index + middle up", "Right click"),
    ("✌️↕  Two fingers + move", "Scroll"),
    ("🤏⏳  Pinch hold >0.3s", "Drag"),
    ("✊  Closed fist", "Pause"),
]


class GestureHelpPanel(ctk.CTkFrame):
    """Scrollable gesture reference panel."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        ctk.CTkLabel(self, text="Gesture Guide",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(8, 4))

        for gesture, action in _GESTURES:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)
            ctk.CTkLabel(row, text=gesture, font=ctk.CTkFont(size=12),
                         anchor="w", width=170).pack(side="left")
            ctk.CTkLabel(row, text=f"→ {action}", font=ctk.CTkFont(size=12),
                         text_color="#888888", anchor="w").pack(side="left")
