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
    VOLUME = "VOLUME"
    SWITCH_WINDOW = "SWITCH_WINDOW"
    OPEN_PALM = "OPEN_PALM"
