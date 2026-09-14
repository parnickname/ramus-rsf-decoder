"""Небольшие переиспользуемые виджеты/вспомогательные функции, общие для всех панелей GUI."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QPushButton, QColorDialog
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal

from ...rsf_model import argb, unpack_argb


class ColorButton(QPushButton):
    """Кнопка, показывающая образец цвета и хранящая упакованное целое
    ARGB в стиле Ramus/Java (см. rsf_model.argb / unpack_argb). Клик
    открывает выбор цвета; colorChanged(int) срабатывает с новым
    упакованным значением."""

    colorChanged = pyqtSignal(int)

    def __init__(self, value: int = -16777216, parent=None):
        super().__init__(parent)
        self._value = value
        self.setFixedWidth(56)
        self.clicked.connect(self._pick)
        self._refresh()

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        self._value = value
        self._refresh()

    def _refresh(self):
        r, g, b, a = unpack_argb(self._value)
        self.setText("")
        self.setStyleSheet(
            "QPushButton { background-color: rgba(%d,%d,%d,%d); "
            "border: 1px solid #888; }" % (r, g, b, a))
        self.setToolTip("RGBA %d,%d,%d,%d  (упаковано %d)" % (r, g, b, a, self._value))

    def _pick(self):
        r, g, b, a = unpack_argb(self._value)
        initial = QColor(r, g, b, a)
        color = QColorDialog.getColor(
            initial, self, "Выберите цвет",
            QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._value = argb(color.red(), color.green(), color.blue(), color.alpha())
            self._refresh()
            self.colorChanged.emit(self._value)


def sql_type_of(field_type: str) -> str:
    return (field_type or "").lower()


def coerce_for_field(text: str, field_type: str):
    """Наилучшая попытка разобрать правку ячейки таблицы (обычная строка
    из QTableWidgetItem) в значение Python, которое ожидает
    rsf_core.Table._encode() для этого SQL-типа. Бросает ValueError при
    некорректном вводе."""
    from ...rsf_core import NULL
    t = sql_type_of(field_type)
    if text == "":
        return ""
    if text is None:
        return NULL
    if t in ("integer", "int4", "long", "bigint", "int8"):
        return int(text)
    if t in ("bool", "boolean"):
        return text.strip().upper() in ("TRUE", "1", "YES")
    if t in ("double", "float8"):
        return float(text)
    if t in ("blob", "varbinary", "bytea"):
        # принимаем обычные hex-пары, введённые пользователем; сохранённые
        # байты -- это то, во что они декодируются после повторного
        # кодирования через Table._encode
        from ...rsf_core import rsf_hex_to_bytes
        return rsf_hex_to_bytes(text)
    return text


def display_value(value) -> str:
    from ...rsf_core import NULL
    if value is NULL or value is None:
        return ""
    if isinstance(value, bytes):
        return "<%d байт>" % len(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)
