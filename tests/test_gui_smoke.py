"""
Headless GUI smoke test. Requires PyQt6 and a Qt platform plugin; runs
against the "offscreen" platform so it works under Xvfb or with no
display at all (CI). Skipped automatically if PyQt6 isn't installed.
"""
import json
import os
import tempfile
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from ramus_rsf_tool.gui.main_window import MainWindow  # noqa: E402
from ramus_rsf_tool.gui.widgets.dialogs import NewArrowDialog  # noqa: E402
from ramus_rsf_tool.rsf_model import Model, ArrowSide  # noqa: E402


@pytest.fixture(scope="module")
def app():
    existing = QApplication.instance()
    return existing or QApplication(["test"])


def test_new_file_add_box_save_reload(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    assert root is not None

    eid = win.model.add_function_box(root, "Box A", 10, 10, 100, 60)
    win._after_structural_edit(root, eid)
    win.tree.select_element(root, eid)
    win._on_tree_selection(root, eid)
    app.processEvents()

    assert win.attr_panel.form.rowCount() > 0

    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        win._save_to(path)
        assert not win.dirty

        win2 = MainWindow()
        win2.open_path(path)
        app.processEvents()
        r2 = win2.model.find_qualifier("Root Diagram")
        els = win2.model.elements_by_qualifier.get(r2, [])
        assert len(els) == 1
        assert win2.model.element_attributes(els[0])["Name"] == "Box A"
    finally:
        os.unlink(path)


def test_name_edit_updates_tree_and_model(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    eid = win.model.add_function_box(root, "Box A", 0, 0, 10, 10)
    win._after_structural_edit(root, eid)
    win.tree.select_element(root, eid)
    win._on_tree_selection(root, eid)
    app.processEvents()

    name_widget = None
    for r in range(win.attr_panel.form.rowCount()):
        label = win.attr_panel.form.itemAt(r, win.attr_panel.form.ItemRole.LabelRole).widget()
        if label.text() == "Name":
            name_widget = win.attr_panel.form.itemAt(r, win.attr_panel.form.ItemRole.FieldRole).widget()
    assert name_widget is not None

    name_widget.setText("Renamed Box")
    name_widget.editingFinished.emit()

    assert win.model.elements[eid]["ELEMENT_NAME"] == "Renamed Box"
    assert win.tree.currentItem().text(0) == "Renamed Box"


def test_raw_table_add_and_delete_row(app):
    win = MainWindow()
    win.new_file()
    win.raw_panel.set_model(win.model)
    win.raw_panel.show_table("data/elements.xml")
    app.processEvents()

    before = win.raw_panel.table.rowCount()
    win.raw_panel._add_row()
    assert win.raw_panel.table.rowCount() == before + 1

    win.raw_panel.table.selectRow(win.raw_panel.table.rowCount() - 1)
    win.raw_panel._delete_selected_rows()
    assert win.raw_panel.table.rowCount() == before


def test_json_dump_reflects_model(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    win.model.add_function_box(root, "Dump Me", 0, 0, 10, 10)
    win.json_panel.set_model(win.model)
    win.json_panel.refresh()
    assert "Dump Me" in win.json_panel.text.toPlainText()


def test_list_mode_attribute_row_builds_without_error(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    eid = win.model.add_function_box(root, "Box A", 0, 0, 10, 10)

    aid = win.model.new_attribute_id()
    win.model.t_attributes.rows.append({
        "ATTRIBUTE_ID": aid, "ATTRIBUTE_NAME": "Links",
        "ATTRIBUTE_TYPE_PLUGIN_NAME": "Core", "ATTRIBUTE_TYPE_NAME": "OtherElement",
        "ATTRIBUTE_TYPE_COMPARABLE": False, "ATTRIBUTE_SYSTEM": False,
    })
    win.model.t_qual_attrs.rows.append({
        "QUALIFIER_ID": root, "ATTRIBUTE_ID": aid,
        "ATTRIBUTE_SYSTEM": False, "ATTRIBUTE_POSITION": 99,
    })
    win.model.refresh()
    t = win.model._get_or_create_vtable("data/Core/attribute_other_elements.xml",
                                         ("Core", "OtherElement"))
    t.rows.append({"ATTRIBUTE_ID": aid, "ELEMENT_ID": eid, "OTHER_ELEMENT": 999})

    win._after_structural_edit(root, eid)
    win.tree.select_element(root, eid)
    win._on_tree_selection(root, eid)
    app.processEvents()
    assert win.attr_panel.form.rowCount() == 9


def test_json_dump_export_redact_reimport_save_workflow(app):
    """The exact workflow this feature exists for: export JSON, redact
    text in it, apply the redacted JSON, then save the .rsf."""
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    eid = win.model.add_function_box(root, "Alice Johnson - sensitive", 0, 0, 10, 10)
    win._after_structural_edit(root, eid)

    # "Export" (the box already reflects the model; this is what Export
    # to file... would write)
    win.json_panel.set_model(win.model)
    win.json_panel.refresh()
    exported = win.json_panel.text.toPlainText()
    assert "Alice Johnson - sensitive" in exported

    # redact, then paste the redacted text back into the box
    redacted = exported.replace("Alice Johnson - sensitive", "[REDACTED]")
    win.json_panel.text.setPlainText(redacted)

    # "Apply edited text below" (Import from file... does the same after
    # loading the file's contents into the box)
    with patch.object(QMessageBox, "exec", return_value=None):
        win.json_panel._apply_text()
    app.processEvents()

    assert win.model.elements[eid]["ELEMENT_NAME"] == "[REDACTED]"
    assert win.dirty
    win.tree.select_element(root, eid)
    assert win.tree.currentItem().text(0) == "[REDACTED]"

    # save the resulting .rsf and confirm the redaction persisted
    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        win._save_to(path)
        assert not win.dirty
        m2 = Model.load(path)
        assert m2.element_attributes(eid)["Name"] == "[REDACTED]"
    finally:
        os.unlink(path)


def test_json_dump_invalid_json_shows_error_without_crashing(app):
    win = MainWindow()
    win.new_file()
    win.json_panel.set_model(win.model)
    win.json_panel.text.setPlainText("{ not valid json")
    dirty_before = win.dirty  # new_file() itself already marks the window dirty

    with patch.object(QMessageBox, "critical", return_value=None) as mock_critical:
        win.json_panel._apply_text()
    mock_critical.assert_called_once()
    assert win.dirty == dirty_before  # invalid JSON must not touch the model


def test_new_arrow_dialog_box_to_box(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    b1 = win.model.add_function_box(root, "Box A", 40, 40, 140, 80)
    b2 = win.model.add_function_box(root, "Box B", 300, 40, 140, 80)
    win._after_structural_edit(root, b2)

    dlg = NewArrowDialog(win.model, root, b1, b2, win)
    dlg.name_edit.setText("GUI Arrow")
    v = dlg.result_values()
    assert v == dict(kind="arrow", from_element_id=b1, from_side=ArrowSide.INPUT,
                      to_element_id=b2, to_side=ArrowSide.INPUT,
                      name="GUI Arrow", tunnel=False)

    stream_eid = win.model.add_arrow(v["from_element_id"], v["from_side"],
                                      v["to_element_id"], v["to_side"],
                                      name=v["name"], tunnel=v["tunnel"])
    win._after_structural_edit(win.model.find_stream_qualifier(), stream_eid)
    app.processEvents()

    sect_qid = win.model.find_sector_qualifier()
    assert len(win.model.elements_by_qualifier[sect_qid]) == 1
    assert win.dirty


def test_new_arrow_dialog_boundary_mode(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    b1 = win.model.add_function_box(root, "Box A", 40, 40, 140, 80)

    dlg = NewArrowDialog(win.model, root, b1, None, win)
    dlg.to_picker.boundary_radio.setChecked(True)
    idx = dlg.to_picker.page_side_combo.findData(ArrowSide.TOP)
    dlg.to_picker.page_side_combo.setCurrentIndex(idx)
    v = dlg.result_values()
    assert v["kind"] == "boundary"
    assert v["element_id"] == b1
    assert v["page_side"] == ArrowSide.TOP
    assert v["direction"] == "out"

    stream_eid = win.model.add_boundary_arrow(
        v["element_id"], v["box_side"], v["page_side"],
        direction=v["direction"], name=v["name"], tunnel=v["tunnel"])
    win._after_structural_edit(win.model.find_stream_qualifier(), stream_eid)
    app.processEvents()
    assert win.dirty


def test_new_arrow_dialog_rejects_boundary_to_boundary(app):
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    win.model.add_function_box(root, "Box A", 40, 40, 140, 80)

    dlg = NewArrowDialog(win.model, root, None, None, win)
    dlg.from_picker.boundary_radio.setChecked(True)
    dlg.to_picker.boundary_radio.setChecked(True)
    with patch.object(QMessageBox, "warning", return_value=None) as mock_warn:
        dlg._on_accept()
    mock_warn.assert_called_once()


def test_action_new_arrow_end_to_end(app):
    """Drives MainWindow.action_new_arrow() itself (not just the dialog),
    with QDialog.exec patched to simulate the user accepting it."""
    win = MainWindow()
    win.new_file()
    root = win.model.find_qualifier("Root Diagram")
    b1 = win.model.add_function_box(root, "Box A", 40, 40, 140, 80)
    b2 = win.model.add_function_box(root, "Box B", 300, 40, 140, 80)
    win._after_structural_edit(root, b1)
    win.tree.select_element(root, b1)
    win._on_tree_selection(root, b1)

    from PyQt6.QtWidgets import QDialog

    captured = {}

    def fake_exec(self):
        captured["dlg"] = self
        self.to_picker.elem_combo.setCurrentIndex(self.to_picker.elem_combo.findData(b2))
        return QDialog.DialogCode.Accepted

    with patch.object(NewArrowDialog, "exec", fake_exec):
        win.action_new_arrow()
    app.processEvents()

    sect_qid = win.model.find_sector_qualifier()
    assert sect_qid is not None
    assert len(win.model.elements_by_qualifier[sect_qid]) == 1
    seid = win.model.elements_by_qualifier[sect_qid][0]
    attrs = win.model.element_attributes(seid)
    assert attrs["F_SECTOR_BORDER_START"]["FUNCTION"] == b1
    assert attrs["F_SECTOR_BORDER_END"]["FUNCTION"] == b2
