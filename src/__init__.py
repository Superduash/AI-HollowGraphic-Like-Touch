"""Windows Hover package exports."""

from .main_window import MainWindow


def _warmup_jit() -> None:
	"""Pre-compile Numba kernels on import so first gesture has no JIT delay."""
	try:
		from .fast_math import ema_step, pinch_dist_3d, pinch_dist_2d, clamp
		ema_step(0.0, 1.0, 0.5)
		pinch_dist_3d(0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
		pinch_dist_2d(0.0, 0.0, 1.0, 1.0)
		clamp(0.5, 0.0, 1.0)
	except Exception:
		pass


import threading as _threading
_threading.Thread(target=_warmup_jit, daemon=True).start()

__all__ = ["MainWindow"]
