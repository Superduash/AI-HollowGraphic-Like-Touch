"""Entry point for AI-HollowGraphic-Like-Touch desktop application."""

from PySide6.QtWidgets import QApplication

from gui.main_window import MainWindow


def run() -> None:
    qt_app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    qt_app.exec()


if __name__ == "__main__":
    run()
