"""
Tests for arrow creation (rsf_model.Model.add_arrow / add_boundary_arrow),
RAMUS_RSF_FORMAT.md section 10.
"""
import io
import os
import struct
import tempfile

import pytest

from ramus_rsf_tool.rsf_model import (
    Model, ArrowSide, TunnelType, encode_sector_visual_attributes,
)
from ramus_rsf_tool.template import new_model


@pytest.fixture
def model():
    m = new_model("Root Diagram")
    root = m.find_qualifier("Root Diagram")
    m.add_function_box(root, "Box A", 40, 40, 140, 80)
    m.add_function_box(root, "Box B", 300, 40, 140, 80)
    m.add_function_box(root, "Box C", 40, 220, 140, 80)
    return m


def _box(model, name):
    root = model.find_qualifier("Root Diagram")
    for eid in model.elements_by_qualifier[root]:
        if model.elements[eid]["ELEMENT_NAME"] == name:
            return eid
    raise KeyError(name)


# -- visual attributes blob codec (RAMUS_RSF_FORMAT.md section 10) ----------

def _decode_visual_attributes(blob):
    """Minimal reader mirroring com.dsoft.utils.DataLoader, independent of
    encode_sector_visual_attributes() (which mirrors DataSaver) -- used to
    prove the encoder's output round-trips through the real format's
    reader logic, not just through itself."""
    f = io.BytesIO(blob)

    def rbool():
        return f.read(1)[0] != 0

    def rint():
        return struct.unpack("<i", f.read(4))[0]

    def rdouble():
        return struct.unpack("<d", f.read(8))[0]

    def rstring():
        n = rint()
        return None if n == -1 else f.read(n).decode("utf-8")

    assert rbool() is True  # "is BasicStroke"
    line_width = rdouble()
    cap = rint()
    join = rint()
    dash_phase = rdouble()
    miter_limit = rdouble()
    n = rint()
    dash = [rdouble() for _ in range(n)] if n > 0 else None

    assert rbool() is False  # font not null
    assert rbool() is True  # font not cached
    font_name = rstring()
    font_size = rint()
    font_style = rint()

    assert rbool() is True  # color not cached
    r, g, b = rint(), rint(), rint()

    assert f.read() == b""  # no leftover bytes
    return dict(line_width=line_width, cap=cap, join=join, dash_phase=dash_phase,
                miter_limit=miter_limit, dash=dash, font_name=font_name,
                font_size=font_size, font_style=font_style, color=(r, g, b))


def test_visual_attributes_default_decodes_cleanly():
    blob = encode_sector_visual_attributes()
    decoded = _decode_visual_attributes(blob)
    assert decoded["line_width"] == 1.5
    assert decoded["cap"] == 2
    assert decoded["join"] == 0
    assert decoded["miter_limit"] == 10.0
    assert decoded["dash"] is None
    assert decoded["font_name"] == "Dialog"
    assert decoded["font_size"] == 10
    assert decoded["font_style"] == 0
    assert decoded["color"] == (0, 0, 0)


def test_visual_attributes_custom_values_round_trip():
    blob = encode_sector_visual_attributes(
        line_width=2.0, font_name="Arial", font_size=14, font_style=1,
        color=(255, 0, 0), dash=[3.0, 3.0])
    decoded = _decode_visual_attributes(blob)
    assert decoded["line_width"] == 2.0
    assert decoded["font_name"] == "Arial"
    assert decoded["font_size"] == 14
    assert decoded["font_style"] == 1
    assert decoded["color"] == (255, 0, 0)
    assert decoded["dash"] == [3.0, 3.0]


# -- ensure_arrow_support() bootstrap ---------------------------------------

def test_ensure_arrow_support_bootstraps_on_fresh_file(model):
    assert model.find_sector_qualifier() is None
    assert model.find_stream_qualifier() is None
    sect_qid, stream_qid = model.ensure_arrow_support()
    assert model.qualifier_name(sect_qid) == "F_SECTORS"
    assert model.qualifier_name(stream_qid) == "F_STREAMS"
    for name in ("F_SECTOR_ATTRIBUTE", "F_SECTOR_BORDER_START", "F_SECTOR_BORDER_END",
                 "F_SECTOR_STREAM", "HierarchicalAttribute"):
        assert model.find_attribute(sect_qid, name) is not None, name
    for name in ("F_STREAM_NAME", "HierarchicalAttribute"):
        assert model.find_attribute(stream_qid, name) is not None, name


def test_ensure_arrow_support_is_idempotent(model):
    ids1 = model.ensure_arrow_support()
    ids2 = model.ensure_arrow_support()
    assert ids1 == ids2
    # calling it twice must not duplicate the attribute set
    sect_qid = ids1[0]
    assert len(model.qualifier_attribute_ids[sect_qid]) == \
        len(set(model.qualifier_attribute_ids[sect_qid]))


# -- add_arrow() (box-to-box) -------------------------------------------------

def test_add_arrow_produces_verified_real_shape(model):
    a, b = _box(model, "Box A"), _box(model, "Box B")
    stream_eid = model.add_arrow(a, ArrowSide.OUTPUT, b, ArrowSide.INPUT, name="Widgets")

    stream_qid = model.find_stream_qualifier()
    assert model.element_qualifier(stream_eid) == stream_qid
    assert model.get_value(stream_eid, model.find_attribute(stream_qid, "F_STREAM_NAME")) == "Widgets"

    sect_qid = model.find_sector_qualifier()
    sectors = model.elements_by_qualifier[sect_qid]
    assert len(sectors) == 1
    attrs = model.element_attributes(sectors[0])

    # exactly the shape verified against 283/288 real arrows in the
    # bundled Ramus sample file (RAMUS_RSF_FORMAT.md section 10)
    start = attrs["F_SECTOR_BORDER_START"]
    end = attrs["F_SECTOR_BORDER_END"]
    assert start["BORDER_TYPE"] == -1 and start["FUNCTION"] == a and start["FUNCTION_TYPE"] == ArrowSide.OUTPUT
    assert end["BORDER_TYPE"] == -1 and end["FUNCTION"] == b and end["FUNCTION_TYPE"] == ArrowSide.INPUT
    assert start["CROSSPOINT"] != end["CROSSPOINT"]
    assert start["CROSSPOINT"] >= 0 and end["CROSSPOINT"] >= 0
    assert start["TUNNEL_SOFT"] == TunnelType.HARD

    sector_attr = attrs["F_SECTOR_ATTRIBUTE"]
    assert sector_attr["CREATE_POS"] == -1.0
    assert sector_attr["SHOW_TEXT"] == 1
    assert sector_attr["VISUAL_ATTRIBUTES"] == encode_sector_visual_attributes()

    # linked back to its stream
    link = attrs["F_SECTOR_STREAM"]
    assert link == [{"ATTRIBUTE_ID": model.find_attribute(sect_qid, "F_SECTOR_STREAM"),
                      "ELEMENT_ID": sectors[0], "OTHER_ELEMENT": stream_eid}]


def test_add_arrow_tunnel_flag(model):
    a, b = _box(model, "Box A"), _box(model, "Box B")
    model.add_arrow(a, ArrowSide.OUTPUT, b, ArrowSide.INPUT, tunnel=True)
    sect_qid = model.find_sector_qualifier()
    seid = model.elements_by_qualifier[sect_qid][0]
    start = model.get_value(seid, model.find_attribute(sect_qid, "F_SECTOR_BORDER_START"))
    assert start["TUNNEL_SOFT"] == TunnelType.SOFT


def test_add_arrow_crosspoints_never_collide(model):
    a, b, c = _box(model, "Box A"), _box(model, "Box B"), _box(model, "Box C")
    model.add_arrow(a, ArrowSide.OUTPUT, b, ArrowSide.INPUT)
    model.add_arrow(b, ArrowSide.OUTPUT, c, ArrowSide.INPUT)
    model.add_arrow(a, ArrowSide.MECHANISM, c, ArrowSide.CONTROL)

    t = model.table("data/IDEF0/attribute_sector_borders.xml")
    crosspoints = [r["CROSSPOINT"] for r in t.rows if r.get("CROSSPOINT", -1) >= 0]
    assert len(crosspoints) == len(set(crosspoints)), "crosspoint id collision"
    assert len(crosspoints) == 6  # 3 arrows x 2 borders each


# -- add_boundary_arrow() ----------------------------------------------------

def test_add_boundary_arrow_direction_in(model):
    a = _box(model, "Box A")
    stream_eid = model.add_boundary_arrow(a, ArrowSide.CONTROL, ArrowSide.TOP,
                                           direction="in", name="Policy")
    sect_qid = model.find_sector_qualifier()
    seid = model.elements_by_qualifier[sect_qid][0]
    attrs = model.element_attributes(seid)
    start, end = attrs["F_SECTOR_BORDER_START"], attrs["F_SECTOR_BORDER_END"]
    # boundary border first (start), box border second (end) -- matches
    # real sectors 116/118/120/124 in the bundled Ramus sample
    assert start["BORDER_TYPE"] == ArrowSide.TOP
    assert start["FUNCTION"] == -1
    assert end["BORDER_TYPE"] == -1
    assert end["FUNCTION"] == a and end["FUNCTION_TYPE"] == ArrowSide.CONTROL


def test_add_boundary_arrow_direction_out(model):
    a = _box(model, "Box A")
    model.add_boundary_arrow(a, ArrowSide.OUTPUT, ArrowSide.RIGHT, direction="out")
    sect_qid = model.find_sector_qualifier()
    seid = model.elements_by_qualifier[sect_qid][0]
    attrs = model.element_attributes(seid)
    start, end = attrs["F_SECTOR_BORDER_START"], attrs["F_SECTOR_BORDER_END"]
    assert start["FUNCTION"] == a and start["FUNCTION_TYPE"] == ArrowSide.OUTPUT
    assert end["BORDER_TYPE"] == ArrowSide.RIGHT and end["FUNCTION"] == -1


def test_add_boundary_arrow_rejects_bad_direction(model):
    a = _box(model, "Box A")
    with pytest.raises(ValueError):
        model.add_boundary_arrow(a, ArrowSide.INPUT, ArrowSide.LEFT, direction="sideways")


# -- hierarchical ordering scoped per-qualifier (regression test) -----------

def test_hierarchical_chain_scoped_per_qualifier_not_global(model):
    a, b, c = _box(model, "Box A"), _box(model, "Box B"), _box(model, "Box C")
    model.add_arrow(a, ArrowSide.OUTPUT, b, ArrowSide.INPUT)
    model.add_arrow(b, ArrowSide.OUTPUT, c, ArrowSide.INPUT)

    sect_qid = model.find_sector_qualifier()
    stream_qid = model.find_stream_qualifier()
    sect_hier_aid = model.find_attribute(sect_qid, "HierarchicalAttribute")
    stream_hier_aid = model.find_attribute(stream_qid, "HierarchicalAttribute")
    assert sect_hier_aid == stream_hier_aid  # the attribute id genuinely is shared

    sector_ids = set(model.elements_by_qualifier[sect_qid])
    stream_ids = set(model.elements_by_qualifier[stream_qid])

    for eid in sector_ids:
        rows = model.get_value(eid, sect_hier_aid)
        prev = rows[0]["PREVIOUS_ELEMENT_ID"]
        assert prev == -1 or prev in sector_ids, \
            "a sector's PREVIOUS_ELEMENT_ID must never point at a stream"
    for eid in stream_ids:
        rows = model.get_value(eid, stream_hier_aid)
        prev = rows[0]["PREVIOUS_ELEMENT_ID"]
        assert prev == -1 or prev in stream_ids, \
            "a stream's PREVIOUS_ELEMENT_ID must never point at a sector"


# -- round trip ---------------------------------------------------------------

def test_add_arrow_save_reload_roundtrip(model):
    a, b = _box(model, "Box A"), _box(model, "Box B")
    stream_eid = model.add_arrow(a, ArrowSide.OUTPUT, b, ArrowSide.INPUT, name="Widgets")
    model.add_boundary_arrow(a, ArrowSide.CONTROL, ArrowSide.TOP, direction="in", name="Policy")

    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        model.save(path)
        m2 = Model.load(path)
        sect_qid = m2.find_sector_qualifier()
        stream_qid = m2.find_stream_qualifier()
        assert len(m2.elements_by_qualifier[sect_qid]) == 2
        assert len(m2.elements_by_qualifier[stream_qid]) == 2
        assert m2.get_value(stream_eid, m2.find_attribute(stream_qid, "F_STREAM_NAME")) == "Widgets"
    finally:
        os.unlink(path)


def test_new_crosspoint_id_on_empty_file():
    m = new_model("Root Diagram")
    assert m.find_sector_qualifier() is None
    assert m.new_crosspoint_id() == 1
