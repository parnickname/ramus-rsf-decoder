"""The "JSON Dump" tab: dump_model() rendered as text, with export."""
from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QCheckBox, QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QFont

from ...rsf_model import Model, dump_model


class JsonDumpPanel(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model: Optional[Model] = None

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.include_system = QCheckBox("Include system qualifiers/attributes")
        self.refresh_btn = QPushButton("Refresh")
        self.export_btn = QPushButton("Export to file…")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self._export)
        top.addWidget(self.include_system)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.export_btn)
        top.addStretch(1)
        outer.addLayout(top)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Monospace"))
        outer.addWidget(self.text, 1)

    def set_model(self, model: Optional[Model]):
        self.model = model
        self.refresh()

    def refresh(self):
        if self.model is None:
            self.text.setPlainText("")
            return
        data = dump_model(self.model, include_system_qualifiers=self.include_system.isChecked())
        self.text.setPlainText(json.dumps(data, ensure_ascii=False, default=str, indent=2))

    def _export(self):
        if self.model is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export JSON dump", "dump.json",
                                               "JSON files (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())
        except OSError as ex:
            QMessageBox.critical(self, "Export failed", str(ex))
