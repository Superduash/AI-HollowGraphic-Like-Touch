"""Unit tests for cursor mapper smoothing/deadzone behavior."""

from src.cursor_mapper import CursorMapper


def test_soft_deadzone_does_not_overshoot() -> None:
    mapper = CursorMapper(cam_w=100, cam_h=100)
    mapper.set_frame_margin(0)
    mapper.set_smoothening(1.0)

    sx0, sy0 = mapper.map_point(50, 50)

    # Small motion that typically falls within the soft deadzone.
    raw1x, raw1y = mapper._map_to_screen(51, 50)
    sx1, sy1 = mapper.map_point(51, 50)

    lo = min(float(sx0), float(raw1x))
    hi = max(float(sx0), float(raw1x))

    # Returned position must stay between previous and current raw (no overshoot).
    assert lo - 2.0 <= float(sx1) <= hi + 2.0
    assert abs(mapper._raw_x - float(raw1x)) < 1e-6


if __name__ == "__main__":
    test_soft_deadzone_does_not_overshoot()
    print("[SUCCESS] All cursor mapper tests passed!")
