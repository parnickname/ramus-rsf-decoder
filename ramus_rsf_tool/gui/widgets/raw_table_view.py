"""
Вкладка "Сырые таблицы": обобщённое табличное представление *любой*
таблицы в архиве (data/**/*.xml), включая те, у которых нет семантического
отображения в TYPE_MAP -- это аварийный люк, на который указывает
RAMUS_RSF_FORMAT.md для редактирования стрелок/секторов и всего прочего,
что не покрыто вкладкой "Атрибуты".
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QMessageBox, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...rsf_model import Model
from ...rsf_core import NULL, Table
from .common import coerce_for_field, display_value


class RawTablesPanel(QWidget):
    modelStructureChanged = pyqtSignal()  # пользователь нажал "Переиндексировать" -- дерево и т.д. должны обновиться

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model: Optional[Model] = None
        self._current_path: Optional[str] = None
        self._loading = False

        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Таблица:"))
        self.combo = QComboBox()
        self.combo.setMinimumWidth(360)
        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        top.addWidget(self.combo, 1)
        self.add_row_btn = QPushButton("Добавить строку")
        self.del_row_btn = QPushButton("Удалить строк(и)")
        self.reindex_btn = QPushButton("Переиндексировать модель")
        self.reindex_btn.setToolTip(
            "Заново вывести индексы квалификаторов/элементов/атрибутов из "
            "сырых таблиц (вызывайте после правки ID здесь, чтобы остальной "
            "GUI увидел изменение).")
        self.add_row_btn.clicked.connect(self._add_row)
        self.del_row_btn.clicked.connect(self._delete_selected_rows)
        self.reindex_btn.clicked.connect(self._reindex)
        top.addWidget(self.add_row_btn)
        top.addWidget(self.del_row_btn)
        top.addWidget(self.reindex_btn)
        outer.addLayout(top)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.itemChanged.connect(self._on_item_changed)
        outer.addWidget(self.table, 1)

        self.info = QLabel("")
        self.info.setStyleSheet("color: #888;")
        outer.addWidget(self.info)

    # -- связывание --------------------------------------------------------
    def set_model(self, model: Optional[Model]):
        self.model = model
        self._refresh_combo()

    def show_table(self, path: str):
        idx = self.combo.findData(path)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)

    def _refresh_combo(self):
        self._loading = True
        self.combo.clear()
        if self.model is not None:
            for path in self.model.table_paths():
                n = len(self.model.table(path).rows)
                self.combo.addItem("%s  (%d строк)" % (path, n), path)
        self._loading = False
        if self.combo.count():
            self.combo.setCurrentIndex(0)
        else:
            self._current_path = None
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

    def _on_combo_changed(self, idx: int):
        if self._loading:
            return
        path = self.combo.currentData()
        self._load_table(path)

    def _current_table(self) -> Optional[Table]:
        if self.model is None or self._current_path is None:
            return None
        return self.model.table(self._current_path)

    def _load_table(self, path: Optional[str]):
        self._current_path = path
        self._loading = True
        self.table.clear()
        if path is None or self.model is None:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self._loading = False
            return
        t = self.model.table(path)
        cols = t.field_names()
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(
            ["%s (%s)" % (c, f.type) for c, f in zip(cols, t.fields)])
        self.table.setRowCount(len(t.rows))
        for r, row in enumerate(t.rows):
            for c, col in enumerate(cols):
                val = row.get(col.upper(), NULL)
                item = QTableWidgetItem(display_value(val))
                self.table.setItem(r, c, item)
        self.table.resizeColumnsToContents()
        self._loading = False
        self.info.setText("%s -- %d строк, %d столбцов. Пустое NULL и пустая строка "
                           "здесь не различаются: оставьте ячейку пустой, чтобы "
                           "записать пустую строку." % (path, len(t.rows), len(cols)))

    # -- редактирование ---------------------------------------------------------
    def _on_item_changed(self, item: QTableWidgetItem):
        if self._loading:
            return
        t = self._current_table()
        if t is None:
            return
        r, c = item.row(), item.column()
        if r >= len(t.rows):
            return
        col = t.field_names()[c]
        fld = t.fields[c]
        try:
            value = coerce_for_field(item.text(), fld.type)
        except ValueError as ex:
            QMessageBox.warning(self, "Некорректное значение", str(ex))
            self._loading = True
            item.setText(display_value(t.rows[r].get(col.upper(), NULL)))
            self._loading = False
            return
        t.rows[r][col.upper()] = value
        self._notify_dirty()

    def _add_row(self):
        t = self._current_table()
        if t is None:
            return
        t.rows.append({})
        self._load_table(self._current_path)
        self._notify_dirty()

    def _delete_selected_rows(self):
        t = self._current_table()
        if t is None:
            return
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        for r in rows:
            if 0 <= r < len(t.rows):
                del t.rows[r]
        self._load_table(self._current_path)
        self._notify_dirty()

    def _reindex(self):
        if self.model is None:
            return
        self.model.refresh()
        self._refresh_combo()
        self.modelStructureChanged.emit()

    def _notify_dirty(self):
        # передаём наверх по тому же каналу, что использует редактор атрибутов
        w = self.window()
        if hasattr(w, "mark_dirty"):
            w.mark_dirty()
