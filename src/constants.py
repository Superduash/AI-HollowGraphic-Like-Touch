from .models import GestureType

_OVERLAY_LABELS = {
    GestureType.NONE: "PAUSED",
    GestureType.MOVE: "MOVE",
    GestureType.LEFT_CLICK: "CLICK",
    GestureType.DOUBLE_CLICK: "DOUBLE",
    GestureType.RIGHT_CLICK: "RIGHT CLICK",
    GestureType.SCROLL: "SCROLL",
    GestureType.DRAG: "DRAG",
    GestureType.TASK_VIEW: "TASK VIEW",
    GestureType.PAUSE: "PAUSED",
    GestureType.KEYBOARD: "KEYBOARD",
    GestureType.MEDIA_VOL_UP: "VOL UP",
    GestureType.MEDIA_VOL_DOWN: "VOL DOWN",
    GestureType.MEDIA_NEXT: "NEXT TRACK",
    GestureType.MEDIA_PREV: "PREV TRACK",
}


_BADGE_COLORS = {
    GestureType.MOVE: "#60A5FA",
    GestureType.LEFT_CLICK: "#4ADE80",
    GestureType.RIGHT_CLICK: "#4ADE80",
    GestureType.DOUBLE_CLICK: "#4ADE80",
    GestureType.SCROLL: "#A78BFA",
    GestureType.DRAG: "#A78BFA",
    GestureType.TASK_VIEW: "#A78BFA",
    GestureType.PAUSE: "#F87171",
    GestureType.KEYBOARD: "#FBBF24",
    GestureType.MEDIA_VOL_UP: "#F472B6",
    GestureType.MEDIA_VOL_DOWN: "#F472B6",
    GestureType.MEDIA_NEXT: "#F472B6",
    GestureType.MEDIA_PREV: "#F472B6",
    GestureType.NONE: "#64748B",
}
