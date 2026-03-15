"""Math helpers for landmark geometry (pure Python, no numpy)."""


def distance_between_points(a: tuple[int, int], b: tuple[int, int]) -> float:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return (dx * dx + dy * dy) ** 0.5


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))
