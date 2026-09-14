"""
Основная вкладка "Атрибуты": каждый атрибут, который несёт квалификатор
выбранного элемента, отрисовывается редактором, подходящим для его
объявленного типа (TYPE_MAP в rsf_model.py), и сразу же фиксируется
обратно в Model -- отдельного шага "Применить" нет.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLabel, QScrollArea, QLineEdit,
    QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QPlainTextEdit,
    QDialog, QDialogButtonBox, QMessageBox, QFileDialog, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ...rsf_model import Model, TYPE_MAP, TypeInfo, _guess_sql_types
from ...rsf_core import NULL
from .common import ColorButton
from .field_widgets import make_value_widget


class AttributeEditorPanel(QWidget):
    changed = pyqtSignal(str)             # kind: "name" | "value"
    openTableRequested = pyqtSignal(str)  # путь к таблице для перехода во вкладку "Сырые таблицы"

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model: Optional[Model] = None
        self.element_id: Optional[int] = None

        outer = QVBoxLayout(self)
        self.header = QLabel("Элемент не выбран.")
        self.header.setStyleSheet("font-weight: bold; padding: 4px;")
        outer.addWidget(self.header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self._body = QWidget()
        self.form = QFormLayout(self._body)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.scroll.setWidget(self._body)
        outer.addWidget(self.scroll, 1)

    # -- связывание --------------------------------------------------------
    def set_model(self, model: Optional[Model]):
        self.model = model
        self.set_element(None)

    def set_element(self, element_id: Optional[int]):
        self.element_id = element_id
        self.rebuild()

    # -- построение -----------------------------------------------------------
    def _clear_form(self):
        while self.form.rowCount():
            self.form.removeRow(0)

    def rebuild(self):
        self._clear_form()
        if self.model is None or self.element_id is None:
            self.header.setText("Элемент не выбран.")
            return
        e = self.model.elements.get(self.element_id)
        if e is None:
            self.header.setText("Элемент %s больше не существует." % self.element_id)
            return
        qid = e.get("QUALIFIER_ID")
        qname = self.model.qualifier_name(qid)
        self.header.setText("Элемент %d — %s   (квалификатор %s: %s)" %
                             (self.element_id, e.get("ELEMENT_NAME") or "(без имени)",
                              qid, qname))

        for aid in self._ordered_attribute_ids(qid):
            a = self.model.attributes.get(aid)
            if a is None:
                continue
            name = a.get("ATTRIBUTE_NAME") or ("attr_%d" % aid)
            plugin = a.get("ATTRIBUTE_TYPE_PLUGIN_NAME")
            typ = a.get("ATTRIBUTE_TYPE_NAME")
            atype = (plugin, typ)
            info = TYPE_MAP.get(atype)
            label = QLabel(name)
            label.setToolTip("id атрибута %d, тип %s.%s" % (aid, plugin, typ))
            row_widget = self._build_row(aid, atype, info)
            self.form.addRow(label, row_widget)

    def _ordered_attribute_ids(self, qid: int):
        rows = []
        if self.model.t_qual_attrs is not None:
            rows = self.model.t_qual_attrs.find_rows(QUALIFIER_ID=qid)
        if rows:
            rows = sorted(rows, key=lambda r: (r.get("ATTRIBUTE_POSITION") if
                                                isinstance(r.get("ATTRIBUTE_POSITION"), int)
                                                else 0))
            return [r["ATTRIBUTE_ID"] for r in rows]
        return list(self.model.qualifier_attribute_ids.get(qid, []))

    # -- построители строк для каждого атрибута --------------------------------
    def _build_row(self, aid: int, atype, info: Optional[TypeInfo]) -> QWidget:
        if info is None:
            w = QLabel("(для этого типа нет редактора -- используйте вкладку «Сырые таблицы»)")
            w.setStyleSheet("color: #888; font-style: italic;")
            return w

        if info.mode == "stream":
            return self._build_stream_row(aid, atype, info)
        if info.mode == "list":
            return self._build_list_row(aid, info)
        if info.mode == "scalar":
            return self._build_scalar_row(aid, atype, info)
        if info.mode == "struct":
            return self._build_struct_row(aid, atype, info)
        w = QLabel("(неизвестный режим %r)" % info.mode)
        return w

    def _column_sql_type(self, info: TypeInfo, column: str) -> str:
        t = self.model._vtable_or_none(info.table_path) if info.table_path else None
        if t is not None:
            for f in t.fields:
                if f.name.upper() == column.upper():
                    return f.type
        return _guess_sql_types([column]).get(column, "CLOB")

    def _commit_scalar(self, aid: int, value):
        self.model.set_value(self.element_id, aid, value)
        self._after_commit(aid)

    def _commit_struct_field(self, aid: int, column: str, value):
        self.model.set_value(self.element_id, aid, {column: value})
        self._after_commit(aid)

    def _after_commit(self, aid: int):
        a = self.model.attributes.get(aid, {})
        if a.get("ATTRIBUTE_NAME") == "Name":
            self.changed.emit("name")
        else:
            self.changed.emit("value")

    def _build_scalar_row(self, aid: int, atype, info: TypeInfo) -> QWidget:
        value = self.model.get_value(self.element_id, aid)
        column = info.columns[0]

        if atype == ("IDEF0", "Color"):
            btn = ColorButton(value if isinstance(value, int) else -16777216)
            btn.colorChanged.connect(lambda v, aid=aid: self._commit_scalar(aid, v))
            return btn

        if atype == ("Core", "Text") and self.model.attributes.get(aid, {}).get("ATTRIBUTE_NAME") == "Name":
            w = QLineEdit()
            w.setText(value or "")
            def commit_name(aid=aid, w=w):
                self.model.set_name(self.element_id, w.text())
                self._after_commit(aid)
            w.editingFinished.connect(commit_name)
            return w

        sql_type = self._column_sql_type(info, column)
        widget, getter = make_value_widget(sql_type, value)
        self._connect_commit(widget, lambda aid=aid, getter=getter: self._commit_scalar(aid, getter()))
        return widget

    def _build_struct_row(self, aid: int, atype, info: TypeInfo) -> QWidget:
        value = self.model.get_value(self.element_id, aid) or {}

        if atype == ("IDEF0", "FRectangle"):
            return self._build_bounds_row(aid, value)
        if atype == ("IDEF0", "Font"):
            return self._build_font_row(aid, value)
        if atype == ("IDEF0", "Status"):
            return self._build_status_row(aid, value)

        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        for col in info.columns:
            sub = QVBoxLayout()
            lab = QLabel(col)
            lab.setStyleSheet("color:#666; font-size: 10px;")
            sql_type = self._column_sql_type(info, col)
            widget, getter = make_value_widget(sql_type, value.get(col))
            self._connect_commit(
                widget, lambda aid=aid, col=col, getter=getter:
                    self._commit_struct_field(aid, col, getter()))
            sub.addWidget(lab)
            sub.addWidget(widget)
            wrap = QWidget()
            wrap.setLayout(sub)
            layout.addWidget(wrap)
        layout.addStretch(1)
        return box

    def _build_bounds_row(self, aid: int, value: dict) -> QWidget:
        from PyQt6.QtWidgets import QDoubleSpinBox
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        spins = {}
        for col, lbl in (("X", "X"), ("Y", "Y"), ("WIDTH", "Ш"), ("HEIGHT", "В")):
            layout.addWidget(QLabel(lbl + ":"))
            sp = QDoubleSpinBox()
            sp.setRange(-100000, 100000)
            sp.setDecimals(1)
            sp.setValue(float(value.get(col) or 0.0))
            sp.setFixedWidth(90)
            spins[col] = sp
            layout.addWidget(sp)

        def commit(col, sp=None):
            self._commit_struct_field(aid, col, spins[col].value())
        for col, sp in spins.items():
            sp.editingFinished.connect(lambda col=col: commit(col))
        layout.addStretch(1)
        return box

    def _build_font_row(self, aid: int, value: dict) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        name_edit = QLineEdit(value.get("NAME") or "Dialog")
        name_edit.setFixedWidth(120)
        bold = QCheckBox("Жирный")
        italic = QCheckBox("Курсив")
        style = int(value.get("STYLE") or 0)
        bold.setChecked(bool(style & 1))
        italic.setChecked(bool(style & 2))
        size = QSpinBox()
        size.setRange(1, 400)
        size.setValue(int(value.get("SIZE") or 12))

        def commit_name():
            self._commit_struct_field(aid, "NAME", name_edit.text())

        def commit_style():
            v = (1 if bold.isChecked() else 0) | (2 if italic.isChecked() else 0)
            self._commit_struct_field(aid, "STYLE", v)

        def commit_size():
            self._commit_struct_field(aid, "SIZE", size.value())

        name_edit.editingFinished.connect(commit_name)
        bold.stateChanged.connect(lambda _=None: commit_style())
        italic.stateChanged.connect(lambda _=None: commit_style())
        size.editingFinished.connect(commit_size)

        layout.addWidget(QLabel("Шрифт:"))
        layout.addWidget(name_edit)
        layout.addWidget(bold)
        layout.addWidget(italic)
        layout.addWidget(QLabel("Размер:"))
        layout.addWidget(size)
        layout.addStretch(1)
        return box

    _STATUS_LABELS = {0: "0 - Не начато / обычный"}

    def _build_status_row(self, aid: int, value: dict) -> QWidget:
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        type_spin = QSpinBox()
        type_spin.setRange(-1000, 1000)
        type_spin.setValue(int(value.get("TYPE") or 0))
        type_spin.setToolTip("Код TYPE статуса (0 = Не начато / обычный, встречается на "
                              "каждом обычном блоке в образцах файлов; прочие значения не "
                              "каталогизированы -- см. RAMUS_RSF_FORMAT.md, раздел 8)")
        other = QLineEdit(value.get("OTHER_NAME") or "")

        def commit_type():
            self._commit_struct_field(aid, "TYPE", type_spin.value())

        def commit_other():
            self._commit_struct_field(aid, "OTHER_NAME", other.text())

        type_spin.editingFinished.connect(commit_type)
        other.editingFinished.connect(commit_other)

        layout.addWidget(QLabel("Тип:"))
        layout.addWidget(type_spin)
        layout.addWidget(QLabel("Другое имя:"))
        layout.addWidget(other)
        layout.addStretch(1)
        return box

    def _connect_commit(self, widget: QWidget, fn):
        if isinstance(widget, QLineEdit):
            widget.editingFinished.connect(fn)
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(lambda _=None: fn())
        elif hasattr(widget, "editingFinished"):
            widget.editingFinished.connect(fn)
        elif hasattr(widget, "valueChanged"):
            widget.valueChanged.connect(lambda _=None: fn())
        # у байтового виджета (простой контейнер QWidget) нет естественного
        # сигнала "commit" -- кнопки Импорт/Экспорт/Очистить внутри него
        # напрямую изменяют общий словарь; подключать периодическую фиксацию
        # через focus-out здесь непрактично, поэтому байтовые столбцы
        # фиксируются немедленно при каждом действии кнопки (см.
        # field_widgets._make_bytes_widget).

    def _build_list_row(self, aid: int, info: TypeInfo) -> QWidget:
        rows = self.model.get_value(self.element_id, aid)
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("строк: %d -- атрибут-список, редактируется в «Сырых таблицах»:" % len(rows)))
        btn = QPushButton(info.table_path.rsplit("/", 1)[-1])
        btn.clicked.connect(lambda: self.openTableRequested.emit(info.table_path))
        layout.addWidget(btn)
        layout.addStretch(1)
        return box

    def _build_stream_row(self, aid: int, atype, info: TypeInfo) -> QWidget:
        value = self.model.get_value(self.element_id, aid)
        box = QWidget()
        layout = QHBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        n = len(value) if value else 0
        label = QLabel("<%d байт>" % n if value else "(не задано)")

        def refresh_label(v):
            label.setText("<%d байт>" % len(v) if v else "(не задано)")

        def do_import():
            path, _ = QFileDialog.getOpenFileName(box, "Импорт файла")
            if not path:
                return
            with open(path, "rb") as f:
                data = f.read()
            self.model.set_value(self.element_id, aid, data)
            refresh_label(data)
            self._after_commit(aid)

        def do_export():
            v = self.model.get_value(self.element_id, aid)
            if not v:
                QMessageBox.information(box, "Экспорт", "Нечего экспортировать.")
                return
            path, _ = QFileDialog.getSaveFileName(box, "Экспорт файла")
            if not path:
                return
            with open(path, "wb") as f:
                f.write(v)

        def do_clear():
            self.model.set_value(self.element_id, aid, None)
            refresh_label(b"")
            self._after_commit(aid)

        def do_edit_text():
            v = self.model.get_value(self.element_id, aid) or b""
            text = v.decode("utf-8", errors="replace")
            dlg = _TextEditDialog(text, box)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                data = dlg.text().encode("utf-8")
                self.model.set_value(self.element_id, aid, data)
                refresh_label(data)
                self._after_commit(aid)

        import_btn = QPushButton("Импорт…")
        export_btn = QPushButton("Экспорт…")
        clear_btn = QPushButton("Очистить")
        import_btn.clicked.connect(do_import)
        export_btn.clicked.connect(do_export)
        clear_btn.clicked.connect(do_clear)
        layout.addWidget(label)
        layout.addWidget(import_btn)
        layout.addWidget(export_btn)
        layout.addWidget(clear_btn)
        if atype == ("Core", "HTMLText"):
            edit_btn = QPushButton("Редактировать как текст…")
            edit_btn.clicked.connect(do_edit_text)
            layout.addWidget(edit_btn)
        layout.addStretch(1)
        return box


class _TextEditDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Редактирование содержимого потока")
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        layout.addWidget(self.edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.edit.toPlainText()
