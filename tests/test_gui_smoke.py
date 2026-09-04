"""
Headless GUI smoke test. Requires PyQt6 and a Qt platform plugin; runs
against the "offscreen" platform so it works under Xvfb or with no
display at all (CI). Skipped automatically if PyQt6 isn't installed.
"""
import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ramus_rsf_tool.gui.main_window import MainWindow  # noqa: E402


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
