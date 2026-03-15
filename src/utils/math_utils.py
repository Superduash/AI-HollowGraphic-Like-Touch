"""Math helpers for landmark geometry."""

from typing import Tuple


Point = Tuple[float, float]


def distance_between_points(point_a: Point, point_b: Point) -> float:
    """Return Euclidean distance between two 2D points."""
    dx = point_a[0] - point_b[0]
    dy = point_a[1] - point_b[1]
    return (dx * dx + dy * dy) ** 0.5


def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp value into the inclusive [min_value, max_value] range."""
    return max(min_value, min(value, max_value))
