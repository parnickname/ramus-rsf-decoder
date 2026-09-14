"""
gui/app.py -- GUI entry point.

Usage:
    python3 -m ramus_rsf_tool.gui.app [FILE.rsf]
    ramus-rsf-gui [FILE.rsf]
"""
from __future__ import annotations

import pathlib
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from . import theme
from .main_window import MainWindow

_ICON_DIR = pathlib.Path(__file__).resolve().parent / "resources" / "icons"


def _load_app_icon() -> QIcon:
    """Собирает QIcon из PNG нескольких разрешений (packaging/icons/
    generate_icons.py). Работает и при запуске из исходников, и из сборки
    PyInstaller -- __file__ внутри onedir/onefile-сборки указывает на
    распакованную копию пакета, так что относительный путь не меняется.
    Значок из .ico/.icns самого exe/.app отвечает за панель задач/Dock;
    этот -- за иконку в заголовке окна на Linux и в Alt+Tab везде."""
    icon = QIcon()
    if _ICON_DIR.is_dir():
        for png in sorted(_ICON_DIR.glob("*.png")):
            icon.addFile(str(png))
    return icon


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    app = QApplication(sys.argv[:1] + argv)
    app.setApplicationName("Редактор Ramus RSF")
    app.setOrganizationName("ramus-rsf-tool")
    app.setWindowIcon(_load_app_icon())
    theme.apply_saved_theme(app)

    win = MainWindow()
    win.show()

    # first non-flag argument, if any, is a file to open on startup
    for a in argv:
        if not a.startswith("-"):
            win.open_path(a)
            break

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
