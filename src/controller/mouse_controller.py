"""PyAutoGUI mouse commands with click cooldown protection."""

import time

import pyautogui

from config import CLICK_COOLDOWN_SECONDS


class MouseController:
    """Control mouse movement and clicks safely."""

    def __init__(self, click_cooldown_seconds: float = CLICK_COOLDOWN_SECONDS) -> None:
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0
        self.click_cooldown_seconds = click_cooldown_seconds
        self._last_left_click_time = 0.0
        self._last_right_click_time = 0.0
        self.is_available = True
        self.last_error_message = ""

    def _mark_unavailable(self, error: Exception) -> None:
        self.is_available = False
        self.last_error_message = str(error)

    def move_cursor(self, x: int, y: int) -> None:
        """Move cursor instantly to target screen position."""
        if not self.is_available:
            return

        try:
            pyautogui.moveTo(x, y)
        except Exception as error:
            self._mark_unavailable(error)

    def left_click(self) -> bool:
        """Trigger left click if cooldown has elapsed."""
        if not self.is_available:
            return False

        now = time.time()
        if now - self._last_left_click_time < self.click_cooldown_seconds:
            return False

        try:
            pyautogui.click(button="left")
        except Exception as error:
            self._mark_unavailable(error)
            return False

        self._last_left_click_time = now
        return True

    def right_click(self) -> bool:
        """Trigger right click if cooldown has elapsed."""
        if not self.is_available:
            return False

        now = time.time()
        if now - self._last_right_click_time < self.click_cooldown_seconds:
            return False

        try:
            pyautogui.click(button="right")
        except Exception as error:
            self._mark_unavailable(error)
            return False

        self._last_right_click_time = now
        return True
