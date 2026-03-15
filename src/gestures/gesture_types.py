"""Gesture labels used across the application."""

from enum import Enum


class GestureType(str, Enum):
    NONE = "NONE"
    MOVE_CURSOR = "MOVE_CURSOR"
    LEFT_CLICK = "LEFT_CLICK"
    RIGHT_CLICK = "RIGHT_CLICK"
