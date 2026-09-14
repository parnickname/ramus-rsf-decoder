from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget, QVBoxLayout, QMessageBox,
    QFileDialog, QInputDialog, QLineEdit, QToolBar, QCheckBox, QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QCloseEvent

from ..rsf_model import Model
from ..rsf_core import RsfArchive
from .. import template
from .widgets.qualifier_tree import QualifierTree
from .widgets.attribute_editor import AttributeEditorPanel
from .widgets.raw_table_view import RawTablesPanel
from .widgets.json_dump import JsonDumpPanel
from .widgets.dialogs import (
    NewElementDialog, NewQualifierDialog, NewFunctionBoxDialog,
    CloneQualifierDialog, RegisterModelRootDialog, NewArrowDialog, AboutDialog,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Редактор Ramus RSF")
        self.resize(1200, 800)

        self.model: Optional[Model] = None
        self.current_path: Optional[str] = None
        self.dirty: bool = False
        self._current_qid: Optional[int] = None
        self._current_eid: Optional[int] = None

        self._build_ui()
        self._build_menus()
        self._apply_model_to_panels()
        self._update_title()

    # -- построение интерфейса ---------------------------------------------
    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.show_system_check = QCheckBox("Показывать системные квалификаторы")
        self.show_system_check.stateChanged.connect(self._on_show_system_toggled)
        self.tree = QualifierTree()
        self.tree.elementSelected.connect(self._on_tree_selection)
        left_layout.addWidget(self.show_system_check)
        left_layout.addWidget(self.tree, 1)
        splitter.addWidget(left)

        self.tabs = QTabWidget()
        self.attr_panel = AttributeEditorPanel()
        self.attr_panel.changed.connect(self._on_attr_changed)
        self.attr_panel.openTableRequested.connect(self._open_table_tab)
        self.raw_panel = RawTablesPanel()
        self.raw_panel.modelStructureChanged.connect(self._on_structure_changed)
        self.json_panel = JsonDumpPanel()
        self.json_panel.modelChanged.connect(self._on_structure_changed)
        self.tabs.addTab(self.attr_panel, "Атрибуты")
        self.tabs.addTab(self.raw_panel, "Сырые таблицы")
        self.tabs.addTab(self.json_panel, "JSON-дамп")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 880])

        self.setCentralWidget(splitter)
        self.statusBar().showMessage("Готово")

    def _build_menus(self):
        mb = self.menuBar()

        file_menu = mb.addMenu("&Файл")
        act_new = QAction("&Создать", self)
        act_new.setShortcut(QKeySequence.StandardKey.New)
        act_new.triggered.connect(self.new_file)
        act_open = QAction("&Открыть…", self)
        act_open.setShortcut(QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self.open_file_dialog)
        act_save = QAction("&Сохранить", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.save_file)
        act_save_as = QAction("Сохранить &как…", self)
        act_save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self.save_file_as)
        act_quit = QAction("&Выход", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        for a in (act_new, act_open, act_save, act_save_as):
            file_menu.addAction(a)
        file_menu.addSeparator()
        file_menu.addAction(act_quit)

        edit_menu = mb.addMenu("&Правка")
        act_add_elem = QAction("Добавить &элемент…", self)
        act_add_elem.triggered.connect(self.action_add_element)
        act_del_elem = QAction("&Удалить элемент", self)
        act_del_elem.triggered.connect(self.action_delete_element)
        act_rename = QAction("&Переименовать элемент…", self)
        act_rename.triggered.connect(self.action_rename_element)
        edit_menu.addAction(act_add_elem)
        edit_menu.addAction(act_del_elem)
        edit_menu.addAction(act_rename)
        edit_menu.addSeparator()
        act_new_qual = QAction("Новый (пустой) &квалификатор…", self)
        act_new_qual.triggered.connect(self.action_new_qualifier)
        act_new_fbox = QAction("Новый &функциональный блок…", self)
        act_new_fbox.triggered.connect(self.action_new_function_box)
        act_clone_qual = QAction("Новая &диаграмма из шаблона…", self)
        act_clone_qual.triggered.connect(self.action_clone_qualifier)
        act_register_root = QAction("Зарегистрировать &корень модели…", self)
        act_register_root.triggered.connect(self.action_register_root)
        act_new_arrow = QAction("Новая &стрелка…", self)
        act_new_arrow.triggered.connect(self.action_new_arrow)
        edit_menu.addAction(act_new_qual)
        edit_menu.addAction(act_new_fbox)
        edit_menu.addAction(act_new_arrow)
        edit_menu.addAction(act_clone_qual)
        edit_menu.addAction(act_register_root)

        help_menu = mb.addMenu("&Справка")
        act_about = QAction("&О программе", self)
        act_about.triggered.connect(self.action_about)
        help_menu.addAction(act_about)

        toolbar = QToolBar("Основная")
        toolbar.addAction(act_new)
        toolbar.addAction(act_open)
        toolbar.addAction(act_save)
        toolbar.addSeparator()
        toolbar.addAction(act_add_elem)
        toolbar.addAction(act_new_fbox)
        toolbar.addAction(act_new_arrow)
        self.addToolBar(toolbar)

    # -- связь с моделью ------------------------------------------------
    def _apply_model_to_panels(self):
        self.tree.set_model(self.model)
        self.attr_panel.set_model(self.model)
        self.raw_panel.set_model(self.model)
        self.json_panel.set_model(self.model)

    def _update_title(self):
        name = os.path.basename(self.current_path) if self.current_path else "Без имени"
        star = "*" if self.dirty else ""
        self.setWindowTitle("%s%s — Редактор Ramus RSF" % (name, star))
        if self.current_path:
            self.statusBar().showMessage(self.current_path)
        elif self.model is not None:
            self.statusBar().showMessage("Без имени (не сохранено)")
        else:
            self.statusBar().showMessage("Файл не загружен")

    def mark_dirty(self):
        self.dirty = True
        self._update_title()

    # -- операции с файлами -------------------------------------------------
    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        resp = QMessageBox.question(
            self, "Несохранённые изменения",
            "У вас есть несохранённые изменения. Отменить их?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return resp == QMessageBox.StandardButton.Discard

    def new_file(self):
        if not self._confirm_discard_changes():
            return
        self.model = template.new_model("Корневая диаграмма")
        self.current_path = None
        self.dirty = True
        self._apply_model_to_panels()
        self._update_title()

    def open_file_dialog(self):
        if not self._confirm_discard_changes():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Открыть файл .rsf", "", "Файлы Ramus (*.rsf);;Все файлы (*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        try:
            self.model = Model.load(path)
        except Exception as ex:
            QMessageBox.critical(self, "Не удалось открыть файл", "%s:\n%s" % (path, ex))
            return
        self.current_path = path
        self.dirty = False
        self._apply_model_to_panels()
        self._update_title()

    def save_file(self):
        if self.model is None:
            return
        if self.current_path is None:
            self.save_file_as()
            return
        self._save_to(self.current_path)

    def save_file_as(self):
        if self.model is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл .rsf",
                                               self.current_path or "model.rsf",
                                               "Файлы Ramus (*.rsf);;Все файлы (*)")
        if path:
            self._save_to(path)

    def _save_to(self, path: str):
        try:
            self.model.save(path)
        except Exception as ex:
            QMessageBox.critical(self, "Не удалось сохранить файл", "%s:\n%s" % (path, ex))
            return
        self.current_path = path
        self.dirty = False
        self._update_title()

    def closeEvent(self, event: QCloseEvent):
        if self._confirm_discard_changes():
            event.accept()
        else:
            event.ignore()

    # -- взаимодействие с деревом/вкладками -------------------------------------------
    def _on_tree_selection(self, qid: int, eid):
        self._current_qid = qid
        self._current_eid = eid
        self.attr_panel.set_element(eid)

    def _on_show_system_toggled(self, _state):
        self.tree.set_show_system(self.show_system_check.isChecked())

    def _open_table_tab(self, path: str):
        self.tabs.setCurrentWidget(self.raw_panel)
        self.raw_panel.show_table(path)

    def _on_attr_changed(self, kind: str):
        self.mark_dirty()
        if kind == "name" and self._current_eid is not None:
            self.tree.rebuild(keep_selection=True)

    def _on_structure_changed(self):
        self.tree.rebuild(keep_selection=True)
        self.attr_panel.rebuild()
        self.json_panel.refresh()
        self.mark_dirty()

    # -- действия редактирования ------------------------------------------------------
    def _require_model(self) -> bool:
        if self.model is None:
            QMessageBox.information(self, "Нет файла", "Сначала откройте или создайте файл.")
            return False
        return True

    def action_add_element(self):
        if not self._require_model():
            return
        dlg = NewElementDialog(self.model, self._current_qid, self)
        if dlg.exec():
            qid, name = dlg.result_values()
            if qid is None:
                QMessageBox.warning(self, "Нет квалификатора", "В этом файле пока нет квалификаторов.")
                return
            eid = self.model.add_element(qid, name)
            self._after_structural_edit(qid, eid)

    def action_delete_element(self):
        if not self._require_model():
            return
        if self._current_eid is None:
            QMessageBox.information(self, "Нет выбора", "Выберите элемент для удаления.")
            return
        resp = QMessageBox.question(self, "Удаление элемента",
                                     "Удалить элемент %d и все значения его атрибутов?" %
                                     self._current_eid)
        if resp != QMessageBox.StandardButton.Yes:
            return
        qid = self._current_qid
        self.model.delete_element(self._current_eid)
        self._current_eid = None
        self._after_structural_edit(qid, None)

    def action_rename_element(self):
        if not self._require_model():
            return
        if self._current_eid is None:
            QMessageBox.information(self, "Нет выбора", "Выберите элемент для переименования.")
            return
        e = self.model.elements.get(self._current_eid)
        current = e.get("ELEMENT_NAME") or "" if e else ""
        name, ok = QInputDialog.getText(self, "Переименование элемента", "Новое имя:",
                                         QLineEdit.EchoMode.Normal, current)
        if ok:
            self.model.set_name(self._current_eid, name)
            self._after_structural_edit(self._current_qid, self._current_eid)

    def action_new_qualifier(self):
        if not self._require_model():
            return
        dlg = NewQualifierDialog(self)
        if dlg.exec():
            name, system = dlg.result_values()
            qid = self.model.new_qualifier_id()
            self.model.t_qualifiers.rows.append({
                "QUALIFIER_ID": qid, "QUALIFIER_NAME": name,
                "QUALIFIER_SYSTEM": system, "ATTRIBUTE_FOR_NAME": None,
            })
            self.model.refresh()
            self._after_structural_edit(qid, None)

    def action_new_function_box(self):
        if not self._require_model():
            return
        if not self.model.qualifiers:
            QMessageBox.information(self, "Нет квалификаторов",
                                     "Сначала создайте квалификатор диаграммы "
                                     "(Правка > Новая диаграмма из шаблона).")
            return
        dlg = NewFunctionBoxDialog(self.model, self._current_qid, self)
        if dlg.exec():
            v = dlg.result_values()
            if v["qualifier_id"] is None:
                QMessageBox.warning(self, "Нет квалификатора", "Выберите квалификатор.")
                return
            try:
                eid = self.model.add_function_box(
                    v["qualifier_id"], v["name"], v["x"], v["y"], v["width"], v["height"],
                    background=v["background"], foreground=v["foreground"],
                    font_name=v["font_name"], font_size=v["font_size"],
                    function_type=v["function_type"])
            except KeyError as ex:
                QMessageBox.critical(self, "Не удалось создать функциональный блок", str(ex))
                return
            self._after_structural_edit(v["qualifier_id"], eid)

    def action_new_arrow(self):
        if not self._require_model():
            return
        qid = self._current_qid
        if qid is None or not self.model.elements_by_qualifier.get(qid):
            # если ничего не выбрано -- берём любой несистемный квалификатор, у которого реально есть блоки
            qid = next((q for q, els in self.model.elements_by_qualifier.items()
                        if els and not self.model.qualifiers.get(q, {}).get("QUALIFIER_SYSTEM")),
                       None)
        if qid is None:
            QMessageBox.information(self, "Нет блоков",
                                     "Сначала добавьте хотя бы один функциональный блок "
                                     "(Правка > Новый функциональный блок).")
            return
        dlg = NewArrowDialog(self.model, qid, self._current_eid, None, self)
        if dlg.exec():
            v = dlg.result_values()
            try:
                if v["kind"] == "arrow":
                    stream_eid = self.model.add_arrow(
                        v["from_element_id"], v["from_side"],
                        v["to_element_id"], v["to_side"],
                        name=v["name"], tunnel=v["tunnel"])
                else:
                    stream_eid = self.model.add_boundary_arrow(
                        v["element_id"], v["box_side"], v["page_side"],
                        direction=v["direction"], name=v["name"], tunnel=v["tunnel"])
            except (KeyError, ValueError) as ex:
                QMessageBox.critical(self, "Не удалось создать стрелку", str(ex))
                return
            self._after_structural_edit(self.model.find_stream_qualifier(), stream_eid)

    def action_clone_qualifier(self):
        if not self._require_model():
            return
        if not self.model.qualifiers:
            QMessageBox.information(self, "Нет доступного шаблона",
                                     "В этом файле нет квалификаторов, из которых можно "
                                     "скопировать набор атрибутов. Используйте Файл > Создать, "
                                     "чтобы собрать его с нуля.")
            return
        dlg = CloneQualifierDialog(self.model, self)
        if dlg.exec():
            v = dlg.result_values()
            if v["source_qualifier_id"] is None:
                QMessageBox.warning(self, "Нет источника", "Выберите квалификатор, из которого копировать.")
                return
            new_qid = self.model.clone_qualifier_as_container(
                v["source_qualifier_id"], v["name"])
            if v["register_root"]:
                bf = self.model.find_base_functions_qualifier()
                if bf is not None:
                    root_elem = self.model.add_element(bf, name="")
                    self.model.register_model_root(root_elem, new_qid)
                else:
                    QMessageBox.warning(
                        self, "Нет квалификатора F_BASE_FUNCTIONS",
                        "В этом файле нет системного квалификатора F_BASE_FUNCTIONS, "
                        "поэтому новая диаграмма создана, но не зарегистрирована как "
                        "корень модели верхнего уровня. Вы всё ещё можете открыть её "
                        "напрямую в дереве.")
            self._after_structural_edit(new_qid, None)

    def action_register_root(self):
        if not self._require_model():
            return
        dlg = RegisterModelRootDialog(self.model, self)
        if dlg.exec():
            qid = dlg.result_values()
            if qid is None:
                return
            bf = self.model.find_base_functions_qualifier()
            if bf is None:
                QMessageBox.critical(self, "Недоступно",
                                      "В этом файле нет квалификатора F_BASE_FUNCTIONS, "
                                      "под которым можно регистрировать корни.")
                return
            root_elem = self.model.add_element(bf, name="")
            try:
                self.model.register_model_root(root_elem, qid)
            except KeyError as ex:
                QMessageBox.critical(self, "Не удалось", str(ex))
                return
            self._after_structural_edit(qid, None)

    def action_about(self):
        AboutDialog(self).exec()

    def _after_structural_edit(self, qid, eid):
        self.tree.rebuild()
        if eid is not None:
            self.tree.select_element(qid, eid)
        self.raw_panel.set_model(self.model)
        self.json_panel.refresh()
        self.mark_dirty()
