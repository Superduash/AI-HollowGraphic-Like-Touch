from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class GestureType(str, Enum):
    NONE = "NONE"
    MOVE = "MOVE"
    LEFT_CLICK = "LEFT CLICK"
    RIGHT_CLICK = "RIGHT CLICK"
    DOUBLE_CLICK = "DOUBLE CLICK"
    SCROLL = "SCROLL"
    DRAG = "DRAG"
    TASK_VIEW = "TASK VIEW"
    PAUSE = "PAUSED"
    KEYBOARD = "KEYBOARD"
    MEDIA_VOL_UP = "MEDIA_VOL_UP"
    MEDIA_VOL_DOWN = "MEDIA_VOL_DOWN"
    MEDIA_NEXT = "MEDIA_NEXT"
    MEDIA_PREV = "MEDIA_PREV"


@dataclass
class GestureResult:
    gesture: GestureType = GestureType.NONE
    scroll_delta: int = 0

    @property
    def value(self) -> int:
        return self.scroll_delta


@dataclass
class FingerStates:
    thumb: bool
    index: bool
    middle: bool
    ring: bool
    pinky: bool
