"""
Вкладка "JSON-дамп": dump_model(), отрисованный как редактируемый текст,
с экспортом и соответствующим повторным импортом. Предполагаемый рабочий
процесс, для которого это существует:

    Экспорт в файл... -> отредактировать/отцензурировать текст где-то ещё
    -> Импорт из файла... (либо вставить отредактированный JSON прямо в
    поле и нажать «Применить отредактированный текст») -> Файл > Сохранить.

Импорт -- это *патч*, а не замена -- точное описание того, что он тронет,
а что нет, см. в docstring rsf_model.apply_json_dump() (коротко: только
значения квалификаторов/элементов, которые уже существуют, сопоставленные
по id; этим ничего никогда не добавляется и не удаляется).
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
    modelChanged = pyqtSignal()  # выдаётся после успешного импорта/применения

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model: Optional[Model] = None

        outer = QVBoxLayout(self)

        top = QHBoxLayout()
        self.include_system = QCheckBox("Включать системные квалификаторы/атрибуты")
        self.refresh_btn = QPushButton("Обновить")
        self.refresh_btn.setToolTip("Перестроить это поле по текущей модели "
                                     "(отменяет все ещё не применённые правки ниже).")
        self.export_btn = QPushButton("Экспорт в файл…")
        self.refresh_btn.clicked.connect(self.refresh)
        self.export_btn.clicked.connect(self._export)
        top.addWidget(self.include_system)
        top.addWidget(self.refresh_btn)
        top.addWidget(self.export_btn)
        top.addStretch(1)
        outer.addLayout(top)

        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Отцензурируйте/отредактируйте экспортированный JSON, затем:"))
        self.import_btn = QPushButton("Импорт из файла…")
        self.import_btn.setToolTip("Загрузить JSON-файл и применить его к модели.")
        self.apply_btn = QPushButton("Применить отредактированный текст ниже")
        self.apply_btn.setToolTip("Применить к модели тот JSON, что сейчас "
                                   "находится в поле ниже (для правок, сделанных прямо здесь).")
        self.import_btn.clicked.connect(self._import_from_file)
        self.apply_btn.clicked.connect(self._apply_text)
        import_row.addWidget(self.import_btn)
        import_row.addWidget(self.apply_btn)
        import_row.addStretch(1)
        outer.addLayout(import_row)

        self.text = QPlainTextEdit()
        self.text.setFont(QFont("Monospace"))
        self.text.setToolTip("Редактируемо -- вставьте или отредактируйте "
                              "отцензурированный JSON здесь, затем нажмите "
                              "«Применить отредактированный текст ниже».")
        outer.addWidget(self.text, 1)

    # -- связывание --------------------------------------------------------
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
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт JSON-дампа", "dump.json",
                                               "Файлы JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.text.toPlainText())
        except OSError as ex:
            QMessageBox.critical(self, "Экспорт не удался", str(ex))

    # -- импорт ------------------------------------------------------------
    def _import_from_file(self):
        if self.model is None:
            QMessageBox.information(self, "Нет файла", "Сначала откройте или создайте файл.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Импорт JSON-дампа", "",
                                               "Файлы JSON (*.json);;Все файлы (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except OSError as ex:
            QMessageBox.critical(self, "Импорт не удался", str(ex))
            return
        self.text.setPlainText(text)
        self._apply_text()

    def _apply_text(self):
        if self.model is None:
            QMessageBox.information(self, "Нет файла", "Сначала откройте или создайте файл.")
            return
        try:
            data = json.loads(self.text.toPlainText())
        except json.JSONDecodeError as ex:
            QMessageBox.critical(self, "Некорректный JSON", "Не удалось разобрать JSON:\n%s" % ex)
            return
        if not isinstance(data, dict) or "qualifiers" not in data:
            QMessageBox.critical(self, "Некорректный JSON",
                                  "Это не похоже на JSON-дамп из этого приложения "
                                  "(ожидался верхнеуровневый объект {\"qualifiers\": [...]}).")
            return

        result = apply_json_dump(self.model, data)

        detail = ""
        if result.warnings:
            shown = result.warnings[:25]
            detail = "\n".join(shown)
            if len(result.warnings) > len(shown):
                detail += "\n... и ещё %d" % (len(result.warnings) - len(shown))

        box = QMessageBox(self)
        box.setWindowTitle("Импорт применён")
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
