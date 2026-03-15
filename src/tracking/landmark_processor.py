"""Finger state detection and landmark helpers — O(1) per frame."""

# Landmark indices
THUMB_TIP = 4
THUMB_IP = 3
INDEX_MCP = 5
INDEX_PIP = 6
INDEX_TIP = 8
MIDDLE_PIP = 10
MIDDLE_TIP = 12
RING_PIP = 14
RING_TIP = 16
PINKY_PIP = 18
PINKY_TIP = 20


class FingerStates:
    """Boolean up/down state for each finger."""
    __slots__ = ("thumb", "index", "middle", "ring", "pinky")

    def __init__(self, thumb: bool, index: bool, middle: bool, ring: bool, pinky: bool) -> None:
        self.thumb = thumb
        self.index = index
        self.middle = middle
        self.ring = ring
        self.pinky = pinky

    @property
    def count(self) -> int:
        return self.thumb + self.index + self.middle + self.ring + self.pinky


def get_finger_states(landmarks: list[tuple[int, int]]) -> FingerStates:
    """Determine up/down state for each finger. O(1)."""
    # Thumb: extended when tip is farther from index_mcp than IP is
    # (orientation-independent, works for both hands)
    tt = landmarks[THUMB_TIP]
    ti = landmarks[THUMB_IP]
    im = landmarks[INDEX_MCP]
    dx1, dy1 = tt[0] - im[0], tt[1] - im[1]
    dx2, dy2 = ti[0] - im[0], ti[1] - im[1]
    thumb = (dx1 * dx1 + dy1 * dy1) > (dx2 * dx2 + dy2 * dy2)

    # Other fingers: tip.y < pip.y means extended (y increases downward)
    index = landmarks[INDEX_TIP][1] < landmarks[INDEX_PIP][1]
    middle = landmarks[MIDDLE_TIP][1] < landmarks[MIDDLE_PIP][1]
    ring = landmarks[RING_TIP][1] < landmarks[RING_PIP][1]
    pinky = landmarks[PINKY_TIP][1] < landmarks[PINKY_PIP][1]

    return FingerStates(thumb, index, middle, ring, pinky)


def get_index_tip(landmarks: list[tuple[int, int]]) -> tuple[int, int]:
    return landmarks[INDEX_TIP]


def get_thumb_tip(landmarks: list[tuple[int, int]]) -> tuple[int, int]:
    return landmarks[THUMB_TIP]


def get_middle_tip(landmarks: list[tuple[int, int]]) -> tuple[int, int]:
    return landmarks[MIDDLE_TIP]


def point_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def midpoint(a: tuple[int, int], b: tuple[int, int]) -> tuple[float, float]:
    return (0.5 * (a[0] + b[0]), 0.5 * (a[1] + b[1]))
