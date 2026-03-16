"""Windows Hover: single-file Windows-optimized holographic touch mouse.

Designed for USB portability: one main Python file with merged camera, tracking,
gesture, cursor, and UI logic.
"""

from .ui import MainWindow

__all__ = ["MainWindow"]
