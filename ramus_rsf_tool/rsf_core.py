"""
rsf_core.py -- Low-level reader/writer for Ramus (.rsf) files.

A .rsf file (Ramus IDEF0/DFD Modeler, https://github.com/Vitaliy-Yakovchuk/ramus)
is a plain ZIP archive containing a small, generic, *self-describing* EAV
(Entity-Attribute-Value) database dump as a set of XML files, plus assorted
binary "streams" (attached files, GUI session state, print settings, etc.)
stored verbatim at their original paths.

This module implements the container format only: it can losslessly parse
any table file into a `Table` object and re-serialize it byte-for-byte
compatible with what Ramus itself writes (see TableToXML.java /
XMLToTable.java in the original Java source), and it can read/write the two
Java `java.util.Properties` XML files used for metadata and sequences.

See RAMUS_RSF_FORMAT.md (shipped alongside this file) for the full writeup
of how this was reverse engineered from the original GPL-3.0 source.
"""

from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# --------------------------------------------------------------------------
# Byte <-> hex encoding used for BLOB / VARBINARY / bytea columns
# (com.ramussoft.core.impl.TableToXML.ByteAConverter /
#  com.ramussoft.core.impl.XMLToTable.ByteAConverter)
#
# Java encodes each byte b (signed, -128..127) as hex digits[b + 128].
# Because 128 == 0x80, "add 128 mod 256" is exactly "flip the top bit",
# i.e. XOR 0x80. Decoding reverses it: unsigned = hex_byte XOR 0x80.
# --------------------------------------------------------------------------

def bytes_to_rsf_hex(data: bytes) -> str:
    return "".join("%02X" % (b ^ 0x80) for b in data)


def rsf_hex_to_bytes(s: str) -> bytes:
    if not s:
        return b""
    if len(s) % 2 != 0:
        raise ValueError("Строка hex-blob RSF имеет нечётную длину: %r" % s)
    out = bytearray(len(s) // 2)
    for i in range(0, len(s), 2):
        out[i // 2] = int(s[i:i + 2], 16) ^ 0x80
    return bytes(out)


# --------------------------------------------------------------------------
# Java short date/time format used for TIMESTAMP columns:
#   DateFormat.getDateTimeInstance(SHORT, SHORT, Locale.ENGLISH)
# On the JDK the app was built/tested against this renders like:
#   "9/3/09 5:23 PM"   (no comma; 2-digit year; no leading zeros)
# (Java 9+ with the CLDR locale provider instead renders
#   "9/3/09, 5:23 PM" -- note the comma -- so the reader accepts both.)
# --------------------------------------------------------------------------

_DATE_PATTERNS = [
    "%m/%d/%y %I:%M %p",
    "%m/%d/%y, %I:%M %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y, %I:%M %p",
]


def parse_rsf_date(s: str) -> datetime:
    s = s.strip()
    for pat in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, pat)
        except ValueError:
            continue
    raise ValueError("Нераспознанная временная метка RSF: %r" % s)


def format_rsf_date(dt: datetime) -> str:
    # Match the legacy (pre-JDK9 / COMPAT locale data) rendering used by
    # the bundled sample files: "9/3/09 5:23 PM"
    month = dt.month
    day = dt.day
    year = dt.year % 100
    hour12 = dt.hour % 12
    if hour12 == 0:
        hour12 = 12
    ampm = "AM" if dt.hour < 12 else "PM"
    return "%d/%d/%02d %d:%02d %s" % (month, day, year, hour12, dt.minute, ampm)


# --------------------------------------------------------------------------
# Generic table model
# --------------------------------------------------------------------------

# SQL type name -> python codec. Matches the branching in TableToXML/
# XMLToTable exactly (case-insensitive comparisons there).
_INT_TYPES = {"integer", "int4"}
_LONG_TYPES = {"long", "bigint", "int8"}
_BOOL_TYPES = {"bool", "boolean"}
_DOUBLE_TYPES = {"double", "float8"}
_BLOB_TYPES = {"blob", "varbinary", "bytea"}
_CLOB_TYPES = {"clob", "char", "text", "bpchar"}
_TIMESTAMP_TYPES = {"timestamp"}


class Missing:
    """Sentinel: the column had no <f id=".."> tag at all for this row
    (SQL NULL), as opposed to a present-but-empty tag (empty string)."""
    def __repr__(self):
        return "NULL"


NULL = Missing()


@dataclass
class Field:
    id: int
    name: str
    type: str


@dataclass
class Table:
    """One data/**/*.xml table file."""
    source_table: str       # generate-from-table="..."
    prefix: str              # prefix="ramus_"
    fields: List[Field]
    rows: List[Dict[str, Any]]   # keyed by UPPERCASE column name -> decoded value or NULL
    generate_time: str = ""

    # -- convenience -----------------------------------------------------
    def field_names(self) -> List[str]:
        return [f.name for f in self.fields]

    def col(self, name: str) -> List[Any]:
        name = name.upper()
        return [r.get(name, NULL) for r in self.rows]

    def find_rows(self, **eq) -> List[Dict[str, Any]]:
        """find_rows(ELEMENT_ID=5, ATTRIBUTE_ID=3) -> matching rows"""
        eq = {k.upper(): v for k, v in eq.items()}
        out = []
        for r in self.rows:
            if all(r.get(k, NULL) == v for k, v in eq.items()):
                out.append(r)
        return out

    def max_int(self, name: str) -> int:
        best = 0
        name = name.upper()
        for r in self.rows:
            v = r.get(name, NULL)
            if isinstance(v, int) and v > best:
                best = v
        return best

    # -- decode ------------------------------------------------------------
    @staticmethod
    def _decode(text: Optional[str], sql_type: str) -> Any:
        if text is None:
            return NULL
        t = sql_type.lower()
        if t in _INT_TYPES:
            return int(text)
        if t in _LONG_TYPES:
            return int(text)
        if t in _BOOL_TYPES:
            return text.strip().upper() == "TRUE"
        if t in _DOUBLE_TYPES:
            return float(text)
        if t in _BLOB_TYPES:
            return rsf_hex_to_bytes(text)
        if t in _TIMESTAMP_TYPES:
            return text  # kept as the raw Java-formatted string; use
            # parse_rsf_date() explicitly when you need a datetime
        # CLOB / CHAR / TEXT / bpchar / unknown -> plain string
        return text

    @staticmethod
    def _encode(value: Any, sql_type: str) -> Optional[str]:
        if value is NULL or value is None:
            return None
        t = sql_type.lower()
        if t in _INT_TYPES or t in _LONG_TYPES:
            return str(int(value))
        if t in _BOOL_TYPES:
            return "TRUE" if value else "FALSE"
        if t in _DOUBLE_TYPES:
            return repr(float(value)) if False else _java_double_str(float(value))
        if t in _BLOB_TYPES:
            if isinstance(value, (bytes, bytearray)):
                return bytes_to_rsf_hex(bytes(value))
            raise TypeError("Для столбца типа %s ожидались байты" % sql_type)
        if t in _TIMESTAMP_TYPES:
            if isinstance(value, datetime):
                return format_rsf_date(value)
            return str(value)
        return str(value)

    # -- parsing / serialising --------------------------------------------
    @classmethod
    def from_xml_bytes(cls, data: bytes) -> "Table":
        root = ET.fromstring(data)
        assert root.tag == "table", "not a <table> document"
        source_table = root.get("generate-from-table", "")
        prefix = root.get("prefix", "")
        gen_time = root.get("generate-time", "")

        fields_el = root.find("fields")
        fields: List[Field] = []
        id_to_field: Dict[str, Field] = {}
        if fields_el is not None:
            for f_el in fields_el.findall("field"):
                fld = Field(id=int(f_el.get("id")), name=f_el.get("name"),
                            type=f_el.get("type"))
                fields.append(fld)
                id_to_field[f_el.get("id")] = fld

        rows: List[Dict[str, Any]] = []
        data_el = root.find("data")
        if data_el is not None:
            for row_el in data_el.findall("row"):
                row: Dict[str, Any] = {}
                for f_el in row_el.findall("f"):
                    fid = f_el.get("id")
                    fld = id_to_field.get(fid)
                    if fld is None:
                        continue
                    text = f_el.text if f_el.text is not None else ""
                    row[fld.name.upper()] = cls._decode(text, fld.type)
                rows.append(row)

        return cls(source_table=source_table, prefix=prefix, fields=fields,
                    rows=rows, generate_time=gen_time)

    def to_xml_bytes(self) -> bytes:
        root = ET.Element("table", {
            "generate-from-table": self.source_table,
            "generate-time": self.generate_time,
            "prefix": self.prefix,
        })
        fields_el = ET.SubElement(root, "fields")
        for fld in self.fields:
            ET.SubElement(fields_el, "field", {
                "id": str(fld.id), "name": fld.name, "type": fld.type,
            })
        data_el = ET.SubElement(root, "data")
        for row in self.rows:
            row_el = ET.SubElement(data_el, "row")
            for fld in self.fields:
                val = row.get(fld.name.upper(), NULL)
                if val is NULL:
                    continue
                enc = self._encode(val, fld.type)
                if enc is None:
                    continue
                f_el = ET.SubElement(row_el, "f", {"id": str(fld.id)})
                f_el.text = enc
        body = ET.tostring(root, encoding="UTF-8", xml_declaration=True)
        return body


def _java_double_str(v: float) -> str:
    """Approximate java.lang.Double.toString() closely enough for RSF
    purposes (positions/sizes): always show a decimal point."""
    if v == int(v) and abs(v) < 1e15:
        return "%.1f" % v
    return repr(v)


# --------------------------------------------------------------------------
# Java Properties XML (application_metadata.xml, sequences.xml)
# --------------------------------------------------------------------------

_PROPS_DOCTYPE = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="no"?>\n'
    b'<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">\n'
)


def parse_properties_xml(data: bytes) -> Dict[str, str]:
    # strip the DOCTYPE line (ElementTree chokes on external DTDs) then parse
    text = data.decode("utf-8")
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text)
    root = ET.fromstring(text)
    out = {}
    for entry in root.findall("entry"):
        out[entry.get("key")] = entry.text or ""
    return out


def build_properties_xml(props: Dict[str, str], comment: str = "") -> bytes:
    buf = io.BytesIO()
    buf.write(_PROPS_DOCTYPE)
    buf.write(b"<properties>\n")
    if comment:
        buf.write(("<comment>%s</comment>\n" % _xml_escape(comment)).encode("utf-8"))
    for k, v in props.items():
        buf.write(('<entry key="%s">%s</entry>\n' %
                    (_xml_escape(k), _xml_escape(v))).encode("utf-8"))
    buf.write(b"</properties>\n")
    return buf.getvalue()


def _xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


# --------------------------------------------------------------------------
# Whole-archive container
# --------------------------------------------------------------------------

@dataclass
class RsfArchive:
    """The full contents of a .rsf ZIP: parsed `data/**/*.xml` tables,
    parsed Properties files, and every other entry kept as raw bytes so
    that re-saving never silently drops GUI state / attachments / etc."""

    tables: Dict[str, Table] = field(default_factory=dict)      # zip path -> Table
    properties: Dict[str, Dict[str, str]] = field(default_factory=dict)  # zip path -> {k:v}
    raw: Dict[str, bytes] = field(default_factory=dict)          # zip path -> bytes (everything else)
    order: List[str] = field(default_factory=list)               # original zip entry order

    @classmethod
    def load(cls, path: str) -> "RsfArchive":
        arc = cls()
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                name = info.filename
                arc.order.append(name)
                data = zf.read(name)
                if name.startswith("data/") and name.endswith(".xml") and \
                        name not in ("data/application_metadata.xml", "data/sequences.xml"):
                    try:
                        arc.tables[name] = Table.from_xml_bytes(data)
                        continue
                    except ET.ParseError:
                        pass  # fall through, keep raw
                if name in ("data/application_metadata.xml", "data/sequences.xml"):
                    arc.properties[name] = parse_properties_xml(data)
                    continue
                arc.raw[name] = data
        return arc

    def save(self, path: str) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in self.order:
                if name in self.tables:
                    zf.writestr(name, self.tables[name].to_xml_bytes())
                elif name in self.properties:
                    comment = ("Ramus file metadata" if "metadata" in name
                               else "Sequence list file")
                    zf.writestr(name, build_properties_xml(self.properties[name], comment))
                else:
                    zf.writestr(name, self.raw[name])
            # anything added after load() that wasn't in the original order
            for name in self.tables:
                if name not in self.order:
                    zf.writestr(name, self.tables[name].to_xml_bytes())
            for name in self.properties:
                if name not in self.order:
                    comment = ("Ramus file metadata" if "metadata" in name
                               else "Sequence list file")
                    zf.writestr(name, build_properties_xml(self.properties[name], comment))
            for name in self.raw:
                if name not in self.order:
                    zf.writestr(name, self.raw[name])

    # -- convenience -------------------------------------------------------
    def get_table(self, path: str) -> Optional[Table]:
        return self.tables.get(path)

    def require_table(self, path: str) -> Table:
        t = self.tables.get(path)
        if t is None:
            raise KeyError("таблица отсутствует в этом файле: %s" % path)
        return t
