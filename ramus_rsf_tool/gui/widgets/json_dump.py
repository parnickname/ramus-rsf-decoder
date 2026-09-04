"""
The "JSON Dump" tab: dump_model() rendered as editable text, with export
and a matching re-import. The intended workflow this exists for is:

    Export to file... -> redact/edit the text elsewhere -> Import from
    file... (or paste the edited JSON directly into the box and hit
    Apply edited text) -> File > Save.

Import is a *patch*, not a replace -- see rsf_model.apply_json_dump()'s
docstring for exactly what it will and won't touch (in short: only values
of qualifiers/elements that already exist, matched by id; nothing is ever
added or removed by this).
"""
from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton,
    QCheckBox, QFileDialog, QMessageBox, QLabel,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal

from ...rsf_model import Model, dump_model, apply_json_dump


class JsonDumpPanel(QWidget):
    modelChanged = pyqtSignal()  # emitted after a successful import/apply

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model: Optional[Model] = None

        outer = QVBoxLayout(self)

        top = QHBoxLayout()
        self.include_system = QCheckBox("Include system qualifiers/attributes")
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setToolTip("Regenerate this box from the current model "
                                     "(discards any unapplied edits below).")
        self.export_btn = QPushButton("Export to file…")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self._export)
        top.addWidget(self.include_system)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.export_btn)
        top.addStretch(1)
        outer.addLayout(top)

        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Redact/edit the exported JSON, then:"))
        self.import_btn = QPushButton("Import from file…")
        self.import_btn.setToolTip("Load a JSON file and apply it to the model.")
        self.apply_btn = QPushButton("Apply edited text below")
        self.apply_btn.setToolTip("Apply whatever JSON is currently in the box "
                                   "below to the model (for edits made directly here).")
        self.import_btn.clicked.connect(self._import_from_file)
        self.apply_btn.clicked.connect(self._apply_text)
        import_row.addWidget(self.import_btn)
        import_row.addWidget(self.apply_btn)
        import_row.addStretch(1)
        outer.addLayout(import_row)

        self.text = QPlainTextEdit()
        self.text.setFont(QFont("Monospace"))
        self.text.setToolTip("Editable -- paste or edit redacted JSON here, then "
                              "'Apply edited text below'.")
        outer.addWidget(self.text, 1)

    # -- wiring --------------------------------------------------------
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

    # -- import ------------------------------------------------------------
    def _import_from_file(self):
        if self.model is None:
            QMessageBox.information(self, "No file", "Open or create a file first.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import JSON dump", "",
                                               "JSON files (*.json);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as ex:
            QMessageBox.critical(self, "Import failed", str(ex))
            return
        self.text.setPlainText(text)
        self._apply_text()

    def _apply_text(self):
        if self.model is None:
            QMessageBox.information(self, "No file", "Open or create a file first.")
            return
        try:
            data = json.loads(self.text.toPlainText())
        except json.JSONDecodeError as ex:
            QMessageBox.critical(self, "Invalid JSON", "Could not parse the JSON:\n%s" % ex)
            return
        if not isinstance(data, dict) or "qualifiers" not in data:
            QMessageBox.critical(self, "Invalid JSON",
                                  "This doesn't look like a JSON dump from this app "
                                  "(expected a top-level {\"qualifiers\": [...]} object).")
            return

        result = apply_json_dump(self.model, data)

        detail = ""
        if result.warnings:
            shown = result.warnings[:25]
            detail = "\n".join(shown)
            if len(result.warnings) > len(shown):
                detail += "\n... and %d more" % (len(result.warnings) - len(shown))

        box = QMessageBox(self)
        box.setWindowTitle("Import applied")
        box.setText(result.summary())
        if detail:
            box.setDetailedText(detail)
        box.setIcon(QMessageBox.Icon.Information if not result.warnings
                    else QMessageBox.Icon.Warning)
        box.exec()

        if (result.qualifiers_updated or result.elements_updated or result.values_updated):
            self.modelChanged.emit()
        else:
            self.refresh()
