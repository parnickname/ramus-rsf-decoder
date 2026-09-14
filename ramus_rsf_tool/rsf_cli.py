#!/usr/bin/env python3
"""
rsf_cli.py -- инспектор командной строки для файлов Ramus (.rsf).

Использование:
    ramus-rsf-cli dump FILE.rsf [--all] [--pretty]
        Вывести всю модель (квалификаторы -> элементы -> атрибуты) в виде JSON.
        --all     включить также системные квалификаторы/атрибуты (по умолчанию:
                   только видимые пользователю)
        --pretty  отформатировать JSON с отступами (по умолчанию: компактно)

    ramus-rsf-cli qualifiers FILE.rsf
        Вывести список каждого квалификатора (id, имя, флаг системного, число элементов).

    ramus-rsf-cli elements FILE.rsf QUALIFIER_ID
        Вывести список каждого элемента одного квалификатора (id, имя).

    ramus-rsf-cli show FILE.rsf ELEMENT_ID
        Показать все разрешённые атрибуты одного элемента.

    ramus-rsf-cli tables FILE.rsf
        Вывести список каждой сырой таблицы данных, найденной в файле, с числом строк.

    ramus-rsf-cli table FILE.rsf TABLE_PATH
        Вывести одну сырую таблицу (например, data/IDEF0/attribute_sectors.xml) в виде JSON.

    ramus-rsf-cli rename FILE.rsf ELEMENT_ID NEW_NAME OUT.rsf
        Переименовать атрибут Name одного элемента и сохранить в OUT.rsf.

    ramus-rsf-cli import-json FILE.rsf DUMP.json OUT.rsf
        Применить (возможно, отредактированный/отцензурированный вручную)
        JSON-файл `dump` обратно к FILE.rsf как патч -- сопоставляет
        квалификаторы/элементы по id и обновляет только те значения
        скалярных/struct-атрибутов, которые реально изменились; никогда
        ничего не добавляет и не удаляет (см. rsf_model.apply_json_dump()).
        Сохраняет результат в OUT.rsf. Типичный рабочий процесс цензурирования:
            ramus-rsf-cli dump FILE.rsf --all --pretty > dump.json
            $EDITOR dump.json                      # отцензурировать конфиденциальный текст
            ramus-rsf-cli import-json FILE.rsf dump.json FILE.redacted.rsf

    ramus-rsf-cli gui [FILE.rsf]
        Запустить графический редактор (эквивалентно запуску ramus-rsf-gui).

Этот модуль также можно запускать напрямую: `python3 -m ramus_rsf_tool.rsf_cli ...`
"""
import json
import sys

from .rsf_model import Model, dump_model, apply_json_dump


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
        print("%6d  %-6s  %-40s  %d элементов" %
              (qid, "система" if q.get("QUALIFIER_SYSTEM") else "пользователь",
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
        print("Нет такого элемента: %s" % eid, file=sys.stderr)
        sys.exit(1)
    print(_json({"id": eid, "name": e.get("ELEMENT_NAME"),
                  "qualifier_id": e.get("QUALIFIER_ID"),
                  "qualifier_name": m.qualifier_name(e.get("QUALIFIER_ID")),
                  "attributes": m.element_attributes(eid)}, pretty=True))


def cmd_tables(args):
    path = args[0]
    m = Model.load(path)
    for p in m.table_paths():
        print("%-55s %5d строк" % (p, len(m.table(p).rows)))


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
    print("Элемент %d переименован -> %r, сохранено в %s" % (eid, new_name, out))


def cmd_import_json(args):
    path, json_path, out = args[0], args[1], args[2]
    m = Model.load(path)
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    result = apply_json_dump(m, data)
    m.save(out)
    print(result.summary())
    print("Сохранено в %s" % out)
    for w in result.warnings:
        print("предупреждение: %s" % w, file=sys.stderr)


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
    "import-json": cmd_import_json,
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
