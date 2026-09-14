"""Левый навигатор: квалификаторы (классы) -> элементы (экземпляры)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget
from PyQt6.QtCore import Qt, pyqtSignal

from ...rsf_model import Model

QUALIFIER_ROLE = Qt.ItemDataRole.UserRole
ELEMENT_ROLE = Qt.ItemDataRole.UserRole + 1


class QualifierTree(QTreeWidget):
    """QTreeWidget с одним элементом верхнего уровня на каждый
    квалификатор и одним дочерним элементом на каждый элемент модели.
    elementSelected(qualifier_id, element_id) срабатывает, когда
    пользователь выбирает элемент; qualifierSelected(qualifier_id) --
    когда выбирает сам квалификатор (element_id в этом случае None)."""

    elementSelected = pyqtSignal(int, object)   # (qualifier_id, element_id или None)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setHeaderLabels(["Имя", "ID"])
        self.setColumnWidth(0, 260)
        self.model: Optional[Model] = None
        self.show_system = False
        self.itemSelectionChanged.connect(self._on_selection)

    def set_model(self, model: Optional[Model]):
        self.model = model
        self.rebuild()

    def set_show_system(self, show: bool):
        self.show_system = show
        self.rebuild()

    def rebuild(self, keep_selection: bool = False):
        prev = self.current_selection() if keep_selection else None
        self.clear()
        if self.model is None:
            return
        for qid, q in sorted(self.model.qualifiers.items(),
                              key=lambda kv: (kv[1].get("QUALIFIER_NAME") or "")):
            is_system = bool(q.get("QUALIFIER_SYSTEM"))
            if is_system and not self.show_system:
                continue
            qname = q.get("QUALIFIER_NAME") or "(без имени)"
            label = qname + ("  [система]" if is_system else "")
            qitem = QTreeWidgetItem([label, str(qid)])
            qitem.setData(0, QUALIFIER_ROLE, qid)
            qitem.setData(0, ELEMENT_ROLE, None)
            if is_system:
                qitem.setForeground(0, self._system_brush())
            self.addTopLevelItem(qitem)
            for eid in self.model.elements_by_qualifier.get(qid, []):
                e = self.model.elements[eid]
                ename = e.get("ELEMENT_NAME") or "(без имени)"
                eitem = QTreeWidgetItem([ename, str(eid)])
                eitem.setData(0, QUALIFIER_ROLE, qid)
                eitem.setData(0, ELEMENT_ROLE, eid)
                qitem.addChild(eitem)
        if prev is not None:
            self.select_element(*prev)

    def _system_brush(self):
        from PyQt6.QtGui import QBrush, QColor
        return QBrush(QColor("#888888"))

    def current_selection(self):
        items = self.selectedItems()
        if not items:
            return None
        it = items[0]
        return (it.data(0, QUALIFIER_ROLE), it.data(0, ELEMENT_ROLE))

    def select_element(self, qualifier_id: int, element_id):
        def walk(item: QTreeWidgetItem):
            if (item.data(0, QUALIFIER_ROLE) == qualifier_id and
                    item.data(0, ELEMENT_ROLE) == element_id):
                self.setCurrentItem(item)
                return True
            for i in range(item.childCount()):
                if walk(item.child(i)):
                    return True
            return False
        for i in range(self.topLevelItemCount()):
            if walk(self.topLevelItem(i)):
                break

    def _on_selection(self):
        sel = self.current_selection()
        if sel is None:
            return
        qid, eid = sel
        self.elementSelected.emit(qid, eid)
