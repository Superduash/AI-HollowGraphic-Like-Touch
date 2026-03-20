"""Windows Hover: holographic touch mouse entry point.

Designed for USB portability: one main Python file driving an integrated package.
"""

from __future__ import annotations

import os
from pathlib import Path

# Keep OpenCV backend probing quiet in production startup logs.
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

# Keep Qt/MediaPipe/TFLite startup logs quiet for end users.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("ABSL_MIN_LOG_LEVEL", "3")

from PySide6.QtGui import QIcon  # type: ignore
from PySide6.QtWidgets import QApplication  # type: ignore
from src import MainWindow  # type: ignore


def main() -> None:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication([])
    icon_path = Path(__file__).resolve().parent / "assets" / "icons" / "holographic_touch.svg"
    app_icon = QIcon(str(icon_path))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
