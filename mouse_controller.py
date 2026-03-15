"""
mouse_controller.py - Translate gesture results into mouse actions.

Uses PyAutoGUI for cross-platform mouse movement and click injection.
PyAutoGUI's built-in *FAILSAFE* (move to corner to abort) is intentionally
kept enabled for safety – moving the physical mouse to the top-left corner
of the screen will raise a ``pyautogui.FailSafeException`` and exit.
"""

import pyautogui

# Disable the animation delay in PyAutoGUI so moves feel instant.
# The smoothing is handled by our EMAFilter instead.
pyautogui.PAUSE = 0


class MouseController:
    """
    Executes mouse movements and click actions on the host operating system.

    The controller accepts already-smoothed screen coordinates produced by
    :class:`utils.EMAFilter`, so it does not perform additional smoothing
    itself.  Click events originate from :class:`gesture_detector.GestureDetector`.
    """

    def __init__(self):
        # Retrieve the current screen resolution at startup.
        # Stored for reference but not strictly required for the move calls.
        self.screen_w, self.screen_h = pyautogui.size()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def move(self, x, y):
        """
        Move the mouse cursor to an absolute screen position instantly.

        Args:
            x (int): Target X coordinate in screen pixels.
            y (int): Target Y coordinate in screen pixels.
        """
        # duration=0 makes the move instantaneous; our EMA provides smoothing
        pyautogui.moveTo(x, y, duration=0)

    def left_click(self):
        """Perform a single left mouse button click at the current position."""
        pyautogui.click(button="left")

    def right_click(self):
        """Perform a single right mouse button click at the current position."""
        pyautogui.click(button="right")

    def handle_gesture(self, screen_x, screen_y, left_click, right_click):
        """
        Convenience method: move cursor then fire any pending click events.

        Args:
            screen_x (int): Smoothed screen X coordinate.
            screen_y (int): Smoothed screen Y coordinate.
            left_click (bool): Whether a left-click event should fire.
            right_click (bool): Whether a right-click event should fire.
        """
        self.move(screen_x, screen_y)

        if left_click:
            self.left_click()

        if right_click:
            self.right_click()
