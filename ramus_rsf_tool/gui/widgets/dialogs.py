"""Модальные диалоги для структурных правок: новый элемент/квалификатор,
новый функциональный блок, клонирование квалификатора как диаграммы,
регистрация корня модели, новая стрелка."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QHBoxLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QDialogButtonBox, QCheckBox, QLabel,
    QMessageBox, QWidget, QGroupBox, QRadioButton, QButtonGroup,
)

from ...rsf_model import Model, argb, ArrowSide
from .common import ColorButton


def _qualifier_combo(model: Model, include_system: bool = True) -> QComboBox:
    combo = QComboBox()
    for qid, q in sorted(model.qualifiers.items(),
                          key=lambda kv: (kv[1].get("QUALIFIER_NAME") or "")):
        if q.get("QUALIFIER_SYSTEM") and not include_system:
            continue
        label = "%s (%d)" % (q.get("QUALIFIER_NAME") or "(без имени)", qid)
        combo.addItem(label, qid)
    return combo


class NewElementDialog(QDialog):
    """Добавить обычный элемент под выбранным квалификатором."""

    def __init__(self, model: Model, default_qualifier: Optional[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый элемент")
        self.model = model
        layout = QFormLayout(self)
        self.qual_combo = _qualifier_combo(model)
        if default_qualifier is not None:
            idx = self.qual_combo.findData(default_qualifier)
            if idx >= 0:
                self.qual_combo.setCurrentIndex(idx)
        self.name_edit = QLineEdit()
        layout.addRow("Квалификатор:", self.qual_combo)
        layout.addRow("Имя:", self.name_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return self.qual_combo.currentData(), self.name_edit.text()


class NewQualifierDialog(QDialog):
    """Создать пустой квалификатор (без набора атрибутов) -- для нового
    EAV-'класса', не связанного с функциональными блоками IDEF0, например,
    пользовательской таблицы-браузера. Используйте 'Клонировать
    квалификатор как диаграмму', если нужна новая страница диаграммы
    IDEF0."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый (пустой) квалификатор")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.system_check = QCheckBox("Системный квалификатор")
        layout.addRow("Имя:", self.name_edit)
        layout.addRow("", self.system_check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return self.name_edit.text(), self.system_check.isChecked()


class NewFunctionBoxDialog(QDialog):
    """Полная форма add_function_box(): имя, границы, цвета, шрифт,
    статус, тип -- для квалификатора, который уже несёт стандартный набор
    F_* (любой квалификатор, созданный через 'Клонировать квалификатор как
    диаграмму', или любой уже существующий квалификатор Function)."""

    def __init__(self, model: Model, default_qualifier: Optional[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новый функциональный блок")
        self.model = model
        layout = QFormLayout(self)

        self.qual_combo = _qualifier_combo(model, include_system=False)
        if default_qualifier is not None:
            idx = self.qual_combo.findData(default_qualifier)
            if idx >= 0:
                self.qual_combo.setCurrentIndex(idx)
        layout.addRow("Квалификатор (диаграмма):", self.qual_combo)

        self.name_edit = QLineEdit("Новая функция")
        layout.addRow("Имя:", self.name_edit)

        self.x = self._spin(-100000, 100000, 40)
        self.y = self._spin(-100000, 100000, 40)
        self.w = self._spin(1, 100000, 140)
        self.h = self._spin(1, 100000, 80)
        layout.addRow("X:", self.x)
        layout.addRow("Y:", self.y)
        layout.addRow("Ширина:", self.w)
        layout.addRow("Высота:", self.h)

        self.bg = ColorButton(argb(0, 255, 0))
        self.fg = ColorButton(argb(0, 0, 0))
        layout.addRow("Фон:", self.bg)
        layout.addRow("Передний план:", self.fg)

        self.font_name = QLineEdit("Dialog")
        self.font_size = QSpinBox()
        self.font_size.setRange(1, 400)
        self.font_size.setValue(12)
        layout.addRow("Название шрифта:", self.font_name)
        layout.addRow("Размер шрифта:", self.font_size)

        self.func_type = QSpinBox()
        self.func_type.setRange(-1000, 1000)
        self.func_type.setValue(3)
        self.func_type.setToolTip("F_TYPE; 3 = обычный функциональный блок во всех образцах файлов")
        layout.addRow("Тип функции:", self.func_type)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @staticmethod
    def _spin(lo, hi, default):
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setDecimals(1)
        sp.setValue(default)
        return sp

    def result_values(self):
        return dict(
            qualifier_id=self.qual_combo.currentData(),
            name=self.name_edit.text(),
            x=self.x.value(), y=self.y.value(), width=self.w.value(), height=self.h.value(),
            background=self.bg.value(), foreground=self.fg.value(),
            font_name=self.font_name.text(), font_size=self.font_size.value(),
            function_type=self.func_type.value(),
        )


class CloneQualifierDialog(QDialog):
    """clone_qualifier_as_container(): построить новую страницу диаграммы
    IDEF0, скопировав полный набор атрибутов существующего квалификатора
    Function."""

    def __init__(self, model: Model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая диаграмма из шаблона")
        layout = QFormLayout(self)
        self.source_combo = _qualifier_combo(model, include_system=False)
        self.name_edit = QLineEdit("Новая диаграмма")
        self.register_root = QCheckBox("Зарегистрировать как новую модель верхнего уровня (F_BASE_FUNCTIONS)")
        self.register_root.setChecked(True)
        layout.addRow("Скопировать набор атрибутов из:", self.source_combo)
        layout.addRow("Имя новой диаграммы:", self.name_edit)
        layout.addRow("", self.register_root)
        note = QLabel("Копирует каждый атрибут, который требует checkIDEF0Attributes() "
                       "в Ramus (Name, F_BOUNDS, F_BACKGROUND, ...), из выбранного "
                       "квалификатора на новый. См. RAMUS_RSF_FORMAT.md, раздел 9.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return dict(source_qualifier_id=self.source_combo.currentData(),
                    name=self.name_edit.text(),
                    register_root=self.register_root.isChecked())


class RegisterModelRootDialog(QDialog):
    """register_model_root(): пометить существующий квалификатор как
    корень модели верхнего уровня, направив на него новый учётный элемент
    F_BASE_FUNCTIONS. Требует, чтобы в файле уже был квалификатор
    F_BASE_FUNCTIONS с атрибутом F_BASE_FUNCTION_QUALIFIER_ID (верно для
    любого настоящего файла Ramus, и для файлов, начатых через Файл >
    Создать в этом приложении); 'Новая диаграмма из шаблона' делает это
    автоматически и является более простым путём для совершенно новой
    диаграммы."""

    def __init__(self, model: Model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Регистрация корня модели")
        layout = QFormLayout(self)
        self.qual_combo = _qualifier_combo(model, include_system=False)
        layout.addRow("Квалификатор для регистрации как корень:", self.qual_combo)
        note = QLabel("Добавляет новый элемент под системным квалификатором "
                       "F_BASE_FUNCTIONS, указывающий на выбранный квалификатор, "
                       "тем же способом, каким Ramus отмечает модель верхнего "
                       "уровня в своём навигаторе.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        layout.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return self.qual_combo.currentData()


_BOX_SIDES = [
    ("Input (слева)", ArrowSide.INPUT),
    ("Control (сверху)", ArrowSide.CONTROL),
    ("Output (справа)", ArrowSide.OUTPUT),
    ("Mechanism (снизу)", ArrowSide.MECHANISM),
]
_PAGE_SIDES = [
    ("Левый край", ArrowSide.LEFT),
    ("Верхний край", ArrowSide.TOP),
    ("Правый край", ArrowSide.RIGHT),
    ("Нижний край", ArrowSide.BOTTOM),
]


class EndpointPicker(QGroupBox):
    """Один конец новой стрелки: либо сторона функционального блока на
    текущей диаграмме, либо сторона самой страницы диаграммы (граничная
    стрелка, входящая на страницу или покидающая её извне)."""

    def __init__(self, title: str, model: Model, qualifier_id: int,
                 default_element: Optional[int] = None, parent=None):
        super().__init__(title, parent)
        self.model = model
        self.qualifier_id = qualifier_id
        layout = QVBoxLayout(self)

        self.box_radio = QRadioButton("Функциональный блок:")
        self.boundary_radio = QRadioButton("Граница страницы диаграммы:")
        self.box_radio.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.box_radio)
        group.addButton(self.boundary_radio)

        box_row = QHBoxLayout()
        self.elem_combo = QComboBox()
        for eid in model.elements_by_qualifier.get(qualifier_id, []):
            name = model.elements[eid].get("ELEMENT_NAME") or "(без имени)"
            self.elem_combo.addItem("%s (%d)" % (name, eid), eid)
        if default_element is not None:
            idx = self.elem_combo.findData(default_element)
            if idx >= 0:
                self.elem_combo.setCurrentIndex(idx)
        self.box_side_combo = QComboBox()
        for label, value in _BOX_SIDES:
            self.box_side_combo.addItem(label, value)
        box_row.addWidget(self.box_radio)
        box_row.addWidget(self.elem_combo, 1)
        box_row.addWidget(self.box_side_combo)

        boundary_row = QHBoxLayout()
        self.page_side_combo = QComboBox()
        for label, value in _PAGE_SIDES:
            self.page_side_combo.addItem(label, value)
        boundary_row.addWidget(self.boundary_radio)
        boundary_row.addWidget(self.page_side_combo)
        boundary_row.addStretch(1)

        layout.addLayout(box_row)
        layout.addLayout(boundary_row)

        self.box_radio.toggled.connect(self._sync_enabled)
        self._sync_enabled()

    def _sync_enabled(self):
        is_box = self.box_radio.isChecked()
        self.elem_combo.setEnabled(is_box)
        self.box_side_combo.setEnabled(is_box)
        self.page_side_combo.setEnabled(not is_box)

    def is_boundary(self) -> bool:
        return self.boundary_radio.isChecked()

    def element_and_side(self):
        return self.elem_combo.currentData(), self.box_side_combo.currentData()

    def page_side(self):
        return self.page_side_combo.currentData()


class NewArrowDialog(QDialog):
    """Добавить новую стрелку IDEF0 (Model.add_arrow() /
    add_boundary_arrow()): блок-к-блоку, либо блок-к-границе-страницы в
    любом направлении."""

    def __init__(self, model: Model, qualifier_id: int,
                 default_from: Optional[int] = None,
                 default_to: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Новая стрелка")
        self.model = model
        self.qualifier_id = qualifier_id
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.tunnel_check = QCheckBox("Туннелирована (не показывается на уровне родитель/потомок)")
        form.addRow("Подпись (необязательно):", self.name_edit)
        form.addRow("", self.tunnel_check)
        layout.addLayout(form)

        self.from_picker = EndpointPicker("Откуда", model, qualifier_id, default_from)
        self.to_picker = EndpointPicker("Куда", model, qualifier_id, default_to)
        layout.addWidget(self.from_picker)
        layout.addWidget(self.to_picker)

        note = QLabel(
            "Оба блока должны быть на одной диаграмме. Геометрия оставлена "
            "на усмотрение автоматической прокладки Ramus, как выглядит "
            "любая немодифицированная стрелка в реальном файле -- см. "
            "RAMUS_RSF_FORMAT.md, раздел 10.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if self.from_picker.is_boundary() and self.to_picker.is_boundary():
            QMessageBox.warning(self, "Не поддерживается",
                                 "Стрелка не может идти от границы страницы "
                                 "прямо к границе страницы -- хотя бы один "
                                 "конец должен быть функциональным блоком.")
            return
        if not self.from_picker.is_boundary() and self.from_picker.element_and_side()[0] is None:
            QMessageBox.warning(self, "Нет элементов", "На этой диаграмме пока нет блоков.")
            return
        if not self.to_picker.is_boundary() and self.to_picker.element_and_side()[0] is None:
            QMessageBox.warning(self, "Нет элементов", "На этой диаграмме пока нет блоков.")
            return
        self.accept()

    def result_values(self):
        """Возвращает словарь, готовый для передачи в Model.add_arrow()/
        add_boundary_arrow(): либо {'kind': 'arrow', 'from_element_id',
        'from_side', 'to_element_id', 'to_side', 'name', 'tunnel'}, либо
        {'kind': 'boundary', 'element_id', 'box_side', 'page_side',
        'direction', 'name', 'tunnel'}."""
        name = self.name_edit.text()
        tunnel = self.tunnel_check.isChecked()
        from_boundary = self.from_picker.is_boundary()
        to_boundary = self.to_picker.is_boundary()

        if not from_boundary and not to_boundary:
            from_eid, from_side = self.from_picker.element_and_side()
            to_eid, to_side = self.to_picker.element_and_side()
            return dict(kind="arrow", from_element_id=from_eid, from_side=from_side,
                        to_element_id=to_eid, to_side=to_side, name=name, tunnel=tunnel)

        if from_boundary:
            page_side = self.from_picker.page_side()
            box_eid, box_side = self.to_picker.element_and_side()
            direction = "in"
        else:
            page_side = self.to_picker.page_side()
            box_eid, box_side = self.from_picker.element_and_side()
            direction = "out"
        return dict(kind="boundary", element_id=box_eid, box_side=box_side,
                    page_side=page_side, direction=direction, name=name, tunnel=tunnel)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("О программе")
        layout = QVBoxLayout(self)
        from ... import __version__
        text = QLabel(
            "<h3>Редактор Ramus RSF</h3>"
            "<p>Версия %s</p>"
            "<p>Нативный GUI для Linux для чтения и редактирования файлов моделей "
            "IDEF0/DFD Ramus <code>.rsf</code>, построенный на реализации формата "
            "файла методом «чистой комнаты» (см. RAMUS_RSF_FORMAT.md).</p>"
            "<p>Не связано с проектом Ramus.</p>" % __version__)
        text.setWordWrap(True)
        text.setTextFormat(text.textFormat().RichText)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
