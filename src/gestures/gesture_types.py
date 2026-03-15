"""Gesture labels used across the application."""

from enum import Enum


class GestureType(str, Enum):
    NONE = "NONE"
    MOVE = "MOVE"
    LEFT_CLICK = "LEFT_CLICK"
    DOUBLE_CLICK = "DOUBLE_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    PAUSE = "PAUSE"
    TASK_VIEW = "TASK_VIEW"
    VOLUME = "VOLUME"
    SWITCH_WINDOW = "SWITCH_WINDOW"
    OPEN_PALM = "OPEN_PALM"
    KEYBOARD = "KEYBOARD"
    
    # Left-hand Media Controls
    MEDIA_VOL_UP = "MEDIA_VOL_UP"
    MEDIA_VOL_DOWN = "MEDIA_VOL_DOWN"
    MEDIA_NEXT = "MEDIA_NEXT"
    MEDIA_PREV = "MEDIA_PREV"


STATE_MACHINE_GESTURES = (
    GestureType.MOVE,
    GestureType.LEFT_CLICK,
    GestureType.RIGHT_CLICK,
    GestureType.SCROLL,
    GestureType.DRAG,
    GestureType.PAUSE,
    GestureType.KEYBOARD,
    GestureType.MEDIA_VOL_UP,
    GestureType.MEDIA_VOL_DOWN,
    GestureType.MEDIA_NEXT,
    GestureType.MEDIA_PREV,
)
