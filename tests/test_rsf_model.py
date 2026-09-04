import json
import os
import tempfile

import pytest

from ramus_rsf_tool.rsf_model import Model, argb, unpack_argb, dump_model, apply_json_dump
from ramus_rsf_tool.template import new_model


@pytest.fixture
def model():
    return new_model("Root Diagram")


def test_color_codec():
    assert argb(0, 255, 0) == -16711936
    assert argb(0, 0, 0) == -16777216
    assert unpack_argb(-16711936) == (0, 255, 0, 255)
    assert unpack_argb(-16777216) == (0, 0, 0, 255)


def test_add_function_box_and_read_back(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Receive Order", 40, 40, 140, 80)
    attrs = model.element_attributes(eid)
    assert attrs["Name"] == "Receive Order"
    assert attrs["F_BOUNDS"] == {"X": 40.0, "Y": 40.0, "WIDTH": 140.0, "HEIGHT": 80.0}
    assert attrs["F_BACKGROUND"] == -16711936
    assert attrs["F_FOREGROUND"] == -16777216
    assert attrs["F_TYPE"] == 3


def test_rename_mirrors_element_name(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Old name", 0, 0, 10, 10)
    model.set_name(eid, "New name")
    assert model.elements[eid]["ELEMENT_NAME"] == "New name"
    assert model.get_value(eid, model.find_attribute(root, "Name")) == "New name"


def test_delete_element_removes_attribute_rows(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Box", 0, 0, 10, 10)
    aid = model.find_attribute(root, "F_BOUNDS")
    assert model.get_value(eid, aid) is not None
    model.delete_element(eid)
    assert eid not in model.elements
    # value tables no longer reference the deleted element
    t = model.table("data/IDEF0/attribute_rectangles.xml")
    assert not t.find_rows(ELEMENT_ID=eid)


def test_clone_qualifier_as_container_and_new_box(model):
    root = model.find_qualifier("Root Diagram")
    new_qid = model.clone_qualifier_as_container(root, "Child Diagram")
    assert model.qualifier_attribute_ids[new_qid] == model.qualifier_attribute_ids[root]
    eid = model.add_function_box(new_qid, "Sub-step", 5, 5, 50, 30)
    assert model.element_attributes(eid)["Name"] == "Sub-step"


def test_register_model_root(model):
    root = model.find_qualifier("Root Diagram")
    new_qid = model.clone_qualifier_as_container(root, "Second model")
    bf = model.find_base_functions_qualifier()
    assert bf is not None
    elem = model.add_element(bf, name="")
    model.register_model_root(elem, new_qid)
    aid = model.find_attribute(bf, "F_BASE_FUNCTION_QUALIFIER_ID")
    assert model.get_value(elem, aid) == new_qid


def test_save_and_reload_roundtrip(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Persisted box", 1, 2, 3, 4)
    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        model.save(path)
        m2 = Model.load(path)
        r2 = m2.find_qualifier("Root Diagram")
        assert r2 == root
        els = m2.elements_by_qualifier.get(r2, [])
        assert eid in els
        assert m2.element_attributes(eid)["Name"] == "Persisted box"
    finally:
        os.unlink(path)


def test_dump_model_is_json_safe(model):
    root = model.find_qualifier("Root Diagram")
    model.add_function_box(root, "Box", 0, 0, 10, 10)
    d = dump_model(model, include_system_qualifiers=True)
    import json
    json.dumps(d, default=str)  # must not raise


def test_stream_attribute_roundtrip(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Box", 0, 0, 10, 10)
    aid = model.find_attribute(root, "Description")
    assert aid is not None
    model.set_value(eid, aid, "<p>Hello</p>")
    assert model.get_value(eid, aid) == b"<p>Hello</p>"

    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        model.save(path)
        m2 = Model.load(path)
        assert m2.get_value(eid, aid) == b"<p>Hello</p>"
    finally:
        os.unlink(path)


def test_list_mode_via_raw_table(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Box", 0, 0, 10, 10)
    aid = model.new_attribute_id()
    model.t_attributes.rows.append({
        "ATTRIBUTE_ID": aid, "ATTRIBUTE_NAME": "Links",
        "ATTRIBUTE_TYPE_PLUGIN_NAME": "Core", "ATTRIBUTE_TYPE_NAME": "OtherElement",
        "ATTRIBUTE_TYPE_COMPARABLE": False, "ATTRIBUTE_SYSTEM": False,
    })
    model.t_qual_attrs.rows.append({
        "QUALIFIER_ID": root, "ATTRIBUTE_ID": aid,
        "ATTRIBUTE_SYSTEM": False, "ATTRIBUTE_POSITION": 99,
    })
    model.refresh()
    with pytest.raises(ValueError):
        model.set_value(eid, aid, {"OTHER_ELEMENT": 1})
    t = model.table("data/Core/attribute_other_elements.xml") if \
        "data/Core/attribute_other_elements.xml" in model.table_paths() else \
        model._get_or_create_vtable("data/Core/attribute_other_elements.xml", ("Core", "OtherElement"))
    t.rows.append({"ATTRIBUTE_ID": aid, "ELEMENT_ID": eid, "OTHER_ELEMENT": 777})
    rows = model.get_value(eid, aid)
    assert rows == [{"ATTRIBUTE_ID": aid, "ELEMENT_ID": eid, "OTHER_ELEMENT": 777}]


# -- apply_json_dump: the export-redact-reimport workflow -------------------

def test_apply_json_dump_redacts_text_values(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Alice Johnson - SSN 123-45-6789", 0, 0, 10, 10)
    other_name_aid = model.find_attribute(root, "F_STATUS")
    model.set_value(eid, other_name_aid, {"OTHER_NAME": "contact: alice@example.com"})

    data = dump_model(model, include_system_qualifiers=True)
    text = json.dumps(data)
    redacted_text = (text
                      .replace("Alice Johnson - SSN 123-45-6789", "[REDACTED NAME]")
                      .replace("contact: alice@example.com", "[REDACTED EMAIL]"))
    redacted = json.loads(redacted_text)

    result = apply_json_dump(model, redacted)
    assert result.warnings == []
    assert result.elements_updated == 1
    assert result.values_updated == 2  # Name + F_STATUS.OTHER_NAME

    assert model.elements[eid]["ELEMENT_NAME"] == "[REDACTED NAME]"
    name_aid = model.find_attribute(root, "Name")
    assert model.get_value(eid, name_aid) == "[REDACTED NAME]"
    assert model.get_value(eid, other_name_aid)["OTHER_NAME"] == "[REDACTED EMAIL]"


def test_apply_json_dump_is_a_noop_when_unchanged(model):
    root = model.find_qualifier("Root Diagram")
    model.add_function_box(root, "Unchanged box", 0, 0, 10, 10)
    data = dump_model(model, include_system_qualifiers=True)

    result = apply_json_dump(model, json.loads(json.dumps(data)))
    assert result.elements_updated == 0
    assert result.values_updated == 0
    assert result.qualifiers_updated == 0
    assert result.warnings == []


def test_apply_json_dump_never_adds_or_removes(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Real box", 0, 0, 10, 10)
    data = dump_model(model, include_system_qualifiers=True)

    # a ghost qualifier/element id that doesn't exist in the file
    data["qualifiers"].append({"id": 999999, "name": "Ghost", "system": False,
                                "elements": [{"id": 888888, "name": "Nope",
                                              "attributes": {}}]})
    before_qualifiers = set(model.qualifiers)
    before_elements = set(model.elements)

    result = apply_json_dump(model, data)
    assert len(result.warnings) == 1
    assert "999999" in result.warnings[0]
    # nothing was added
    assert set(model.qualifiers) == before_qualifiers
    assert set(model.elements) == before_elements
    # the real element is untouched (values matched, nothing changed)
    assert model.elements[eid]["ELEMENT_NAME"] == "Real box"


def test_apply_json_dump_skips_bytes_and_list_placeholders(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Box", 0, 0, 10, 10)
    desc_aid = model.find_attribute(root, "Description")
    model.set_value(eid, desc_aid, "<p>secret</p>")

    data = dump_model(model, include_system_qualifiers=True)
    # dump_model() only ever emits a byte-length placeholder for streams --
    # confirm it round-trips through apply_json_dump as a no-op, not a
    # silent data-loss "clear the field" edit.
    result = apply_json_dump(model, json.loads(json.dumps(data)))
    assert result.values_updated == 0
    assert model.get_value(eid, desc_aid) == b"<p>secret</p>"


def test_apply_json_dump_save_reload_roundtrip(model):
    root = model.find_qualifier("Root Diagram")
    eid = model.add_function_box(root, "Original Name", 0, 0, 10, 10)
    data = dump_model(model, include_system_qualifiers=True)
    redacted = json.loads(json.dumps(data).replace("Original Name", "[REDACTED]"))
    apply_json_dump(model, redacted)

    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        model.save(path)
        m2 = Model.load(path)
        assert m2.element_attributes(eid)["Name"] == "[REDACTED]"
    finally:
        os.unlink(path)
