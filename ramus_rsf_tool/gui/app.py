"""
gui/app.py -- GUI entry point.

Usage:
    python3 -m ramus_rsf_tool.gui.app [FILE.rsf]
    ramus-rsf-gui [FILE.rsf]
"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from .main_window import MainWindow


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)

    app = QApplication(sys.argv[:1] + argv)
    app.setApplicationName("Ramus RSF Editor")
    app.setOrganizationName("ramus-rsf-tool")

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
