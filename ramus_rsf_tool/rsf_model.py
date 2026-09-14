"""
rsf_model.py -- Semantic layer on top of rsf_core.py for Ramus (.rsf) files.

rsf_core.py understands the *container* (zip + generic self-describing XML
tables). This module understands the *data model* Ramus builds on top of
that container: a generic Entity-Attribute-Value (EAV) store where

    qualifiers          "classes" / categories (an IDEF0 diagram's set of
                         function-boxes is one qualifier; the built-in
                         "Attributes" browser is another; etc.)
    elements            "instances" of a qualifier (a function box, an
                         arrow sector, a row in the attribute browser...)
    attributes          "fields" that can be attached to elements of a
                         given qualifier (Name, Description, F_BOUNDS,
                         F_BACKGROUND, ...)
    qualifiers_attributes  which attributes are attached to which qualifier
    attribute_<type>s   the actual values, one physical table per
                         AttributeType (plugin_name, type_name), keyed by
                         (attribute_id, element_id)

See RAMUS_RSF_FORMAT.md for the full write-up (including which parts of
this were verified against real Ramus source vs. inferred/partially
verified, in particular the Sector/SectorPoint/SectorBorder "arrow
routing" tables).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field as _dataclass_field
from typing import Any, Dict, List, Optional, Tuple, Union

from .rsf_core import RsfArchive, Table, Field, NULL, parse_rsf_date, format_rsf_date


# ==========================================================================
# Attribute-type -> physical table map
#
# mode:
#   'scalar' -- exactly one row per (attribute_id, element_id); one value
#               column. get -> python scalar, set -> replace it.
#   'struct' -- exactly one row per (attribute_id, element_id); several
#               named columns. get/set a dict of {COLUMN: value}.
#   'list'   -- zero or more rows may share (attribute_id, element_id)
#               (there are additional primary-key columns). get returns a
#               list of row-dicts; there's no single "set", use the raw
#               table API (`Model.table(path)`) to add/remove rows.
#   'stream' -- not an EAV row at all. The value lives as a raw zip entry
#               at /elements/<element_id>/<attribute_id>/<plugin>/<file>,
#               and its existence is mirrored by one row in data/streams.xml.
# ==========================================================================

@dataclass
class TypeInfo:
    table_path: Optional[str]
    mode: str
    columns: Optional[List[str]] = None
    file_name: Optional[str] = None   # for mode == 'stream'


TYPE_MAP: Dict[Tuple[str, str], TypeInfo] = {
    # --- Core, simple scalar types (core-simple-attributes/.../*.java) ---
    ("Core", "Text"):     TypeInfo("data/Core/attribute_texts.xml", "scalar", ["VALUE"]),
    ("Core", "Long"):     TypeInfo("data/Core/attribute_longs.xml", "scalar", ["VALUE"]),
    ("Core", "Double"):   TypeInfo("data/Core/attribute_doubles.xml", "scalar", ["VALUE"]),
    ("Core", "Date"):     TypeInfo("data/Core/attribute_dates.xml", "scalar", ["VALUE"]),
    ("Core", "Currency"): TypeInfo("data/Core/attribute_currencies.xml", "scalar", ["VALUE"]),
    ("Core", "Boolean"):  TypeInfo("data/Core/attribute_booleans.xml", "scalar", ["VALUE"]),
    ("Core", "Variant"):  TypeInfo("data/Core/attribute_variants.xml", "scalar", ["VARIANT_ID"]),
    ("Core", "Icon"):     TypeInfo("data/Core/attribute_icons.xml", "struct", ["ICON", "NAME"]),

    # ONE_TO_MANY in the Java source -> several rows may share
    # (attribute_id, element_id); each row is one link / one tree-slot.
    ("Core", "OtherElement"):  TypeInfo("data/Core/attribute_other_elements.xml", "list", ["OTHER_ELEMENT"]),
    ("Core", "Hierarchical"):  TypeInfo("data/Core/attribute_hierarchicals.xml", "list",
                                         ["ICON_ID", "PARENT_ELEMENT_ID", "PREVIOUS_ELEMENT_ID"]),

    # file-backed (HTML page / arbitrary attachment) -- not simple EAV rows
    ("Core", "HTMLText"): TypeInfo(None, "stream", file_name="index.html"),
    ("Core", "File"):     TypeInfo(None, "stream", file_name=None),  # actual name is attribute-specific

    # --- IDEF0 plugin types (idef0-core/.../attribute/*.java) ---
    ("IDEF0", "FRectangle"): TypeInfo("data/IDEF0/attribute_rectangles.xml", "struct",
                                       ["X", "Y", "WIDTH", "HEIGHT"]),
    ("IDEF0", "Color"):      TypeInfo("data/IDEF0/attribute_colors.xml", "scalar", ["COLOR"]),
    ("IDEF0", "Font"):       TypeInfo("data/IDEF0/attribute_fonts.xml", "struct",
                                       ["NAME", "STYLE", "SIZE"]),
    ("IDEF0", "Status"):     TypeInfo("data/IDEF0/attribute_statuses.xml", "struct",
                                       ["TYPE", "OTHER_NAME"]),
    ("IDEF0", "Type"):       TypeInfo("data/IDEF0/attribute_function_types.xml", "scalar", ["TYPE"]),
    ("IDEF0", "OunerId"):    TypeInfo("data/IDEF0/attribute_function_ouners.xml", "scalar", ["OUNER_ID"]),
    ("IDEF0", "DecompositionType"): TypeInfo("data/IDEF0/attribute_decomposition_types.xml",
                                              "scalar", ["TYPE"]),
    ("IDEF0", "VisualData"): TypeInfo("data/IDEF0/attribute_visual_datas.xml", "scalar", ["DATA"]),
    ("IDEF0", "AnyToAny"):   TypeInfo("data/IDEF0/attribute_any_to_any_elements.xml", "list",
                                       ["OTHER_ELEMENT"]),
    ("IDEF0", "ProjectPreferences"): TypeInfo("data/IDEF0/attribute_model_preferences.xml", "struct",
                                               ["CHANGE_DATE", "CREATE_DATE", "DEFINITION",
                                                "PROJECT_AUTOR", "PROJECT_NAME", "USED_AT"]),

    # --- Arrow / connection routing -- readable & editable generically via
    # Model.table(path), but treat as opaque: not enough of the runtime
    # semantics (crosspoint graph, ordinate allocation) was recovered from
    # static analysis alone to safely synthesize *new* arrows. See the
    # "Known limitation: arrows" section of RAMUS_RSF_FORMAT.md.
    ("IDEF0", "Sector"): TypeInfo("data/IDEF0/attribute_sectors.xml", "struct",
                                   ["ALTERNATIVE_TEXT", "CREATE_POS", "CREATE_STATE",
                                    "SHOW_TEXT", "VISUAL_ATTRIBUTES", "TEXT_ALIGMENT"]),
    ("IDEF0", "SectorBorder"): TypeInfo("data/IDEF0/attribute_sector_borders.xml", "struct",
                                         ["BORDER_TYPE", "CROSSPOINT", "FUNCTION",
                                          "FUNCTION_TYPE", "TUNNEL_SOFT"]),
    ("IDEF0", "SectorPoint"): TypeInfo("data/IDEF0/attribute_sector_points.xml", "list",
                                        ["X_ORDINATE_ID", "Y_ORDINATE_ID", "X_POSITION",
                                         "Y_POSITION", "POINT_TYPE", "POSITION"]),
    ("IDEF0", "SectorProperties"): TypeInfo("data/IDEF0/attribute_sector_properties.xml", "struct",
                                             ["SHOW_TILDA", "SHOW_TEXT", "TRANSPARENT", "TILDA_POS",
                                              "TEXT_X", "TEXT_Y", "TEXT_WIDTH", "TEXT_HIEGHT"]),

    ("Eval", "Function"): TypeInfo("data/Eval/attribute_functions.xml", "struct",
                                    ["AUTOCHANGE", "FUNCTION", "QUALIFIER_ATTRIBUTE_ID",
                                     "QUALIFIER_TABLE_ATTRIBUTE_ID"]),
}


def _key_cols(mode: str) -> List[str]:
    return ["ATTRIBUTE_ID", "ELEMENT_ID"]


# --------------------------------------------------------------------------
# IDEF0 arrows -- side/tunnel constants and the Sector VISUAL_ATTRIBUTES
# blob codec.
#
# Everything here was verified against the real Ramus GPL-3.0 source
# (idef0-common: SectorRefactor.java, PaintSector.java, NSector.java,
# NSectorBorder.java, NCrosspoint.java, AbstractCrosspoint.java,
# Crosspoint.java, DataSaver.java/DataLoader.java; idef0-core:
# IDEF0Plugin.java) cross-checked against the real attribute_sectors.xml/
# attribute_sector_borders.xml data in all three sample .rsf files bundled
# with that repository. See RAMUS_RSF_FORMAT.md section 10 for the full
# write-up, including what's *not* covered here (mainly: multi-segment/
# bent arrows and manually-repositioned arrows, which additionally use
# the SectorPoint table this module doesn't populate).
# --------------------------------------------------------------------------

class ArrowSide:
    """Which edge of a function box -- or, for a boundary arrow, of the
    diagram page itself -- a sector border touches. Values match
    com.ramussoft.pb.idef.visual.MovingPanel's side constants exactly:
    confirmed from source, SectorRefactor.java compares a border's
    FUNCTION_TYPE directly against MovingPanel.RIGHT/LEFT. Standard IDEF0
    usage: LEFT=Input, TOP=Control, RIGHT=Output, BOTTOM=Mechanism."""
    RIGHT = 0
    BOTTOM = 1
    LEFT = 2
    TOP = 3

    OUTPUT = RIGHT
    MECHANISM = BOTTOM
    INPUT = LEFT
    CONTROL = TOP


class TunnelType:
    """Values for a SectorBorder's TUNNEL_SOFT column (from
    com.ramussoft.pb.Crosspoint's constants -- the column name is
    misleading; it holds one of these four, not a plain soft/hard flag).
    SOFT/SIMPLE_SOFT are IDEF0's tunnel notation: the "(" ")" bracket
    marks meaning an ICOM arrow isn't shown at the parent or child level."""
    HARD = 0
    SOFT = 1
    NONE = 2
    SIMPLE_SOFT = 3


def _va_bool(v: bool) -> bytes:
    return bytes([1 if v else 0])


def _va_int(v: int) -> bytes:
    return int(v).to_bytes(4, "little", signed=True)


def _va_double(v: float) -> bytes:
    import struct as _struct
    return _struct.pack("<d", float(v))


def _va_string(s: Optional[str]) -> bytes:
    if s is None:
        return _va_int(-1)
    data = s.encode("utf-8")
    return _va_int(len(data)) + data


def encode_sector_visual_attributes(
        *, line_width: float = 1.5, cap: int = 2, join: int = 0,
        dash_phase: float = 0.0, miter_limit: float = 10.0,
        dash: Optional[List[float]] = None,
        font_name: str = "Dialog", font_size: int = 10, font_style: int = 0,
        color: Tuple[int, int, int] = (0, 0, 0)) -> bytes:
    """Build an IDEF0.Sector VISUAL_ATTRIBUTES blob, matching the exact
    binary format `com.dsoft.utils.DataSaver.saveStroke/saveFont/
    saveColor` write (a small custom little-endian serialization, not
    Java's built-in object serialization). Defaults reproduce a real
    Ramus-drawn default arrow byte-for-byte (verified by decoding a real
    sample sector's blob with the mirrored reader and finding zero
    leftover bytes) -- Dialog 10pt plain, black, a 1.5pt stroke with
    CAP_SQUARE/JOIN_MITER and miter limit 10, which are Ramus's
    DEFAULT_ARROW_FONT/DEFAULT_ARROW_COLOR/DEFAULT_ARROW_STROKE options.

    An *empty* blob is also valid -- PaintSector.loadVisuals() special-
    cases a 0-length VISUAL_ATTRIBUTES and falls back to the same
    defaults -- but this gives you the literal bytes a real "just drawn,
    never restyled" arrow has, and lets you customize line width/font/
    color if you want to."""
    out = bytearray()
    # stroke: saveBoolean(true) "is BasicStroke" + fields + dash array
    out += _va_bool(True)
    out += _va_double(line_width)
    out += _va_int(cap)
    out += _va_int(join)
    out += _va_double(dash_phase)
    out += _va_double(miter_limit)
    if dash:
        out += _va_int(len(dash))
        for d in dash:
            out += _va_double(d)
    else:
        out += _va_int(-1)
    # font: saveBoolean(false) "not null" + saveBoolean(true) "new, not cached"
    out += _va_bool(False)
    out += _va_bool(True)
    out += _va_string(font_name)
    out += _va_int(font_size)
    out += _va_int(font_style)
    # color: saveBoolean(true) "new, not cached"
    out += _va_bool(True)
    out += _va_int(color[0])
    out += _va_int(color[1])
    out += _va_int(color[2])
    return bytes(out)


# A real Ramus-drawn default arrow's exact VISUAL_ATTRIBUTES bytes (see
# encode_sector_visual_attributes()'s docstring) -- computed once at
# import time from that same function so it's provably consistent with it.
_DEFAULT_SECTOR_VISUAL_ATTRIBUTES = encode_sector_visual_attributes()

class Model:
    """Semantic view over an RsfArchive. Construct with Model(archive) or
    Model.load(path)."""

    def __init__(self, archive: RsfArchive):
        self.arc = archive
        self._reindex()

    @classmethod
    def load(cls, path: str) -> "Model":
        return cls(RsfArchive.load(path))

    def save(self, path: str) -> None:
        self.arc.save(path)

    # -- low level passthrough ---------------------------------------------
    def table(self, path: str) -> Table:
        """Direct access to any raw table by its zip path, e.g.
        model.table('data/IDEF0/attribute_sectors.xml'). Works for every
        table in the file, including ones with no semantic mapping above."""
        t = self.arc.get_table(path)
        if t is None:
            raise KeyError("В этом файле нет такой таблицы: %s" % path)
        return t

    def table_paths(self) -> List[str]:
        return sorted(self.arc.tables.keys())

    # -- indexing ------------------------------------------------------------
    def _reindex(self):
        a = self.arc
        self.t_qualifiers = a.get_table("data/qualifiers.xml")
        self.t_elements = a.get_table("data/elements.xml")
        self.t_attributes = a.get_table("data/attributes.xml")
        self.t_qual_attrs = a.get_table("data/qualifiers_attributes.xml")

        self.qualifiers: Dict[int, Dict[str, Any]] = {}
        if self.t_qualifiers:
            for r in self.t_qualifiers.rows:
                self.qualifiers[r["QUALIFIER_ID"]] = r

        self.elements: Dict[int, Dict[str, Any]] = {}
        self.elements_by_qualifier: Dict[int, List[int]] = {}
        if self.t_elements:
            for r in self.t_elements.rows:
                eid = r["ELEMENT_ID"]
                self.elements[eid] = r
                self.elements_by_qualifier.setdefault(r.get("QUALIFIER_ID"), []).append(eid)

        self.attributes: Dict[int, Dict[str, Any]] = {}
        self.attribute_id_by_name: Dict[str, List[int]] = {}
        if self.t_attributes:
            for r in self.t_attributes.rows:
                aid = r["ATTRIBUTE_ID"]
                self.attributes[aid] = r
                name = r.get("ATTRIBUTE_NAME")
                if isinstance(name, str):
                    self.attribute_id_by_name.setdefault(name, []).append(aid)

        self.qualifier_attribute_ids: Dict[int, List[int]] = {}
        if self.t_qual_attrs:
            for r in self.t_qual_attrs.rows:
                qid = r["QUALIFIER_ID"]
                self.qualifier_attribute_ids.setdefault(qid, []).append(r["ATTRIBUTE_ID"])

        # cache of loaded per-type value tables, path -> Table
        self._value_tables: Dict[str, Table] = {}

    def refresh(self):
        """Call after directly mutating tables via .table(...) if you then
        want the qualifier/element/attribute indexes to reflect the change."""
        self._reindex()

    # -- lookups -------------------------------------------------------------
    def qualifier_name(self, qid: int) -> Optional[str]:
        q = self.qualifiers.get(qid)
        return q.get("QUALIFIER_NAME") if q else None

    def find_qualifier(self, name: str) -> Optional[int]:
        for qid, q in self.qualifiers.items():
            if q.get("QUALIFIER_NAME") == name:
                return qid
        return None

    def attribute_type(self, aid: int) -> Optional[Tuple[str, str]]:
        a = self.attributes.get(aid)
        if not a:
            return None
        return (a.get("ATTRIBUTE_TYPE_PLUGIN_NAME"), a.get("ATTRIBUTE_TYPE_NAME"))

    def find_attribute(self, qualifier_id: int, name: str) -> Optional[int]:
        """Find the attribute id named `name` that's attached to
        `qualifier_id` (e.g. find_attribute(qid, 'Name'),
        find_attribute(qid, 'F_BOUNDS'))."""
        candidates = set(self.attribute_id_by_name.get(name, []))
        for aid in self.qualifier_attribute_ids.get(qualifier_id, []):
            if aid in candidates:
                return aid
        return None

    def element_qualifier(self, element_id: int) -> Optional[int]:
        e = self.elements.get(element_id)
        return e.get("QUALIFIER_ID") if e else None

    # -- value tables ----------------------------------------------------
    def _vtable(self, path: str) -> Table:
        t = self._value_tables.get(path)
        if t is None:
            t = self.arc.get_table(path)
            if t is None:
                raise KeyError(
                    "В этом файле нет таблицы %s (тип атрибута, который она "
                    "обслуживает, ни разу не использовался в этом файле)." % path)
            self._value_tables[path] = t
        return t

    def _vtable_or_none(self, path: str) -> Optional[Table]:
        t = self._value_tables.get(path)
        if t is not None:
            return t
        t = self.arc.get_table(path)
        if t is not None:
            self._value_tables[path] = t
        return t

    # -- generic attribute value get/set -------------------------------------
    def get_value(self, element_id: int, attribute_id: int) -> Any:
        """Read the value of `attribute_id` on `element_id`, decoded
        according to the attribute's declared type. Returns:
          - a python scalar for 'scalar' types (str/int/float/bytes/None)
          - a dict for 'struct' types
          - a list of dicts for 'list' types
          - bytes for 'stream' types (or None if unset)
        Raises KeyError if the attribute id is unknown, and returns None
        (scalar/struct) or [] (list) if the type is known but this
        element simply has no value set for it.
        """
        atype = self.attribute_type(attribute_id)
        if atype is None:
            raise KeyError("Неизвестный id атрибута %s" % attribute_id)
        info = TYPE_MAP.get(atype)
        if info is None:
            raise KeyError("Нет известного сопоставления с физической таблицей для "
                            "типа атрибута %s (id атрибута %s). Используйте model.table(...), "
                            "чтобы изучить его по сырому пути, если вы его знаете."
                            % (atype, attribute_id))
        if info.mode == "stream":
            path = self._stream_path(element_id, attribute_id, atype, info)
            return self.arc.raw.get(path.lstrip("/"))

        t = self._vtable_or_none(info.table_path)
        if t is None:
            return [] if info.mode == "list" else None
        rows = t.find_rows(ATTRIBUTE_ID=attribute_id, ELEMENT_ID=element_id)
        if info.mode == "list":
            return rows
        if not rows:
            return None
        row = rows[0]
        if info.mode == "scalar":
            return row.get(info.columns[0])
        return {c: row.get(c) for c in info.columns}

    def set_value(self, element_id: int, attribute_id: int, value: Any) -> None:
        """Write the value of `attribute_id` on `element_id`. `value` must
        match the attribute's mode: a scalar for 'scalar' types, a dict of
        {COLUMN: value} for 'struct' types (partial dicts are merged into
        the existing row), or bytes for 'stream' types. Not valid for
        'list'-mode types -- use model.table(path) directly for those."""
        atype = self.attribute_type(attribute_id)
        if atype is None:
            raise KeyError("Неизвестный id атрибута %s" % attribute_id)
        info = TYPE_MAP.get(atype)
        if info is None:
            raise KeyError("Нет известного сопоставления с физической таблицей для "
                            "типа атрибута %s (id атрибута %s)" % (atype, attribute_id))

        if info.mode == "stream":
            path = self._stream_path(element_id, attribute_id, atype, info)
            self._set_stream(path, value)
            return

        if info.mode == "list":
            raise ValueError("Тип атрибута %s имеет вид «список»; используйте "
                              "model.table(%r), чтобы добавлять/удалять строки напрямую."
                              % (atype, info.table_path))

        t = self._get_or_create_vtable(info.table_path, atype)
        rows = t.find_rows(ATTRIBUTE_ID=attribute_id, ELEMENT_ID=element_id)
        if rows:
            row = rows[0]
        else:
            row = {"ATTRIBUTE_ID": attribute_id, "ELEMENT_ID": element_id}
            t.rows.append(row)
        if info.mode == "scalar":
            row[info.columns[0]] = value
        else:
            if not isinstance(value, dict):
                raise TypeError("атрибут в режиме struct ожидает словарь с ключами "
                                 "%s" % info.columns)
            for k, v in value.items():
                row[k.upper()] = v

    def delete_value(self, element_id: int, attribute_id: int) -> None:
        """Remove any stored value for (element_id, attribute_id) --
        equivalent to it never having been set."""
        atype = self.attribute_type(attribute_id)
        if atype is None:
            return
        info = TYPE_MAP.get(atype)
        if info is None or info.mode == "stream":
            return
        t = self._vtable_or_none(info.table_path)
        if t is None:
            return
        t.rows = [r for r in t.rows
                  if not (r.get("ATTRIBUTE_ID") == attribute_id and
                          r.get("ELEMENT_ID") == element_id)]

    def _get_or_create_vtable(self, path: str, atype: Tuple[str, str]) -> Table:
        t = self._vtable_or_none(path)
        if t is not None:
            return t
        # The table doesn't exist yet in this file (this attribute type has
        # never been used). Create it fresh -- see RAMUS_RSF_FORMAT.md for
        # why this is safe (missing tables are simply treated as "no rows"
        # on load).
        info = TYPE_MAP[atype]
        cols = ["ATTRIBUTE_ID", "ELEMENT_ID"] + list(info.columns)
        sql_types = _guess_sql_types(cols)
        fields = [Field(id=i, name=c, type=sql_types[c]) for i, c in enumerate(cols)]
        t = Table(source_table=posixpath.basename(path)[:-4], prefix="ramus_",
                  fields=fields, rows=[])
        self.arc.tables[path] = t
        self.arc.order.append(path)
        self._value_tables[path] = t
        return t

    # -- stream ("file") backed attributes -----------------------------------
    def _stream_path(self, element_id, attribute_id, atype, info: TypeInfo) -> str:
        plugin = atype[0]
        fname = info.file_name or "file"
        return "/elements/%d/%d/%s/%s" % (element_id, attribute_id, plugin, fname)

    def _set_stream(self, path: str, data: Optional[bytes]) -> None:
        key = path.lstrip("/")
        streams = self.arc.get_table("data/streams.xml")
        if data is None:
            self.arc.raw.pop(key, None)
            if streams is not None:
                streams.rows = [r for r in streams.rows if r.get("STREAM_ID") != path]
            return
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.arc.raw[key] = data
        if key not in self.arc.order:
            self.arc.order.append(key)
        if streams is None:
            fields = [Field(id=0, name="STREAM_ID", type="CLOB")]
            streams = Table(source_table="streams", prefix="ramus_", fields=fields, rows=[])
            self.arc.tables["data/streams.xml"] = streams
            self.arc.order.append("data/streams.xml")
        if not any(r.get("STREAM_ID") == path for r in streams.rows):
            streams.rows.append({"STREAM_ID": path})

    # -- element-level convenience --------------------------------------------
    def element_attributes(self, element_id: int, resolve_names: bool = True) -> Dict[str, Any]:
        """All attribute values set for `element_id`, keyed by attribute
        name (or 'attr_<id>' if resolve_names finds no name / a clash)."""
        qid = self.element_qualifier(element_id)
        out: Dict[str, Any] = {}
        if qid is None:
            return out
        for aid in self.qualifier_attribute_ids.get(qid, []):
            a = self.attributes.get(aid, {})
            name = a.get("ATTRIBUTE_NAME") if resolve_names else None
            key = name if isinstance(name, str) and name else ("attr_%d" % aid)
            try:
                val = self.get_value(element_id, aid)
            except KeyError:
                continue
            if val in (None, [], {}):
                continue
            if isinstance(val, bytes):
                val = {"__bytes_len__": len(val)}
            out[key] = val
        return out

    def new_element_id(self) -> int:
        return (self.t_elements.max_int("ELEMENT_ID") if self.t_elements else 0) + 1

    def new_qualifier_id(self) -> int:
        return (self.t_qualifiers.max_int("QUALIFIER_ID") if self.t_qualifiers else 0) + 1

    def new_attribute_id(self) -> int:
        return (self.t_attributes.max_int("ATTRIBUTE_ID") if self.t_attributes else 0) + 1

    def add_element(self, qualifier_id: int, name: str = "") -> int:
        """Create a bare element under `qualifier_id` (no attribute values
        yet -- use set_value / helpers below to populate it) and return
        its new element id. Safe against ID collisions: Ramus resyncs its
        own ID sequences from MAX(id) on every create (see
        RAMUS_RSF_FORMAT.md, "ID allocation")."""
        if self.t_elements is None:
            raise RuntimeError("В этом файле нет таблицы data/elements.xml")
        eid = self.new_element_id()
        self.t_elements.rows.append({
            "ELEMENT_ID": eid, "ELEMENT_NAME": name, "QUALIFIER_ID": qualifier_id,
        })
        self.elements[eid] = self.t_elements.rows[-1]
        self.elements_by_qualifier.setdefault(qualifier_id, []).append(eid)
        return eid

    def set_element_name(self, element_id: int, name: str) -> None:
        e = self.elements.get(element_id)
        if e is None:
            raise KeyError("Нет такого элемента: %s" % element_id)
        e["ELEMENT_NAME"] = name

    def delete_element(self, element_id: int) -> None:
        """Remove an element and every attribute value row that references
        it (across every value table currently loaded from this file).
        Does not touch qualifiers/attributes/formulas bookkeeping."""
        if element_id in self.elements:
            qid = self.elements[element_id].get("QUALIFIER_ID")
            self.t_elements.rows = [r for r in self.t_elements.rows
                                     if r.get("ELEMENT_ID") != element_id]
            del self.elements[element_id]
            if qid in self.elements_by_qualifier:
                self.elements_by_qualifier[qid] = [
                    e for e in self.elements_by_qualifier[qid] if e != element_id]
        for path, t in list(self.arc.tables.items()):
            if "ELEMENT_ID" in {f.name.upper() for f in t.fields}:
                t.rows = [r for r in t.rows if r.get("ELEMENT_ID") != element_id]

    # -- IDEF0 "function box" convenience -------------------------------------
    # These wrap the F_* system attributes documented in RAMUS_RSF_FORMAT.md.
    # They look the attribute ids up by name on the *target element's own
    # qualifier* each time, so they work on any qualifier that carries the
    # standard IDEF0 function attribute set (which checkIDEF0Attributes()
    # guarantees for every function-box qualifier Ramus itself creates).

    def set_name(self, element_id: int, name: str) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "Name")
        if aid is None:
            self.set_element_name(element_id, name)
            return
        self.set_value(element_id, aid, name)
        self.set_element_name(element_id, name)  # keep ELEMENT_NAME mirrored too

    def set_bounds(self, element_id: int, x: float, y: float, width: float, height: float) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "F_BOUNDS")
        if aid is None:
            raise KeyError("У квалификатора %s нет атрибута F_BOUNDS" % qid)
        self.set_value(element_id, aid, {"X": x, "Y": y, "WIDTH": width, "HEIGHT": height})

    def set_background(self, element_id: int, argb: int) -> None:
        self._set_named_color(element_id, "F_BACKGROUND", argb)

    def set_foreground(self, element_id: int, argb: int) -> None:
        self._set_named_color(element_id, "F_FOREGROUND", argb)

    def _set_named_color(self, element_id: int, attr_name: str, argb: int) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, attr_name)
        if aid is None:
            raise KeyError("У квалификатора %s нет атрибута %s" % (qid, attr_name))
        self.set_value(element_id, aid, argb)

    def set_font(self, element_id: int, name: str, style: int, size: int) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "F_FONT")
        if aid is None:
            raise KeyError("У квалификатора %s нет атрибута F_FONT" % qid)
        self.set_value(element_id, aid, {"NAME": name, "STYLE": style, "SIZE": size})

    def set_status(self, element_id: int, status_type: int, other_name: str = "") -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "F_STATUS")
        if aid is None:
            raise KeyError("У квалификатора %s нет атрибута F_STATUS" % qid)
        self.set_value(element_id, aid, {"TYPE": status_type, "OTHER_NAME": other_name})

    def clone_qualifier_as_container(self, source_qualifier_id: int, new_name: str,
                                      system: bool = False) -> int:
        """Create a brand-new qualifier that carries the *same attribute
        set* as `source_qualifier_id` (copies every data/qualifiers_attributes.xml
        row). This is the recommended way to create a new, valid
        'function box container' (i.e. a new IDEF0 diagram page) without
        hand-bootstrapping the whole F_* system attribute set from
        scratch: point it at any existing Function-style qualifier in a
        template file (e.g. the one holding the root diagram) and clone
        it. See RAMUS_RSF_FORMAT.md, 'Building a new diagram from a
        template'."""
        if self.t_qualifiers is None or self.t_qual_attrs is None:
            raise RuntimeError("В этом файле отсутствует data/qualifiers.xml или "
                                "data/qualifiers_attributes.xml")
        src = self.qualifiers.get(source_qualifier_id)
        if src is None:
            raise KeyError("Нет такого квалификатора: %s" % source_qualifier_id)

        new_qid = self.new_qualifier_id()
        self.t_qualifiers.rows.append({
            "QUALIFIER_ID": new_qid,
            "QUALIFIER_NAME": new_name,
            "QUALIFIER_SYSTEM": system,
            "ATTRIBUTE_FOR_NAME": src.get("ATTRIBUTE_FOR_NAME"),
        })
        self.qualifiers[new_qid] = self.t_qualifiers.rows[-1]

        for r in self.t_qual_attrs.find_rows(QUALIFIER_ID=source_qualifier_id):
            self.t_qual_attrs.rows.append({
                "QUALIFIER_ID": new_qid,
                "ATTRIBUTE_ID": r.get("ATTRIBUTE_ID"),
                "ATTRIBUTE_SYSTEM": r.get("ATTRIBUTE_SYSTEM"),
                "ATTRIBUTE_POSITION": r.get("ATTRIBUTE_POSITION"),
            })
        self.qualifier_attribute_ids[new_qid] = list(
            self.qualifier_attribute_ids.get(source_qualifier_id, []))
        self.elements_by_qualifier.setdefault(new_qid, [])
        return new_qid

    def add_function_box(self, qualifier_id: int, name: str,
                          x: float, y: float, width: float, height: float,
                          background: int = -16711936, foreground: int = -16777216,
                          font_name: str = "Dialog", font_style: int = 0, font_size: int = 12,
                          function_type: int = 3, status_type: int = 0) -> int:
        """Convenience one-shot: add_element + set_name + set_bounds +
        set_background/foreground + set_font + set_status + F_TYPE, in one
        call, using the same defaults Ramus itself uses for a freshly
        drawn function box (green fill, black border/text, 'Dialog' font,
        status 0 = 'Not started'/normal). `qualifier_id` must already
        carry the standard F_* attribute set (true for any qualifier
        created via clone_qualifier_as_container(), or any pre-existing
        Function qualifier)."""
        eid = self.add_element(qualifier_id, name=name)
        self.set_name(eid, name)
        self.set_bounds(eid, x, y, width, height)
        self.set_background(eid, background)
        self.set_foreground(eid, foreground)
        self.set_font(eid, font_name, font_style, font_size)
        self.set_status(eid, status_type)
        aid = self.find_attribute(qualifier_id, "F_TYPE")
        if aid is not None:
            self.set_value(eid, aid, function_type)
        return eid

    def register_model_root(self, base_functions_element_id: int, root_qualifier_id: int) -> None:
        """UNVERIFIED AGAINST A RUNNING RAMUS -- see RAMUS_RSF_FORMAT.md,
        'Decomposition hierarchy (partially understood)'.

        F_BASE_FUNCTION_QUALIFIER_ID is only ever attached to the system
        qualifier F_BASE_FUNCTIONS (found via find_base_functions_qualifier()),
        and only its elements carry it -- this is confirmed from a real
        file (element 3 -> qualifier 9 in the bundled 'Enterprise
        activity.rsf' sample). It records which qualifier is the *root
        diagram* of a whole model (what shows up as a top-level entry in
        Ramus's project navigator).

        It is NOT how an ordinary function box is linked to its own
        decomposition (child) diagram -- that turned out to be resolved
        through more involved GUI-side logic (IDEF0Plugin.isFunction /
        findElementForBaseFunction, F_OUNER_ID, and per-qualifier
        bookkeeping) that static analysis alone did not fully pin down.
        Use this only to register a new top-level model root; do not use
        it to wire up a box's decomposition page."""
        qid = self.element_qualifier(base_functions_element_id)
        aid = self.find_attribute(qid, "F_BASE_FUNCTION_QUALIFIER_ID")
        if aid is None:
            raise KeyError("Элемент %s не относится к квалификатору "
                            "F_BASE_FUNCTIONS (или у этого квалификатора нет "
                            "F_BASE_FUNCTION_QUALIFIER_ID)" % base_functions_element_id)
        self.set_value(base_functions_element_id, aid, root_qualifier_id)

    def find_base_functions_qualifier(self) -> Optional[int]:
        return self.find_qualifier("F_BASE_FUNCTIONS")

    # -- generic list-attribute helpers ---------------------------------
    # TYPE_MAP's 'list' mode (Core.OtherElement, Core.Hierarchical, ...)
    # has no single "set" -- rows are appended/removed directly. These
    # two cover the common shapes generically (any qualifier/attribute,
    # not just arrows) rather than requiring callers to poke at
    # model.table(path) by hand for every one-to-many link.

    def add_other_element_link(self, element_id: int, attribute_id: int,
                                other_element_id: int) -> None:
        """Append one row to a Core.OtherElement-typed (list-mode)
        attribute -- e.g. linking a sector to its owning stream. Does not
        check for an existing identical row; call multiple times to add
        multiple links."""
        atype = self.attribute_type(attribute_id)
        if atype != ("Core", "OtherElement"):
            raise TypeError("Атрибут %s не является Core.OtherElement (получено %r)"
                             % (attribute_id, atype))
        info = TYPE_MAP[atype]
        t = self._get_or_create_vtable(info.table_path, atype)
        t.rows.append({"ATTRIBUTE_ID": attribute_id, "ELEMENT_ID": element_id,
                        "OTHER_ELEMENT": other_element_id})

    def add_hierarchical_link(self, element_id: int, attribute_id: int, *,
                               parent_element_id: int = -1,
                               previous_element_id: Optional[int] = None,
                               icon_id: int = -1) -> None:
        """Append one row to a Core.Hierarchical-typed (list-mode)
        attribute, used for the tree/order bookkeeping every browsable
        qualifier's element list carries (RAMUS_RSF_FORMAT.md section 6).
        `previous_element_id=None` (the default) auto-fills it with
        whichever element was most recently added under `element_id`'s
        own qualifier (or -1, "no previous sibling", if it's the first),
        matching the ordering real Ramus files use.

        Note this attribute id is commonly *shared* across many
        qualifiers (every real sample file reuses one global
        "HierarchicalAttribute" id everywhere) -- its physical table has
        no qualifier column, so auto-fill deliberately scopes the search
        to `element_id`'s qualifier's own elements rather than the whole
        table, or it could pick a same-attribute row that happens to
        belong to a completely unrelated qualifier."""
        atype = self.attribute_type(attribute_id)
        if atype != ("Core", "Hierarchical"):
            raise TypeError("Атрибут %s не является Core.Hierarchical (получено %r)"
                             % (attribute_id, atype))
        if previous_element_id is None:
            qid = self.element_qualifier(element_id)
            previous_element_id = self._last_hierarchical_sibling(attribute_id, qid)
        info = TYPE_MAP[atype]
        t = self._get_or_create_vtable(info.table_path, atype)
        t.rows.append({"ATTRIBUTE_ID": attribute_id, "ELEMENT_ID": element_id,
                        "ICON_ID": icon_id, "PARENT_ELEMENT_ID": parent_element_id,
                        "PREVIOUS_ELEMENT_ID": previous_element_id})

    def _last_hierarchical_sibling(self, attribute_id: int, qualifier_id: Optional[int]) -> int:
        info = TYPE_MAP[("Core", "Hierarchical")]
        t = self._vtable_or_none(info.table_path)
        if t is None:
            return -1
        siblings = set(self.elements_by_qualifier.get(qualifier_id, []))
        rows = [r for r in t.find_rows(ATTRIBUTE_ID=attribute_id, PARENT_ELEMENT_ID=-1)
                if r.get("ELEMENT_ID") in siblings]
        if not rows:
            return -1
        # The tail of the sibling chain is whichever top-level row's
        # ELEMENT_ID nothing else references as *its* PREVIOUS_ELEMENT_ID.
        referenced_as_previous = {r.get("PREVIOUS_ELEMENT_ID") for r in rows}
        tails = [r["ELEMENT_ID"] for r in rows
                 if r["ELEMENT_ID"] not in referenced_as_previous]
        return tails[-1] if tails else rows[-1]["ELEMENT_ID"]

    # -- IDEF0 arrows (sectors / streams / crosspoints) -------------------
    # See the "IDEF0 arrows" section further down this file for the
    # verified data model this implements, and RAMUS_RSF_FORMAT.md
    # section 10 for the write-up.

    def find_sector_qualifier(self) -> Optional[int]:
        return self.find_qualifier("F_SECTORS")

    def find_stream_qualifier(self) -> Optional[int]:
        return self.find_qualifier("F_STREAMS")

    def new_crosspoint_id(self) -> int:
        """A fresh crosspoint id guaranteed not to collide with any
        already used in this file.

        Unlike element/qualifier/attribute ids (RAMUS_RSF_FORMAT.md
        section 7), Ramus's own crosspoint id source is a plain SQL
        sequence with **no** resync-from-existing-data safety net --
        confirmed from source: `NDataPlugin.createCrosspoint()` calls
        `IDEF0Plugin.getNextCrosspointId()` -> `engine.nextValue(
        "crosspoint_sequence")` directly, unlike `IEngineImpl.
        createElement()` et al., which loop against `MAX(id)` before
        accepting a sequence value. Consequently the `crosspoint_sequence`
        entry persisted in a file's `data/sequences.xml` cannot be
        trusted on its own -- in the bundled real sample file it's `31`
        while actual `CROSSPOINT` values already in use run past `54000`
        (almost certainly stale from a pre-migration counter reset; see
        RAMUS_RSF_FORMAT.md section 12 on this file format's history of
        migrations). This method sidesteps the whole question the same
        way `new_element_id()` etc. do: derive a safe value directly
        from `MAX(CROSSPOINT already in this file's own border data)`."""
        info = TYPE_MAP[("IDEF0", "SectorBorder")]
        t = self._vtable_or_none(info.table_path)
        if t is None:
            return 1
        return t.max_int("CROSSPOINT") + 1

    def ensure_arrow_support(self) -> Tuple[int, int]:
        """Make sure this file has the F_SECTORS/F_STREAMS system
        qualifiers and their standard attribute set that arrows need,
        creating them if this file doesn't have them yet (e.g. one
        started from `template.new_model()`). Every real Ramus file
        already has these (confirmed against all three bundled samples),
        so on a real file this is a no-op that just looks them up.
        Returns (sector_qualifier_id, stream_qualifier_id)."""
        sect_qid = self.find_sector_qualifier()
        stream_qid = self.find_stream_qualifier()
        if sect_qid is not None and stream_qid is not None:
            return sect_qid, stream_qid

        if self.t_qualifiers is None or self.t_attributes is None or \
                self.t_qual_attrs is None:
            raise RuntimeError("В этом файле отсутствует один из файлов data/qualifiers.xml, "
                                "data/attributes.xml, data/qualifiers_attributes.xml")

        def _get_or_add_attribute(name: str, plugin: str, type_name: str) -> int:
            existing = self.attribute_id_by_name.get(name)
            if existing:
                return existing[0]
            aid = self.new_attribute_id()
            self.t_attributes.rows.append({
                "ATTRIBUTE_ID": aid, "ATTRIBUTE_NAME": name,
                "ATTRIBUTE_TYPE_PLUGIN_NAME": plugin, "ATTRIBUTE_TYPE_NAME": type_name,
                "ATTRIBUTE_TYPE_COMPARABLE": False, "ATTRIBUTE_SYSTEM": True,
            })
            self.attributes[aid] = self.t_attributes.rows[-1]
            self.attribute_id_by_name.setdefault(name, []).append(aid)
            return aid

        def _attach(qid: int, aid: int, pos: int) -> None:
            self.t_qual_attrs.rows.append({
                "QUALIFIER_ID": qid, "ATTRIBUTE_ID": aid,
                "ATTRIBUTE_SYSTEM": True, "ATTRIBUTE_POSITION": pos,
            })
            self.qualifier_attribute_ids.setdefault(qid, []).append(aid)

        hierarchical_aid = _get_or_add_attribute("HierarchicalAttribute", "Core", "Hierarchical")

        if sect_qid is None:
            sect_qid = self.new_qualifier_id()
            self.t_qualifiers.rows.append({
                "QUALIFIER_ID": sect_qid, "QUALIFIER_NAME": "F_SECTORS",
                "QUALIFIER_SYSTEM": True, "ATTRIBUTE_FOR_NAME": -1,
            })
            self.qualifiers[sect_qid] = self.t_qualifiers.rows[-1]
            self.elements_by_qualifier.setdefault(sect_qid, [])
            aid_sector = _get_or_add_attribute("F_SECTOR_ATTRIBUTE", "IDEF0", "Sector")
            aid_border_start = _get_or_add_attribute("F_SECTOR_BORDER_START", "IDEF0", "SectorBorder")
            aid_border_end = _get_or_add_attribute("F_SECTOR_BORDER_END", "IDEF0", "SectorBorder")
            aid_func_sector = _get_or_add_attribute("F_FUNCTION_SECTOR", "Core", "OtherElement")
            aid_sector_stream = _get_or_add_attribute("F_SECTOR_STREAM", "Core", "OtherElement")
            for pos, aid in enumerate((aid_sector_stream, hierarchical_aid, aid_sector,
                                        aid_border_start, aid_border_end, aid_func_sector)):
                _attach(sect_qid, aid, pos)

        if stream_qid is None:
            aid_stream_name = _get_or_add_attribute("F_STREAM_NAME", "Core", "Text")
            stream_qid = self.new_qualifier_id()
            self.t_qualifiers.rows.append({
                "QUALIFIER_ID": stream_qid, "QUALIFIER_NAME": "F_STREAMS",
                "QUALIFIER_SYSTEM": True, "ATTRIBUTE_FOR_NAME": aid_stream_name,
            })
            self.qualifiers[stream_qid] = self.t_qualifiers.rows[-1]
            self.elements_by_qualifier.setdefault(stream_qid, [])
            aid_stream_added = _get_or_add_attribute("F_STREAM_ADDED", "IDEF0", "AnyToAny")
            for pos, aid in enumerate((aid_stream_added, hierarchical_aid, aid_stream_name)):
                _attach(stream_qid, aid, pos)

        return sect_qid, stream_qid

    def _new_sector(self, stream_eid: int, sect_qid: int,
                     start: Dict[str, Any], end: Dict[str, Any]) -> int:
        aid_sector = self.find_attribute(sect_qid, "F_SECTOR_ATTRIBUTE")
        aid_border_start = self.find_attribute(sect_qid, "F_SECTOR_BORDER_START")
        aid_border_end = self.find_attribute(sect_qid, "F_SECTOR_BORDER_END")
        aid_sector_stream = self.find_attribute(sect_qid, "F_SECTOR_STREAM")
        aid_hierarchical = self.find_attribute(sect_qid, "HierarchicalAttribute")

        sector_eid = self.add_element(sect_qid, name="")
        # Matches every simple (non-bent, non-manually-repositioned) real
        # sector's IDEF0.Sector row exactly (RAMUS_RSF_FORMAT.md section 10):
        # unlabeled, "not yet text-positioned" (CREATE_POS -1.0), and using
        # a real Ramus-drawn arrow's exact default look (see
        # _DEFAULT_SECTOR_VISUAL_ATTRIBUTES).
        self.set_value(sector_eid, aid_sector, {
            "ALTERNATIVE_TEXT": "", "CREATE_POS": -1.0, "CREATE_STATE": 0,
            "SHOW_TEXT": 1, "VISUAL_ATTRIBUTES": _DEFAULT_SECTOR_VISUAL_ATTRIBUTES,
        })
        self.set_value(sector_eid, aid_border_start, start)
        self.set_value(sector_eid, aid_border_end, end)
        if aid_sector_stream is not None:
            self.add_other_element_link(sector_eid, aid_sector_stream, stream_eid)
        if aid_hierarchical is not None:
            self.add_hierarchical_link(sector_eid, aid_hierarchical)
        return sector_eid

    def _new_stream(self, stream_qid: int, name: str) -> int:
        aid_name = self.find_attribute(stream_qid, "F_STREAM_NAME")
        aid_hierarchical = self.find_attribute(stream_qid, "HierarchicalAttribute")
        stream_eid = self.add_element(stream_qid, name="")
        if aid_name is not None:
            self.set_value(stream_eid, aid_name, name)
        if aid_hierarchical is not None:
            self.add_hierarchical_link(stream_eid, aid_hierarchical)
        return stream_eid

    def _border(self, *, border_type: int = -1, crosspoint: int = -1,
                function: int = -1, function_type: int = -1,
                tunnel: int = TunnelType.HARD) -> Dict[str, Any]:
        return {"BORDER_TYPE": border_type, "CROSSPOINT": crosspoint,
                "FUNCTION": function, "FUNCTION_TYPE": function_type,
                "TUNNEL_SOFT": tunnel}

    def add_arrow(self, from_element_id: int, from_side: int,
                  to_element_id: int, to_side: int, *,
                  name: str = "", tunnel: bool = False) -> int:
        """Create a new, straight IDEF0 arrow directly connecting two
        function boxes' edges (one Sector, both borders TYPE_FUNCTION) --
        the common case, matching 283 of the 288 arrows in the bundled
        'Enterprise activity.rsf' sample byte-for-byte in shape. Both
        boxes must be on the same diagram (same qualifier); this does not
        check that, since nothing in the format itself requires it, but
        Ramus's own GUI never draws one otherwise.

        `from_side`/`to_side` are `ArrowSide` values (which edge of each
        box the arrow touches -- LEFT=Input, TOP=Control, RIGHT=Output,
        BOTTOM=Mechanism in standard IDEF0 usage). `tunnel=True` marks
        both ends with a soft tunnel (the "(" ")" bracket marks meaning
        "not shown at the parent/child level").

        Geometry note: like every other unmodified real arrow in the
        sample files, this deliberately stores *no* explicit path
        (no SectorPoint rows) -- Ramus computes a straight-line/default
        route between the two box edges at paint time. Only an arrow a
        user has manually dragged/bent in the real GUI ends up with
        stored ordinates; this function reproduces the *unmodified,
        auto-routed* state, which is what every arrow starts as.

        Returns the id of the new Stream element (the arrow's own
        identity -- rename it via set_value(stream_id,
        find_attribute(stream_qualifier_id, "F_STREAM_NAME"), ...) or
        just pass `name` here)."""
        sect_qid, stream_qid = self.ensure_arrow_support()
        tt = TunnelType.SOFT if tunnel else TunnelType.HARD
        stream_eid = self._new_stream(stream_qid, name)
        # Two fresh crosspoints, one per border -- new_crosspoint_id()
        # derives from what's already committed to the file, so the
        # second call here would return the *same* id as the first
        # (nothing's been written yet); allocate the pair explicitly
        # instead of calling it twice.
        cp_from = self.new_crosspoint_id()
        cp_to = cp_from + 1
        start = self._border(function=from_element_id, function_type=from_side,
                              crosspoint=cp_from, tunnel=tt)
        end = self._border(function=to_element_id, function_type=to_side,
                            crosspoint=cp_to, tunnel=tt)
        self._new_sector(stream_eid, sect_qid, start, end)
        return stream_eid

    def add_boundary_arrow(self, element_id: int, box_side: int, page_side: int, *,
                            direction: str = "in", name: str = "",
                            tunnel: bool = False) -> int:
        """Create a new IDEF0 boundary arrow: one Sector connecting a
        function box's edge to the diagram page's own edge -- an
        Input/Control/Output/Mechanism arrow entering or leaving the
        diagram from outside it. Matches real boundary-arrow sectors in
        the bundled sample byte-for-byte in shape (e.g. sectors 116/118/
        120/124 in 'Enterprise activity.rsf').

        `box_side` is where it touches the box (`ArrowSide`); `page_side`
        is which edge of the page it touches (also an `ArrowSide` value --
        the same RIGHT/BOTTOM/LEFT/TOP encoding is reused for the page
        border, confirmed against real data). `direction="in"` (default)
        draws it flowing from the page boundary into the box (typical for
        Input/Control/Mechanism); `direction="out"` flows from the box out
        to the boundary (typical for Output).

        Returns the new Stream element id, as add_arrow() does."""
        if direction not in ("in", "out"):
            raise ValueError("direction должно быть 'in' или 'out'")
        sect_qid, stream_qid = self.ensure_arrow_support()
        tt = TunnelType.SOFT if tunnel else TunnelType.HARD
        stream_eid = self._new_stream(stream_qid, name)
        cp_boundary = self.new_crosspoint_id()
        cp_box = cp_boundary + 1
        boundary = self._border(border_type=page_side, crosspoint=cp_boundary, tunnel=tt)
        box = self._border(function=element_id, function_type=box_side,
                            crosspoint=cp_box, tunnel=tt)
        if direction == "in":
            self._new_sector(stream_eid, sect_qid, boundary, box)
        else:
            self._new_sector(stream_eid, sect_qid, box, boundary)
        return stream_eid


# --------------------------------------------------------------------------
# Color helpers
#
# IDEF0.Color values are stored as java.awt.Color.getRGB(): a packed
# 0xAARRGGBB int, reinterpreted as a *signed* 32-bit Java int (so anything
# with the alpha/red high bit set comes out negative). Pure opaque green
# (0xFF00FF00) is -16711936, which is exactly what Ramus uses as the
# default function-box fill -- see the bundled sample files.
# --------------------------------------------------------------------------

def argb(r: int, g: int, b: int, a: int = 255) -> int:
    """r,g,b,a in 0..255 -> the signed 32-bit int IDEF0.Color expects."""
    v = ((a & 0xFF) << 24) | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
    return v - 0x100000000 if v >= 0x80000000 else v


def unpack_argb(value: int) -> Tuple[int, int, int, int]:
    """Inverse of argb(): signed 32-bit int -> (r, g, b, a)."""
    v = value & 0xFFFFFFFF
    a = (v >> 24) & 0xFF
    r = (v >> 16) & 0xFF
    g = (v >> 8) & 0xFF
    b = v & 0xFF
    return (r, g, b, a)




# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

_SCALAR_SQL_TYPE_GUESS = {
    "VALUE_TEXT": "CLOB",
}


def _guess_sql_types(cols: List[str]) -> Dict[str, str]:
    """Best-effort SQL type for a freshly-created value table (only used
    when this file has never used that attribute type before, so there's
    no existing table to copy the schema from)."""
    out = {}
    for c in cols:
        cu = c.upper()
        if cu in ("ATTRIBUTE_ID", "ELEMENT_ID"):
            out[c] = "BIGINT"
        elif cu in ("X", "Y", "WIDTH", "HEIGHT", "CREATE_POS", "TILDA_POS",
                    "TEXT_X", "TEXT_Y", "TEXT_WIDTH", "TEXT_HIEGHT",
                    "X_POSITION", "Y_POSITION"):
            out[c] = "DOUBLE"
        elif cu in ("COLOR", "STYLE", "SIZE", "TYPE", "SHOW_TEXT", "SHOW_TILDA",
                    "TRANSPARENT", "CREATE_STATE", "BORDER_TYPE", "FUNCTION_TYPE",
                    "TUNNEL_SOFT", "TEXT_ALIGMENT", "POINT_TYPE", "POSITION",
                    "AUTOCHANGE"):
            out[c] = "INTEGER"
        elif cu in ("OTHER_ELEMENT", "OUNER_ID", "FUNCTION", "CROSSPOINT",
                    "VARIANT_ID", "ICON_ID", "PARENT_ELEMENT_ID",
                    "PREVIOUS_ELEMENT_ID", "X_ORDINATE_ID", "Y_ORDINATE_ID",
                    "QUALIFIER_ATTRIBUTE_ID", "QUALIFIER_TABLE_ATTRIBUTE_ID"):
            out[c] = "BIGINT"
        elif cu in ("ICON", "VISUAL_ATTRIBUTES", "DATA"):
            out[c] = "VARBINARY"
        elif cu in ("CHANGE_DATE", "CREATE_DATE", "LAST_MODIFIED_TIME", "UPLOAD_TIME"):
            out[c] = "TIMESTAMP"
        else:
            out[c] = "CLOB"
    return out


# --------------------------------------------------------------------------
# JSON-friendly full dump
# --------------------------------------------------------------------------

def dump_model(model: Model, include_system_qualifiers: bool = True) -> Dict[str, Any]:
    """A complete, JSON-serialisable snapshot of the model: every
    qualifier, every element under it, and every resolved attribute value.
    Intended for feeding to an AI / for human inspection, not as an
    edit-and-save-back format (round-trip editing should go through the
    Model API so IDs / row bookkeeping stay consistent)."""
    out: Dict[str, Any] = {"qualifiers": []}
    for qid, q in sorted(model.qualifiers.items()):
        if not include_system_qualifiers and q.get("QUALIFIER_SYSTEM"):
            continue
        q_out = {
            "id": qid,
            "name": q.get("QUALIFIER_NAME"),
            "system": q.get("QUALIFIER_SYSTEM"),
            "elements": [],
        }
        for eid in model.elements_by_qualifier.get(qid, []):
            e = model.elements[eid]
            q_out["elements"].append({
                "id": eid,
                "name": e.get("ELEMENT_NAME"),
                "attributes": _json_safe(model.element_attributes(eid)),
            })
        out["qualifiers"].append(q_out)
    return out


def _json_safe(d: Any) -> Any:
    if isinstance(d, dict):
        return {k: _json_safe(v) for k, v in d.items()}
    if isinstance(d, list):
        return [_json_safe(v) for v in d]
    if isinstance(d, bytes):
        return {"__bytes_len__": len(d)}
    return d


# --------------------------------------------------------------------------
# Re-importing a (possibly hand-edited/redacted) JSON dump
#
# dump_model() is explicitly documented as "not an edit-and-save-back
# format" -- this is the deliberately narrow exception: a *patch*
# operation intended for the "export JSON, redact/edit text values,
# re-import" workflow (and the GUI's JSON Dump tab), not a general
# import/replace. See apply_json_dump()'s docstring for exactly what it
# will and won't touch.
# --------------------------------------------------------------------------

@dataclass
class ImportResult:
    qualifiers_updated: int = 0
    elements_updated: int = 0
    values_updated: int = 0
    warnings: List[str] = _dataclass_field(default_factory=list)

    def summary(self) -> str:
        return ("Обновлено имён квалификаторов: %d, элементов: %d (всего значений: %d); "
                "предупреждений: %d." % (self.qualifiers_updated, self.elements_updated,
                                     self.values_updated, len(self.warnings)))


def apply_json_dump(model: Model, data: Dict[str, Any]) -> ImportResult:
    """Apply a dump_model()-shaped JSON structure back onto `model` as a
    patch, not a replace:

    - Qualifiers and elements in `data` are matched against this file by
      id. An id that isn't found here is skipped and reported in
      `ImportResult.warnings` -- nothing is ever added.
    - Conversely, a qualifier/element that exists in `model` but is
      simply absent from `data` (e.g. it was dumped with
      include_system_qualifiers=False, or its whole block was deleted
      while redacting) is left completely alone -- nothing is ever
      removed. This function only patches values of things present in
      *both*.
    - Only scalar and struct attribute values (and each element's/
      qualifier's plain "name") are written back, and only where the new
      value actually differs from the current one -- matching what
      dump_model() actually captures. List-valued attributes and the
      `{"__bytes_len__": n}` placeholders dump_model() emits in place of
      real bytes (stream/blob-valued attributes) are left untouched and
      reported as warnings; edit those via the Raw Tables view instead
      (RAMUS_RSF_FORMAT.md sections 10-11).

    A no-op re-import (JSON unchanged from what was just exported)
    reports zero updates.
    """
    result = ImportResult()
    for q in data.get("qualifiers", []):
        qid = q.get("id")
        if qid not in model.qualifiers:
            result.warnings.append("Квалификатор %r не найден в этом файле; пропущен." % (qid,))
            continue
        new_qname = q.get("name")
        if isinstance(new_qname, str) and new_qname != model.qualifiers[qid].get("QUALIFIER_NAME"):
            model.qualifiers[qid]["QUALIFIER_NAME"] = new_qname
            result.qualifiers_updated += 1
        for e in q.get("elements", []):
            eid = e.get("id")
            if eid not in model.elements:
                result.warnings.append("Элемент %r (квалификатор %r) не найден; пропущен." % (eid, qid))
                continue
            if model.elements[eid].get("QUALIFIER_ID") != qid:
                result.warnings.append(
                    "Элемент %r больше не относится к квалификатору %r; пропущен." % (eid, qid))
                continue
            if _apply_element_dump(model, qid, eid, e, result):
                result.elements_updated += 1
    return result


def _resolve_attribute_key(model: Model, qid: int, key: str) -> Optional[int]:
    """Reverse of the key dump_model()/element_attributes() used: the
    attribute's own name, or 'attr_<id>' when it had none/a name clash."""
    if key.startswith("attr_") and key[5:].isdigit():
        aid = int(key[5:])
        if aid in model.qualifier_attribute_ids.get(qid, []):
            return aid
        return None
    return model.find_attribute(qid, key)


def _apply_element_dump(model: Model, qid: int, eid: int, e: Dict[str, Any],
                         result: ImportResult) -> bool:
    changed = False
    attrs = e.get("attributes") or {}
    name_attr_id = model.find_attribute(qid, "Name")

    for key, new_value in attrs.items():
        aid = _resolve_attribute_key(model, qid, key)
        if aid is None:
            result.warnings.append(
                "Атрибут %r не найден у квалификатора %r (элемент %r); пропущен." % (key, qid, eid))
            continue
        atype = model.attribute_type(aid)
        info = TYPE_MAP.get(atype)
        if info is None:
            result.warnings.append(
                "Нет известного редактора для атрибута %r (элемент %r); пропущен." % (key, eid))
            continue

        if info.mode == "list":
            result.warnings.append(
                "Атрибут %r имеет тип-список; редактируйте его через вкладку "
                "«Сырые таблицы» (элемент %r)." % (key, eid))
            continue
        if info.mode == "stream":
            result.warnings.append(
                "Атрибут %r хранится как файл/поток; JSON-дамп не содержит "
                "его байты, поэтому он не может быть повторно импортирован (элемент %r)." % (key, eid))
            continue

        if info.mode == "scalar":
            if isinstance(new_value, dict) and "__bytes_len__" in new_value:
                continue  # placeholder for a bytes value the dump can't round-trip
            current = model.get_value(eid, aid)
            if current == new_value:
                continue
            if aid == name_attr_id:
                model.set_name(eid, new_value)
            else:
                try:
                    model.set_value(eid, aid, new_value)
                except (TypeError, ValueError) as ex:
                    result.warnings.append(
                        "Не удалось установить %r у элемента %r: %s" % (key, eid, ex))
                    continue
            result.values_updated += 1
            changed = True

        elif info.mode == "struct":
            if not isinstance(new_value, dict):
                result.warnings.append(
                    "Атрибут %r ожидает объект, получено %s (элемент %r); пропущен."
                    % (key, type(new_value).__name__, eid))
                continue
            current = model.get_value(eid, aid) or {}
            patch = {}
            for col, v in new_value.items():
                if isinstance(v, dict) and "__bytes_len__" in v:
                    continue  # bytes column placeholder, not round-trippable
                cu = col.upper()
                if current.get(cu) != v:
                    patch[cu] = v
            if not patch:
                continue
            try:
                model.set_value(eid, aid, patch)
            except (TypeError, ValueError) as ex:
                result.warnings.append("Не удалось установить %r у элемента %r: %s" % (key, eid, ex))
                continue
            result.values_updated += len(patch)
            changed = True

    # Element display name: dump_model() writes this separately from the
    # "Name" attribute (elements.ELEMENT_NAME vs. the Core.Text value) --
    # they're normally mirrored (see Model.set_name), so only apply this
    # when the "Name" attribute wasn't already processed above.
    new_name = e.get("name")
    if isinstance(new_name, str) and "Name" not in attrs and "name" not in attrs:
        if new_name != model.elements[eid].get("ELEMENT_NAME"):
            if name_attr_id is not None:
                model.set_name(eid, new_name)
            else:
                model.set_element_name(eid, new_name)
            changed = True

    return changed
