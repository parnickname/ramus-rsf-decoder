#!/usr/bin/env python3
"""
rsf_cli.py -- command-line inspector for Ramus (.rsf) files.

Usage:
    ramus-rsf-cli dump FILE.rsf [--all] [--pretty]
        Dump the whole model (qualifiers -> elements -> attributes) as JSON.
        --all     include system qualifiers/attributes too (default: only
                   user-visible ones)
        --pretty  indent the JSON (default: compact)

    ramus-rsf-cli qualifiers FILE.rsf
        List every qualifier (id, name, system flag, element count).

    ramus-rsf-cli elements FILE.rsf QUALIFIER_ID
        List every element under one qualifier (id, name).

    ramus-rsf-cli show FILE.rsf ELEMENT_ID
        Show every resolved attribute of one element.

    ramus-rsf-cli tables FILE.rsf
        List every raw data table found in the file, with row counts.

    ramus-rsf-cli table FILE.rsf TABLE_PATH
        Dump one raw table (e.g. data/IDEF0/attribute_sectors.xml) as JSON.

    ramus-rsf-cli rename FILE.rsf ELEMENT_ID NEW_NAME OUT.rsf
        Rename one element's Name attribute and save to OUT.rsf.

    ramus-rsf-cli gui [FILE.rsf]
        Launch the graphical editor (equivalent to running ramus-rsf-gui).

This module can also be run directly: `python3 -m ramus_rsf_tool.rsf_cli ...`
"""
import json
import sys

from .rsf_model import Model, dump_model


def _json(obj, pretty=False):
    return json.dumps(obj, ensure_ascii=False, default=str,
                       indent=2 if pretty else None)


def cmd_dump(args):
    path = args.pop(0)
    include_system = "--all" in args
    pretty = "--pretty" in args
    m = Model.load(path)
    print(_json(dump_model(m, include_system_qualifiers=include_system), pretty))


def cmd_qualifiers(args):
    path = args.pop(0)
    m = Model.load(path)
    for qid, q in sorted(m.qualifiers.items()):
        n = len(m.elements_by_qualifier.get(qid, []))
        print("%6d  %-6s  %-40s  %d elements" %
              (qid, "system" if q.get("QUALIFIER_SYSTEM") else "user",
               q.get("QUALIFIER_NAME"), n))


def cmd_elements(args):
    path, qid = args[0], int(args[1])
    m = Model.load(path)
    for eid in m.elements_by_qualifier.get(qid, []):
        print("%6d  %s" % (eid, m.elements[eid].get("ELEMENT_NAME")))


def cmd_show(args):
    path, eid = args[0], int(args[1])
    m = Model.load(path)
    e = m.elements.get(eid)
    if e is None:
        print("No such element: %s" % eid, file=sys.stderr)
        sys.exit(1)
    print(_json({"id": eid, "name": e.get("ELEMENT_NAME"),
                  "qualifier_id": e.get("QUALIFIER_ID"),
                  "qualifier_name": m.qualifier_name(e.get("QUALIFIER_ID")),
                  "attributes": m.element_attributes(eid)}, pretty=True))


def cmd_tables(args):
    path = args[0]
    m = Model.load(path)
    for p in m.table_paths():
        print("%-55s %5d rows" % (p, len(m.table(p).rows)))


def cmd_table(args):
    path, table_path = args[0], args[1]
    m = Model.load(path)
    t = m.table(table_path)
    print(_json({"fields": [f.__dict__ for f in t.fields], "rows": t.rows}, pretty=True))


def cmd_rename(args):
    path, eid, new_name, out = args[0], int(args[1]), args[2], args[3]
    m = Model.load(path)
    m.set_name(eid, new_name)
    m.save(out)
    print("Renamed element %d -> %r, saved to %s" % (eid, new_name, out))


def cmd_gui(args):
    from .gui.app import main as gui_main
    gui_main(args)


COMMANDS = {
    "dump": cmd_dump,
    "qualifiers": cmd_qualifiers,
    "elements": cmd_elements,
    "show": cmd_show,
    "tables": cmd_tables,
    "table": cmd_table,
    "rename": cmd_rename,
    "gui": cmd_gui,
}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 1 or argv[0] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    cmd = argv[0]
    args = argv[1:]
    if cmd != "gui" and len(args) < 1:
        print(__doc__)
        sys.exit(1)
    COMMANDS[cmd](args)


if __name__ == "__main__":
    main()
