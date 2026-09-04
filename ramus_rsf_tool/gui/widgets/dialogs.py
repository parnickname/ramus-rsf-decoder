"""Modal dialogs for structural edits: new element/qualifier, new function
box, clone-qualifier-as-diagram, register model root."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QVBoxLayout, QLineEdit, QComboBox, QSpinBox,
    QDoubleSpinBox, QDialogButtonBox, QCheckBox, QLabel, QMessageBox,
)

from ...rsf_model import Model, argb
from .common import ColorButton


def _qualifier_combo(model: Model, include_system: bool = True) -> QComboBox:
    combo = QComboBox()
    for qid, q in sorted(model.qualifiers.items(),
                          key=lambda kv: (kv[1].get("QUALIFIER_NAME") or "")):
        if q.get("QUALIFIER_SYSTEM") and not include_system:
            continue
        label = "%s (%d)" % (q.get("QUALIFIER_NAME") or "(unnamed)", qid)
        combo.addItem(label, qid)
    return combo


class NewElementDialog(QDialog):
    """Add a bare element under a chosen qualifier."""

    def __init__(self, model: Model, default_qualifier: Optional[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("New element")
        self.model = model
        layout = QFormLayout(self)
        self.qual_combo = _qualifier_combo(model)
        if default_qualifier is not None:
            idx = self.qual_combo.findData(default_qualifier)
            if idx >= 0:
                self.qual_combo.setCurrentIndex(idx)
        self.name_edit = QLineEdit()
        layout.addRow("Qualifier:", self.qual_combo)
        layout.addRow("Name:", self.name_edit)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return self.qual_combo.currentData(), self.name_edit.text()


class NewQualifierDialog(QDialog):
    """Create a bare qualifier (no attribute set) -- for a fresh EAV
    'class' unrelated to IDEF0 function boxes, e.g. a custom browser
    table. Use 'Clone qualifier as diagram' instead if you want a new
    IDEF0 diagram page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New (empty) qualifier")
        layout = QFormLayout(self)
        self.name_edit = QLineEdit()
        self.system_check = QCheckBox("System qualifier")
        layout.addRow("Name:", self.name_edit)
        layout.addRow("", self.system_check)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                    QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def result_values(self):
        return self.name_edit.text(), self.system_check.isChecked()


class NewFunctionBoxDialog(QDialog):
    """Full add_function_box() form: name, bounds, colors, font, status,
    type -- for a qualifier that already carries the standard F_* set
    (any qualifier created via 'Clone qualifier as diagram', or any
    pre-existing Function qualifier)."""

    def __init__(self, model: Model, default_qualifier: Optional[int], parent=None):
        super().__init__(parent)
        self.setWindowTitle("New function box")
        self.model = model
        layout = QFormLayout(self)

        self.qual_combo = _qualifier_combo(model, include_system=False)
        if default_qualifier is not None:
            idx = self.qual_combo.findData(default_qualifier)
            if idx >= 0:
                self.qual_combo.setCurrentIndex(idx)
        layout.addRow("Qualifier (diagram):", self.qual_combo)

        self.name_edit = QLineEdit("New function")
        layout.addRow("Name:", self.name_edit)

        self.x = self._spin(-100000, 100000, 40)
        self.y = self._spin(-100000, 100000, 40)
        self.w = self._spin(1, 100000, 140)
        self.h = self._spin(1, 100000, 80)
        layout.addRow("X:", self.x)
        layout.addRow("Y:", self.y)
        layout.addRow("Width:", self.w)
        layout.addRow("Height:", self.h)

        self.bg = ColorButton(argb(0, 255, 0))
        self.fg = ColorButton(argb(0, 0, 0))
        layout.addRow("Background:", self.bg)
        layout.addRow("Foreground:", self.fg)

        self.font_name = QLineEdit("Dialog")
        self.font_size = QSpinBox()
        self.font_size.setRange(1, 400)
        self.font_size.setValue(12)
        layout.addRow("Font name:", self.font_name)
        layout.addRow("Font size:", self.font_size)

        self.func_type = QSpinBox()
        self.func_type.setRange(-1000, 1000)
        self.func_type.setValue(3)
        self.func_type.setToolTip("F_TYPE; 3 = ordinary function box on every sample file")
        layout.addRow("Function type:", self.func_type)

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
    """clone_qualifier_as_container(): build a new IDEF0 diagram page by
    copying an existing Function qualifier's full attribute set."""

    def __init__(self, model: Model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New diagram from template")
        layout = QFormLayout(self)
        self.source_combo = _qualifier_combo(model, include_system=False)
        self.name_edit = QLineEdit("New diagram")
        self.register_root = QCheckBox("Register as a new top-level model (F_BASE_FUNCTIONS)")
        self.register_root.setChecked(True)
        layout.addRow("Copy attribute set from:", self.source_combo)
        layout.addRow("New diagram name:", self.name_edit)
        layout.addRow("", self.register_root)
        note = QLabel("Copies every attribute Ramus's checkIDEF0Attributes() requires "
                       "(Name, F_BOUNDS, F_BACKGROUND, ...) from the chosen qualifier "
                       "onto a new one. See RAMUS_RSF_FORMAT.md section 9.")
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
    """register_model_root(): mark an existing qualifier as a top-level
    model root by pointing a new F_BASE_FUNCTIONS bookkeeping element at
    it. Requires the file to already have an F_BASE_FUNCTIONS qualifier
    carrying F_BASE_FUNCTION_QUALIFIER_ID (true of every real Ramus file,
    and of files started via File > New in this app); 'New diagram from
    template' does this automatically and is the easier path for a
    brand-new diagram."""

    def __init__(self, model: Model, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Register model root")
        layout = QFormLayout(self)
        self.qual_combo = _qualifier_combo(model, include_system=False)
        layout.addRow("Qualifier to register as root:", self.qual_combo)
        note = QLabel("Adds a new element under the F_BASE_FUNCTIONS system "
                       "qualifier pointing at the chosen qualifier, the same "
                       "way Ramus marks a top-level model in its navigator.")
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


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        layout = QVBoxLayout(self)
        from ... import __version__
        text = QLabel(
            "<h3>Ramus RSF Editor</h3>"
            "<p>Version %s</p>"
            "<p>A native Linux GUI for reading and editing Ramus IDEF0/DFD "
            "<code>.rsf</code> model files, built on a clean-room reimplementation "
            "of the file format (see RAMUS_RSF_FORMAT.md).</p>"
            "<p>Not affiliated with the Ramus project.</p>" % __version__)
        text.setWordWrap(True)
        text.setTextFormat(text.textFormat().RichText)
        layout.addWidget(text)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
