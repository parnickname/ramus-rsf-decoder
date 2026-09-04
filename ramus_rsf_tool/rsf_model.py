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
from dataclasses import dataclass
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
            raise KeyError("No such table in this file: %s" % path)
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
                    "This file has no %s table (the attribute type it "
                    "backs has never been used in this file)." % path)
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
            raise KeyError("Unknown attribute id %s" % attribute_id)
        info = TYPE_MAP.get(atype)
        if info is None:
            raise KeyError("No physical-table mapping known for attribute "
                            "type %s (attribute id %s). Use model.table(...) "
                            "to inspect it via the raw path if you know it."
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
            raise KeyError("Unknown attribute id %s" % attribute_id)
        info = TYPE_MAP.get(atype)
        if info is None:
            raise KeyError("No physical-table mapping known for attribute "
                            "type %s (attribute id %s)" % (atype, attribute_id))

        if info.mode == "stream":
            path = self._stream_path(element_id, attribute_id, atype, info)
            self._set_stream(path, value)
            return

        if info.mode == "list":
            raise ValueError("Attribute type %s is list-valued; use "
                              "model.table(%r) to add/remove rows directly."
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
                raise TypeError("struct-mode attribute expects a dict of "
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
            raise RuntimeError("This file has no data/elements.xml table")
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
            raise KeyError("No such element: %s" % element_id)
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
            raise KeyError("Qualifier %s has no F_BOUNDS attribute" % qid)
        self.set_value(element_id, aid, {"X": x, "Y": y, "WIDTH": width, "HEIGHT": height})

    def set_background(self, element_id: int, argb: int) -> None:
        self._set_named_color(element_id, "F_BACKGROUND", argb)

    def set_foreground(self, element_id: int, argb: int) -> None:
        self._set_named_color(element_id, "F_FOREGROUND", argb)

    def _set_named_color(self, element_id: int, attr_name: str, argb: int) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, attr_name)
        if aid is None:
            raise KeyError("Qualifier %s has no %s attribute" % (qid, attr_name))
        self.set_value(element_id, aid, argb)

    def set_font(self, element_id: int, name: str, style: int, size: int) -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "F_FONT")
        if aid is None:
            raise KeyError("Qualifier %s has no F_FONT attribute" % qid)
        self.set_value(element_id, aid, {"NAME": name, "STYLE": style, "SIZE": size})

    def set_status(self, element_id: int, status_type: int, other_name: str = "") -> None:
        qid = self.element_qualifier(element_id)
        aid = self.find_attribute(qid, "F_STATUS")
        if aid is None:
            raise KeyError("Qualifier %s has no F_STATUS attribute" % qid)
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
            raise RuntimeError("This file is missing data/qualifiers.xml or "
                                "data/qualifiers_attributes.xml")
        src = self.qualifiers.get(source_qualifier_id)
        if src is None:
            raise KeyError("No such qualifier: %s" % source_qualifier_id)

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
            raise KeyError("Element %s is not under the F_BASE_FUNCTIONS "
                            "qualifier (or that qualifier lacks "
                            "F_BASE_FUNCTION_QUALIFIER_ID)" % base_functions_element_id)
        self.set_value(base_functions_element_id, aid, root_qualifier_id)

    def find_base_functions_qualifier(self) -> Optional[int]:
        return self.find_qualifier("F_BASE_FUNCTIONS")


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
