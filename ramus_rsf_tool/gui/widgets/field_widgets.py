"""
Обобщённые построители "одно SQL-значение <-> один виджет", используемые
для отрисовки как скалярных атрибутов, так и отдельных столбцов struct-
атрибутов без жёсткого закрепления виджета за именем атрибута. Горстка
хорошо известных типов атрибутов IDEF0 (Color, FRectangle, Font)
получает более приятные выделенные виджеты в attribute_editor.py; всё
остальное -- включая таблицы стрелок/"Sector", которые набор инструментов
намеренно считает непрозрачными (RAMUS_RSF_FORMAT.md, раздел 10) --
сводится к этим построителям, так что каждый столбец в файле остаётся
доступным для чтения и редактирования из GUI даже без знания,
специфичного для типа.
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
    """Построить (виджет, геттер). getter() читает текущее значение
    виджета, уже приведённое к тому, что ожидает rsf_core.Table._encode."""
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
        # столбцы BIGINT могут превышать 32-битный диапазон QIntValidator в
        # Qt (id элементов/атрибутов и т. п.), поэтому проверяем нестрого
        # (цифры + необязательный знак) и разбираем обычным int(), не
        # ограничивая сам виджет.
        w = QLineEdit()
        w.setValidator(QRegularExpressionValidator(QRegularExpression(r"-?\d*")))
        w.setText(str(value) if isinstance(value, int) else "")
        def get_int():
            txt = w.text().strip()
            return int(txt) if txt and txt != "-" else 0
        return w, get_int

    if t in ("blob", "varbinary", "bytea"):
        return _make_bytes_widget(value)

    # CLOB/CHAR/TEXT/bpchar/TIMESTAMP/неизвестный -> обычный текст
    w = QLineEdit()
    w.setText("" if value in (None, NULL) else str(value))
    return w, (lambda: w.text())


def _make_bytes_widget(value) -> Tuple[QWidget, Callable[[], Any]]:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    state = {"value": value if isinstance(value, (bytes, bytearray)) else b""}
    label = QLabel("<%d байт>" % len(state["value"]))
    load_btn = QPushButton("Импорт…")
    save_btn = QPushButton("Экспорт…")
    clear_btn = QPushButton("Очистить")

    def do_load():
        path, _ = QFileDialog.getOpenFileName(container, "Импорт байт из файла")
        if not path:
            return
        with open(path, "rb") as f:
            state["value"] = f.read()
        label.setText("<%d байт>" % len(state["value"]))

    def do_save():
        if not state["value"]:
            QMessageBox.information(container, "Экспорт", "Нет данных для экспорта.")
            return
        path, _ = QFileDialog.getSaveFileName(container, "Экспорт байт в файл")
        if not path:
            return
        with open(path, "wb") as f:
            f.write(state["value"])

    def do_clear():
        state["value"] = b""
        label.setText("<0 байт>")

    load_btn.clicked.connect(do_load)
    save_btn.clicked.connect(do_save)
    clear_btn.clicked.connect(do_clear)
    layout.addWidget(label)
    layout.addWidget(load_btn)
    layout.addWidget(save_btn)
    layout.addWidget(clear_btn)
    layout.addStretch(1)
    return container, (lambda: state["value"])
