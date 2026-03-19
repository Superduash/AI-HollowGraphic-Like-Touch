"""Windows Hover: holographic touch mouse entry point.

Designed for USB portability: one main Python file driving an integrated package.
"""

from __future__ import annotations

import os

# Keep OpenCV backend probing quiet in production startup logs.
os.environ.setdefault("OPENCV_LOG_LEVEL", "SILENT")
os.environ.setdefault("OPENCV_VIDEOIO_DEBUG", "0")

# Keep Qt/MediaPipe/TFLite startup logs quiet for end users.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
os.environ.setdefault("GLOG_minloglevel", "3")
os.environ.setdefault("ABSL_MIN_LOG_LEVEL", "3")

from PySide6.QtWidgets import QApplication

from src import MainWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
