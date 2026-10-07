import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from app.gui import MainWindow


def resource_path(relative_path: str):
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / relative_path
    return Path(relative_path)


def run():
    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(str(resource_path("app/assets/icons/ticket-it-logo.ico"))))

    theme_path = resource_path("app/theme.qss")
    if theme_path.exists():
        app.setStyleSheet(theme_path.read_text(encoding="utf-8"))

    window = MainWindow()
    window.showMaximized()

    sys.exit(app.exec())
