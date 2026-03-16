"""Windows Hover: holographic touch mouse entry point.

Designed for USB portability: one main Python file driving an integrated package.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from src import MainWindow


def main() -> None:
    app = QApplication.instance() or QApplication([])
    w = MainWindow()
    w.show()
    app.exec()


if __name__ == "__main__":
    main()
