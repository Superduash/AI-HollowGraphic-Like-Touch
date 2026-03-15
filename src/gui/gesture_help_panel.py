"""Gesture guide panel for the GUI."""

import customtkinter as ctk

_GESTURES = [
    ("☝️ Index up", "Move"),
    ("🤏 Pinch", "L-Click"),
    ("🤏🤏 2x Pinch", "D-Click"),
    ("✌️ 2 Fingers", "R-Click"),
    ("🤏⏳ Hold", "Drag"),
    ("✌️↕ Move Y", "Scroll"),
    ("✊ Fist", "Pause"),
]


class GestureHelpPanel(ctk.CTkFrame):
    """Clean, modern gesture reference panel."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        ctk.CTkLabel(self, text="Gesture Guide",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=(12, 8))

        list_frame = ctk.CTkFrame(self, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=12, pady=4)

        for icon_text, action in _GESTURES:
            row = ctk.CTkFrame(list_frame, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=icon_text, font=ctk.CTkFont(size=13),
                         anchor="w", width=120).pack(side="left")
            ctk.CTkLabel(row, text=action, font=ctk.CTkFont(size=13, weight="bold"),
                         text_color="#AAAAAA").pack(side="right")
