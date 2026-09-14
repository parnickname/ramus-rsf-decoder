"""
template.py -- build a brand-new, minimal-but-valid .rsf archive from
scratch (no template file needed).

This bootstraps just enough of the self-describing EAV schema (see
RAMUS_RSF_FORMAT.md) for a single IDEF0 root diagram: the core
qualifiers/elements/attributes/qualifiers_attributes tables, the standard
F_* function-box attribute set (checkIDEF0Attributes(), RAMUS_RSF_FORMAT.md
section 8), and one F_BASE_FUNCTIONS bookkeeping element pointing at it
(section 9) so the new diagram shows up as a top-level model.

This exact construction is exercised by the test suite (round-tripped,
edited, reloaded) but -- like the rest of the "new diagram" support
inherited from the provided toolkit -- has not been confirmed against a
real Ramus GUI. It follows the same "only pre-2.0 table shapes, no branch
bookkeeping" minimal style the toolkit uses elsewhere (RAMUS_RSF_FORMAT.md
section 12), which real Ramus (2.0.x) loads correctly.
"""

from __future__ import annotations

from .rsf_core import RsfArchive, Table, Field
from .rsf_model import Model

# Fixed attribute ids for the standard function-box attribute set this
# module bootstraps. Kept as constants so callers (and tests) can refer to
# them by name via Model.find_attribute(...) instead -- these numbers are
# just where the sequence starts in a freshly generated file.
_ATTR_NAME = 1
_ATTR_DESCRIPTION = 2
_ATTR_F_BOUNDS = 3
_ATTR_F_BACKGROUND = 4
_ATTR_F_FOREGROUND = 5
_ATTR_F_FONT = 6
_ATTR_F_STATUS = 7
_ATTR_F_TYPE = 8
_ATTR_F_BASE_FUNCTION_QUALIFIER_ID = 9

_QUAL_F_BASE_FUNCTIONS = 1
_QUAL_ROOT_DIAGRAM = 2


def _table(name_no_ext: str, cols_types) -> Table:
    fields = [Field(id=i, name=n, type=t) for i, (n, t) in enumerate(cols_types)]
    return Table(source_table=name_no_ext, prefix="ramus_", fields=fields, rows=[])


def new_model(root_diagram_name: str = "Корневая диаграмма") -> Model:
    """Build an empty Model with one root IDEF0 diagram qualifier, ready
    for add_function_box() calls. Equivalent in spirit to Ramus's
    File > New, minus anything not needed to produce a file real Ramus
    can open (see module docstring)."""
    arc = RsfArchive()

    t_qualifiers = _table("qualifiers", [
        ("QUALIFIER_ID", "BIGINT"), ("QUALIFIER_NAME", "CLOB"),
        ("QUALIFIER_SYSTEM", "BOOLEAN"), ("ATTRIBUTE_FOR_NAME", "BIGINT"),
    ])
    t_elements = _table("elements", [
        ("ELEMENT_ID", "BIGINT"), ("ELEMENT_NAME", "CLOB"), ("QUALIFIER_ID", "BIGINT"),
    ])
    t_attributes = _table("attributes", [
        ("ATTRIBUTE_ID", "BIGINT"), ("ATTRIBUTE_NAME", "CLOB"),
        ("ATTRIBUTE_TYPE_PLUGIN_NAME", "CLOB"), ("ATTRIBUTE_TYPE_NAME", "CLOB"),
        ("ATTRIBUTE_TYPE_COMPARABLE", "BOOLEAN"), ("ATTRIBUTE_SYSTEM", "BOOLEAN"),
    ])
    t_qual_attrs = _table("qualifiers_attributes", [
        ("QUALIFIER_ID", "BIGINT"), ("ATTRIBUTE_ID", "BIGINT"),
        ("ATTRIBUTE_SYSTEM", "BOOLEAN"), ("ATTRIBUTE_POSITION", "INTEGER"),
    ])

    t_qualifiers.rows = [
        {"QUALIFIER_ID": _QUAL_F_BASE_FUNCTIONS, "QUALIFIER_NAME": "F_BASE_FUNCTIONS",
         "QUALIFIER_SYSTEM": True, "ATTRIBUTE_FOR_NAME": _ATTR_NAME},
        {"QUALIFIER_ID": _QUAL_ROOT_DIAGRAM, "QUALIFIER_NAME": root_diagram_name,
         "QUALIFIER_SYSTEM": False, "ATTRIBUTE_FOR_NAME": _ATTR_NAME},
    ]

    attrs = [
        (_ATTR_NAME, "Name", "Core", "Text"),
        (_ATTR_DESCRIPTION, "Description", "Core", "HTMLText"),
        (_ATTR_F_BOUNDS, "F_BOUNDS", "IDEF0", "FRectangle"),
        (_ATTR_F_BACKGROUND, "F_BACKGROUND", "IDEF0", "Color"),
        (_ATTR_F_FOREGROUND, "F_FOREGROUND", "IDEF0", "Color"),
        (_ATTR_F_FONT, "F_FONT", "IDEF0", "Font"),
        (_ATTR_F_STATUS, "F_STATUS", "IDEF0", "Status"),
        (_ATTR_F_TYPE, "F_TYPE", "IDEF0", "Type"),
        (_ATTR_F_BASE_FUNCTION_QUALIFIER_ID, "F_BASE_FUNCTION_QUALIFIER_ID", "Core", "Long"),
    ]
    t_attributes.rows = [
        {"ATTRIBUTE_ID": aid, "ATTRIBUTE_NAME": name,
         "ATTRIBUTE_TYPE_PLUGIN_NAME": plugin, "ATTRIBUTE_TYPE_NAME": typ,
         "ATTRIBUTE_TYPE_COMPARABLE": False, "ATTRIBUTE_SYSTEM": False}
        for (aid, name, plugin, typ) in attrs
    ]

    root_attr_ids = [_ATTR_NAME, _ATTR_DESCRIPTION, _ATTR_F_BOUNDS, _ATTR_F_BACKGROUND,
                      _ATTR_F_FOREGROUND, _ATTR_F_FONT, _ATTR_F_STATUS, _ATTR_F_TYPE]
    t_qual_attrs.rows = [
        {"QUALIFIER_ID": _QUAL_ROOT_DIAGRAM, "ATTRIBUTE_ID": aid,
         "ATTRIBUTE_SYSTEM": False, "ATTRIBUTE_POSITION": pos}
        for pos, aid in enumerate(root_attr_ids)
    ] + [
        {"QUALIFIER_ID": _QUAL_F_BASE_FUNCTIONS, "ATTRIBUTE_ID": _ATTR_F_BASE_FUNCTION_QUALIFIER_ID,
         "ATTRIBUTE_SYSTEM": True, "ATTRIBUTE_POSITION": 0},
    ]

    t_elements.rows = []

    arc.tables["data/qualifiers.xml"] = t_qualifiers
    arc.tables["data/elements.xml"] = t_elements
    arc.tables["data/attributes.xml"] = t_attributes
    arc.tables["data/qualifiers_attributes.xml"] = t_qual_attrs
    arc.order = ["data/qualifiers.xml", "data/elements.xml",
                 "data/attributes.xml", "data/qualifiers_attributes.xml"]
    arc.properties["data/application_metadata.xml"] = {
        "ApplicationName": "Ramus",
        "ApplicationVersion": "1.2",
        "FileOpenMinimumVersion": "1.0",
        "PluginCount": "2",
        "Plugin_0": "Core",
        "Plugin_1": "IDEF0",
    }
    arc.order.append("data/application_metadata.xml")

    model = Model(arc)

    # Register the root diagram as a top-level model, mirroring what a real
    # file's F_BASE_FUNCTIONS bookkeeping element looks like (section 9).
    bf_elem = model.add_element(_QUAL_F_BASE_FUNCTIONS, name="")
    model.register_model_root(bf_elem, _QUAL_ROOT_DIAGRAM)

    return model
