import io
import zipfile

from ramus_rsf_tool.rsf_core import (
    Table, Field, RsfArchive, NULL, bytes_to_rsf_hex, rsf_hex_to_bytes,
    parse_rsf_date, format_rsf_date, parse_properties_xml, build_properties_xml,
)


def test_bytes_hex_roundtrip():
    data = bytes(range(256))
    hexed = bytes_to_rsf_hex(data)
    assert rsf_hex_to_bytes(hexed) == data
    # not standard hex: 0x00 encodes as the XOR-0x80'd byte, i.e. "80"
    assert bytes_to_rsf_hex(b"\x00") == "80"
    assert rsf_hex_to_bytes("80") == b"\x00"


def test_date_roundtrip():
    from datetime import datetime
    dt = datetime(2009, 9, 3, 17, 23)
    s = format_rsf_date(dt)
    assert s == "9/3/09 5:23 PM"
    parsed = parse_rsf_date(s)
    assert (parsed.month, parsed.day, parsed.year, parsed.hour, parsed.minute) == (9, 3, 2009, 17, 23)
    # comma variant (JDK9+ CLDR) also accepted
    parsed2 = parse_rsf_date("9/3/09, 5:23 PM")
    assert parsed2 == parsed


def test_table_xml_roundtrip_and_null_handling():
    fields = [
        Field(id=0, name="ELEMENT_ID", type="BIGINT"),
        Field(id=1, name="ELEMENT_NAME", type="CLOB"),
        Field(id=2, name="FLAG", type="BOOLEAN"),
    ]
    rows = [
        {"ELEMENT_ID": 4, "ELEMENT_NAME": "Infrastructure", "FLAG": True},
        {"ELEMENT_ID": 1, "ELEMENT_NAME": "", "FLAG": NULL},  # present-but-empty vs NULL
    ]
    t = Table(source_table="elements", prefix="ramus_", fields=fields, rows=rows)
    xml_bytes = t.to_xml_bytes()
    assert b"TRUE" in xml_bytes
    t2 = Table.from_xml_bytes(xml_bytes)
    assert t2.rows[0] == {"ELEMENT_ID": 4, "ELEMENT_NAME": "Infrastructure", "FLAG": True}
    # row 1: ELEMENT_NAME present-but-empty -> "" ; FLAG absent -> no key at
    # all in the row dict (SQL NULL), so .get(..., NULL) is the sentinel
    assert t2.rows[1]["ELEMENT_NAME"] == ""
    assert "FLAG" not in t2.rows[1]
    assert t2.rows[1].get("FLAG", NULL) is NULL


def test_properties_xml_roundtrip():
    props = {"ApplicationName": "Ramus", "PluginCount": "2"}
    data = build_properties_xml(props, comment="test")
    assert parse_properties_xml(data) == props


def test_archive_roundtrip_preserves_raw_entries():
    arc = RsfArchive()
    fields = [Field(id=0, name="QUALIFIER_ID", type="BIGINT"),
              Field(id=1, name="QUALIFIER_NAME", type="CLOB")]
    t = Table(source_table="qualifiers", prefix="ramus_", fields=fields,
              rows=[{"QUALIFIER_ID": 1, "QUALIFIER_NAME": "Root"}])
    arc.tables["data/qualifiers.xml"] = t
    arc.raw["user/window_state.bin"] = b"\x01\x02\x03opaque"
    arc.properties["data/application_metadata.xml"] = {"ApplicationName": "Ramus"}
    arc.order = ["data/qualifiers.xml", "user/window_state.bin", "data/application_metadata.xml"]

    buf = io.BytesIO()
    # RsfArchive.save() takes a path; write via a temp file substitute
    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".rsf")
    os.close(fd)
    try:
        arc.save(path)
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            assert names == {"data/qualifiers.xml", "user/window_state.bin",
                              "data/application_metadata.xml"}
            assert zf.read("user/window_state.bin") == b"\x01\x02\x03opaque"

        arc2 = RsfArchive.load(path)
        assert arc2.tables["data/qualifiers.xml"].rows == t.rows
        assert arc2.raw["user/window_state.bin"] == b"\x01\x02\x03opaque"
        assert arc2.properties["data/application_metadata.xml"] == {"ApplicationName": "Ramus"}
    finally:
        os.unlink(path)
