"""
Generic "one SQL value <-> one widget" builders, used to render both
scalar attributes and the individual columns of struct attributes without
hardcoding a widget per attribute name. A handful of well-known IDEF0
attribute types (Color, FRectangle, Font) get nicer dedicated widgets in
attribute_editor.py; everything else -- including the arrow/"Sector"
tables the toolkit deliberately treats as opaque (RAMUS_RSF_FORMAT.md
section 10) -- falls back to these, so every column in the file remains
readable and editable from the GUI even without type-specific knowledge.
"""
from __future__ import annotations

from typing import Any, Callable, Tuple

from PyQt6.QtWidgets import (
    QWidget, QLineEdit, QCheckBox, QDoubleSpinBox, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox,
)
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtCore import QRegularExpression

from ...rsf_core import NULL


def _sql_type(t: str) -> str:
    return (t or "").lower()


def make_value_widget(sql_type: str, value: Any) -> Tuple[QWidget, Callable[[], Any]]:
    """Build (widget, getter). getter() reads the widget's current value,
    already coerced to what rsf_core.Table._encode expects."""
    t = _sql_type(sql_type)

    if t in ("bool", "boolean"):
        w = QCheckBox()
        w.setChecked(bool(value) if value not in (None, NULL) else False)
        return w, (lambda: w.isChecked())

    if t in ("double", "float8"):
        w = QDoubleSpinBox()
        w.setRange(-1e12, 1e12)
        w.setDecimals(4)
        w.setValue(float(value) if isinstance(value, (int, float)) else 0.0)
        return w, (lambda: w.value())

    if t in ("integer", "int4", "long", "bigint", "int8"):
        # BIGINT columns can exceed Qt's 32-bit QIntValidator range (element/
        # attribute ids, etc.), so validate loosely (digits + optional sign)
        # and parse with plain int() rather than constraining the widget.
        w = QLineEdit()
        w.setValidator(QRegularExpressionValidator(QRegularExpression(r"-?\d*")))
        w.setText(str(value) if isinstance(value, int) else "")
        def get_int():
            txt = w.text().strip()
            return int(txt) if txt and txt != "-" else 0
        return w, get_int

    if t in ("blob", "varbinary", "bytea"):
        return _make_bytes_widget(value)

    # CLOB/CHAR/TEXT/bpchar/TIMESTAMP/unknown -> plain text
    w = QLineEdit()
    w.setText("" if value in (None, NULL) else str(value))
    return w, (lambda: w.text())


def _make_bytes_widget(value) -> Tuple[QWidget, Callable[[], Any]]:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    state = {"value": value if isinstance(value, (bytes, bytearray)) else b""}
    label = QLabel("<%d bytes>" % len(state["value"]))
    load_btn = QPushButton("Import…")
    save_btn = QPushButton("Export…")
    clear_btn = QPushButton("Clear")

    def do_load():
        path, _ = QFileDialog.getOpenFileName(container, "Import bytes from file")
        if not path:
            return
        with open(path, "rb") as f:
            state["value"] = f.read()
        label.setText("<%d bytes>" % len(state["value"]))

    def do_save():
        if not state["value"]:
            QMessageBox.information(container, "Export", "No data to export.")
            return
        path, _ = QFileDialog.getSaveFileName(container, "Export bytes to file")
        if not path:
            return
        with open(path, "wb") as f:
            f.write(state["value"])

    def do_clear():
        state["value"] = b""
        label.setText("<0 bytes>")

    load_btn.clicked.connect(do_load)
    save_btn.clicked.connect(do_save)
    clear_btn.clicked.connect(do_clear)
    layout.addWidget(label)
    layout.addWidget(load_btn)
    layout.addWidget(save_btn)
    layout.addWidget(clear_btn)
    layout.addStretch(1)
    return container, (lambda: state["value"])
