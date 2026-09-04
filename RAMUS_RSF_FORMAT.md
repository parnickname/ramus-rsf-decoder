# The Ramus `.rsf` file format — reverse-engineering notes and toolkit

**Source studied:** [`Vitaliy-Yakovchuk/ramus`](https://github.com/Vitaliy-Yakovchuk/ramus)
(GPL-3.0), a Java IDEF0/DFD business-process modeler. `.rsf` is its native
save format.

**Method:** the full repository was cloned and read (not guessed from
binaries) — in particular `core/.../FileIEngineImpl.java`,
`core/.../TableToXML.java` / `XMLToTable.java` (the exact export/import
code), `common/.../persistent/*` (the annotation-driven mini-ORM), the SQL
schema files under `database-storage/.../*.sql`, and `idef0-core/idef0-common`
(the IDEF0-specific attribute types). Every claim below was then
**cross-checked against three real `.rsf` files bundled in the repo itself**
(`dest/doc/en/Enterprise activity.rsf`, `dest/doc/ru/Model example.rsf`,
`dest/doc/ru/Пример модели.rsf`) by unzipping them and inspecting the actual
XML. Where something is inferred from source but *not* confirmed against a
real file or a running Ramus, it's flagged explicitly.

A companion Python toolkit (`rsf_core.py`, `rsf_model.py`, `rsf_cli.py`) is
provided as separate files and implements everything described here. It has
been tested by round-tripping and editing the real sample files (details in
[Verification](#verification)).

---

## Table of contents

1. [The big picture](#1-the-big-picture)
2. [Container format: it's a ZIP](#2-container-format-its-a-zip)
3. [The generic table XML format](#3-the-generic-table-xml-format)
4. [Value encoding rules, per SQL type](#4-value-encoding-rules-per-sql-type)
5. [The data model: a self-describing EAV database](#5-the-data-model-a-self-describing-eav-database)
6. [Full table reference](#6-full-table-reference)
7. [ID allocation and why external edits are safe](#7-id-allocation-and-why-external-edits-are-safe)
8. [The IDEF0 "function box" attribute set](#8-the-idef0-function-box-attribute-set)
9. [Decomposition hierarchy (partially understood)](#9-decomposition-hierarchy-partially-understood)
10. [Drawing new arrows (sectors / streams / crosspoints)](#10-drawing-new-arrows-sectors--streams--crosspoints)
11. [File-attribute / HTML-text streams](#11-file-attribute--html-text-streams)
12. [Old-format compatibility (branches/versioning)](#12-old-format-compatibility-branchesversioning)
13. [The toolkit](#13-the-toolkit)
14. [Verification](#14-verification)
15. [Source-file cross-reference](#15-source-file-cross-reference)

---

## 1. The big picture

Ramus's persistence layer (`core`, `database-storage`, `common/persistent`)
is a tiny embedded relational database framework of its own. At runtime it
keeps everything in a real SQL database (originally HSQLDB-style); a
`.rsf` file is simply **a dump of every table in that database, as XML,
zipped up**, plus a handful of raw binary "streams" (attachments, GUI
state, print settings) stored at their own paths inside the same zip.

Crucially, the dump format is **self-describing**: every table's XML
carries its own column names and SQL types inline, and the *set of tables
that exist* is itself listed in one of the tables (`persistents`). This is
what makes the format tractable to read and write externally — you don't
need a schema file, you can discover the schema from the file itself.

The actual application data (IDEF0 function boxes, DFD elements, arrows,
positions, colors, fonts, notes, everything) is stored as a generic
**Entity–Attribute–Value (EAV)** model: `qualifiers` are roughly "classes",
`elements` are "instances" of a qualifier, `attributes` are "fields", and
each attribute *type* (Text, Long, Rectangle, Color, Font, ...) has its own
physical value table keyed by `(attribute_id, element_id)`.

## 2. Container format: it's a ZIP

Open any `.rsf` with a normal zip tool (`unzip`, `zipfile.ZipFile`, 7-Zip,
etc.) — no special libraries needed. Layout (from a real 69 KB sample,
38 tables / 25 other files):

```
data/
  application_metadata.xml     Java Properties XML: app name/version, plugin list
  sequences.xml                Java Properties XML: a couple of custom ID counters
  application_preferencies.xml key/value app-level settings
  qualifiers.xml                <-- the EAV tables (see §6)
  elements.xml
  attributes.xml
  qualifiers_attributes.xml
  persistents.xml
  persistent_fields.xml
  streams.xml
  formulas.xml
  formula_dependences.xml
  Core/
    attribute_texts.xml         <-- one file per (plugin, attribute-type)
    attribute_longs.xml
    attribute_doubles.xml
    attribute_dates.xml
    attribute_hierarchicals.xml
    attribute_other_elements.xml
    ... (see §6 for the full list actually seen)
  IDEF0/
    attribute_rectangles.xml
    attribute_colors.xml
    attribute_fonts.xml
    attribute_statuses.xml
    ...
  Eval/
    attribute_functions.xml
elements/<element_id>/<attribute_id>/<plugin>/<file>   raw attachment/HTML bytes (see §11)
properties/...             misc app settings (page size, IDEF0 view options)
user/...                   GUI-only state: window layout, table column widths,
                            spell-checker config — never touch this, Ramus
                            regenerates it and doesn't validate it strictly
```

This exact layout is produced by
`FileIEngineImpl.writeToStream()` / `saveToFileNotCloseFile()`
(`core/src/main/java/com/ramussoft/core/impl/FileIEngineImpl.java`), and
read back by `FileIEngineImpl.open()` in the same file. Loading is
**tolerant of missing entries**: `loadTable()` just skips a table silently
if its zip entry doesn't exist (`InputStream stream = zFile.getInputStream(ze); if (stream != null) ...`).
This tolerance is exploited throughout this document (e.g. §12) to keep
generated files minimal.

## 3. The generic table XML format

Every `data/**/*.xml` file **except** `application_metadata.xml` and
`sequences.xml` (which are plain `java.util.Properties` XML, see below)
has this exact shape, produced by
`core/.../impl/TableToXML.java::store()` and consumed by
`core/.../impl/XMLToTable.java::load()`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<table generate-from-table="elements" generate-time="Sat Oct 17 15:44:09 EEST 2009" prefix="ramus_">
  <fields>
    <field id="0" name="ELEMENT_ID" type="BIGINT"/>
    <field id="1" name="ELEMENT_NAME" type="CLOB"/>
    <field id="2" name="QUALIFIER_ID" type="BIGINT"/>
  </fields>
  <data>
    <row><f id="0">4</f><f id="1">Infrastructure</f><f id="2">1</f></row>
    <row><f id="0">1</f><f id="1"/><f id="2">8</f></row>
  </data>
</table>
```

Rules (verified against real files):

- `<fields>` declares every column **for this file only**, with a small
  positional `id` (not the same thing as any row's data!) used purely to
  cross-reference `<f id="...">` inside `<row>` to a column name. Column
  order in `<fields>` does **not** have to match the physical DB column
  order — matching happens by **name** (case-insensitive) at import time,
  so a writer is free to declare columns in any order as long as the `id`s
  used in `<fields>` and in `<row><f id="...">` agree with each other.
- A row's `<f id="N">value</f>` is present **only if the underlying SQL
  value is non-`NULL`**. A present-but-empty string is written as a
  self-closing tag: `<f id="1"/>`. **A completely absent `<f id="N">` for
  that row means SQL `NULL`.** This distinction matters and the toolkit
  preserves it (`rsf_core.NULL` sentinel vs. `""`).
- `prefix="ramus_"` is the DB table-name prefix Ramus uses internally; it's
  written into the XML but not actually needed to parse the file (the
  physical prefix never appears in the zip *paths*, only inside this
  attribute, which the toolkit preserves verbatim but otherwise ignores).
- `generate-time` is informational (Java's `new Date().toString()`
  locale/timezone-dependent format) — cosmetic, safe to leave stale or
  regenerate.

### `application_metadata.xml` and `sequences.xml`

These two are standard `java.util.Properties` XML
(`http://java.sun.com/dtd/properties.dtd`):

```xml
<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
<comment>Ramus file metadata</comment>
<entry key="ApplicationName">Ramus</entry>
<entry key="ApplicationVersion">1.2</entry>
<entry key="FileOpenMinimumVersion">1.0</entry>
<entry key="PluginCount">26</entry>
<entry key="Plugin_0">Attribute.Core.Hierarchical</entry>
<entry key="Plugin_1">Core</entry>
... one entry per plugin ...
</properties>
```

- `FileOpenMinimumVersion` is checked against the running app's version on
  open (`FileIEngineImpl.checkFileVersion()`); a low value like `1.0`
  is maximally compatible and safe to use for generated files.
- The `Plugin_N` list is checked against the set of plugins the *running*
  app actually has loaded (`FileVersionException` if a listed plugin is
  missing) — so don't list plugins that don't exist. Sticking to the
  standard `Core` + `IDEF0` (+`Eval`, `Autochange` if you use formulas)
  plugin set, as in the real sample files, is safe.
- `sequences.xml` only ever held **one** custom counter in the sample
  files (`crosspoint_sequence`). It is *not* where element/qualifier/
  attribute ID counters live — see §7.

## 4. Value encoding rules, per SQL type

The `type="..."` on each `<field>` controls encoding, matching
`TableToXML`'s `Converter` classes exactly (all comparisons are
case-insensitive):

| declared `type`                    | Python/meaning                          | Encoding in `<f>` text |
|---|---|---|
| `BIGINT`, `INTEGER`, `int4`, `LONG`, `int8` | integer | plain decimal, e.g. `144` |
| `BOOLEAN`, `bool`                  | boolean | **`TRUE` / `FALSE`** (uppercase) |
| `DOUBLE`, `float8`                 | float   | Java `Double.toString()`, e.g. `80.0`, `-124.5` |
| `CLOB`, `CHAR`, `TEXT`, `bpchar`   | string  | raw text, XML-escaped |
| `TIMESTAMP`                        | date/time | see below |
| `BLOB`, `VARBINARY`, `bytea`       | bytes   | custom hex, see below |

**Booleans render as `TRUE`/`FALSE` uppercase**, *not* `true`/`false`. This
looks like it should be a bug — `TableToXML`'s own `BoolConverter` calls
plain `Object.toString()` on a boxed `java.lang.Boolean`, which is defined
by the JDK to always be lowercase — but the actual type-dispatch only
special-cases columns whose JDBC type name is exactly `"bool"`
(`meta.getColumnTypeName(...).equalsIgnoreCase("bool")`); real boolean
columns report as `"BOOLEAN"`, which **doesn't match**, so they silently
fall through to the generic string converter, which calls
`ResultSet.getString()` on a boolean column — and that's what actually
produces `"TRUE"`/`"FALSE"`. Confirmed byte-for-byte against real files.
The reader in `XMLToTable` (`Boolean.parseBoolean(...)`) is case-insensitive
either way, so this is safe to rely on but the toolkit **writes uppercase**
to match convention.

**Byte arrays** (`BLOB`/`VARBINARY`/`bytea` — icons, arrow "visual
attributes" blobs, `VisualData`) use a home-grown hex scheme, from
`TableToXML.ByteAConverter` / `XMLToTable.ByteAConverter`:

```java
// encode: for each signed byte b, write hex of (b + 128)
int j = bytes[i]; j += 128; retString.append(digits[j]);   // digits[0..255] = "00".."FF"
// decode: reverse
bs[i/2] = (byte) (val - 128);
```

Because `128 == 0x80`, "add 128 mod 256" and "flip the top bit" are the
same operation, so this is exactly `hex(byte XOR 0x80)` / `hex⁻¹(...) XOR 0x80`.
Implemented in the toolkit as `rsf_core.bytes_to_rsf_hex` /
`rsf_core.rsf_hex_to_bytes`. **This is not standard hex encoding** — feeding
a plain-hex tool at this data will silently produce garbage.

**Timestamps** use `DateFormat.getDateTimeInstance(SHORT, SHORT, Locale.ENGLISH)`,
which on the JDK the app was built/tested against (pre-JDK9 "COMPAT" locale
data) renders like `9/3/09 5:23 PM` — no comma, 2-digit year, no leading
zeros, 12-hour clock. **Confirmed against real file data.** Note: JDK 9+
switched the default locale data provider to CLDR, whose short pattern for
`en` *adds a comma* (`9/3/09, 5:23 PM`) — so files written by a Ramus build
running on a newer JDK may differ here. The toolkit's reader accepts both
forms; its writer emits the no-comma legacy form to match every sample
file actually inspected.

## 5. The data model: a self-describing EAV database

Four tables form the backbone (`database-storage/.../database.sql`):

```sql
qualifiers(QUALIFIER_ID, QUALIFIER_NAME, QUALIFIER_SYSTEM, ATTRIBUTE_FOR_NAME)
elements(ELEMENT_ID, ELEMENT_NAME, QUALIFIER_ID)
attributes(ATTRIBUTE_ID, ATTRIBUTE_NAME, ATTRIBUTE_TYPE_PLUGIN_NAME,
           ATTRIBUTE_TYPE_NAME, ATTRIBUTE_TYPE_COMPARABLE, ATTRIBUTE_SYSTEM)
qualifiers_attributes(QUALIFIER_ID, ATTRIBUTE_ID, ATTRIBUTE_SYSTEM, ATTRIBUTE_POSITION)
```

Read them as: *"a `qualifier` is a class; an `element` is an instance of one
qualifier; `qualifiers_attributes` says which `attribute`s (fields) are
attached to which qualifier (class)."* An IDEF0 diagram page is one
qualifier; every function box drawn on it is one element under that
qualifier.

**Where do the actual values live?** Not in `elements` (that table only has
an ID, a display name, and the owning qualifier). Each *attribute type*
(`(ATTRIBUTE_TYPE_PLUGIN_NAME, ATTRIBUTE_TYPE_NAME)`, e.g. `("Core","Text")`,
`("IDEF0","FRectangle")`) has its **own physical table**, keyed by
`(ATTRIBUTE_ID, ELEMENT_ID)`. This mapping is registered in two more
self-describing tables:

```sql
persistents(PERSISTENT_ID, TABLE_NAME, TABLE_TYPE, CLASS_NAME, PLUGIN_NAME, TYPE_NAME, PERSISTENT_EXISTS)
persistent_fields(PERSISTENT_FIELD_ID, PERSISTENT_ID, FIELD_NAME, FIELD_DATABASE_NAME,
                   FIELD_ID, FIELD_EXISTS, FIELD_TYPE, FIELD_AUTOSET, FIELD_PRIMARY)
```

e.g. a real `persistents` row:

```
PERSISTENT_ID=4  TABLE_NAME=ramus_attribute_texts  CLASS_NAME=com.ramussoft.core.attribute.simple.TextPersistent
                 PLUGIN_NAME=Core  TYPE_NAME=Text
```

...meaning: every attribute whose `(ATTRIBUTE_TYPE_PLUGIN_NAME,
ATTRIBUTE_TYPE_NAME) == ("Core","Text")` stores its value as a row in
`data/Core/attribute_texts.xml`. **This means the file genuinely tells you
its own schema** — you don't need this document at all to do a *generic*
read of any `.rsf` file (the toolkit's `rsf_core.py` layer does exactly
this, with zero hardcoded knowledge of IDEF0). This document and
`rsf_model.py`'s `TYPE_MAP` exist to save you from *re-deriving* which
table/columns go with which attribute type, and to give typed
get/set helpers instead of raw row dicts.

Each physical value table's row shape was read from the corresponding
Java `@Table`-annotated class in `common/persistent/` and
`core-simple-attributes` / `idef0-core`, e.g.:

```java
@Table(name = "rectangles")
public class FRectanglePersistent extends AbstractPersistent {
    @Double(id = 2) double x;
    @Double(id = 3) double y;
    @Double(id = 4) double width;
    @Double(id = 5) double height;
}
```

`AbstractPersistent` itself contributes the `(attribute_id, element_id)`
key columns every value table has. The physical table name is
`ramus_attribute_<name>` → zip path `data/<plugin>/attribute_<name>.xml`.

**Row cardinality per `(attribute_id, element_id)` differs by type:**
most types are exactly **one row** (`ONE_TO_ONE`, the annotation default) —
a function box has exactly one rectangle, one color, one status. A few are
explicitly `ONE_TO_MANY` (`OtherElementPersistent`, `HierarchicalPersistent`)
or have extra primary-key columns beyond `(attribute_id, element_id)`
(`SectorPointPersistent` adds `x_ordinate_id, y_ordinate_id`) — those can
have **many** rows sharing the same `(attribute_id, element_id)`, e.g. all
the points of one arrow's route. The toolkit's `TYPE_MAP` tags each type
`'scalar'` (single value column), `'struct'` (single row, several named
columns), or `'list'` (any number of rows) accordingly.

## 6. Full table reference

Every table below was seen in at least one of the three real sample files
(mostly the English "Enterprise activity" sample); columns are exactly as
declared in that file's own `<fields>`.

### Core tables (not attribute-type-specific)

| zip path | columns | notes |
|---|---|---|
| `data/qualifiers.xml` | QUALIFIER_ID, QUALIFIER_NAME, QUALIFIER_SYSTEM, ATTRIBUTE_FOR_NAME | ATTRIBUTE_FOR_NAME points at the "Name" attribute used to label this qualifier's elements |
| `data/elements.xml` | ELEMENT_ID, ELEMENT_NAME, QUALIFIER_ID | |
| `data/attributes.xml` | ATTRIBUTE_ID, ATTRIBUTE_NAME, ATTRIBUTE_TYPE_PLUGIN_NAME, ATTRIBUTE_TYPE_NAME, ATTRIBUTE_TYPE_COMPARABLE, ATTRIBUTE_SYSTEM | |
| `data/qualifiers_attributes.xml` | QUALIFIER_ID, ATTRIBUTE_ID, ATTRIBUTE_SYSTEM, ATTRIBUTE_POSITION | which attributes exist on which qualifier, and their display order |
| `data/persistents.xml` | PERSISTENT_ID, TABLE_NAME, TABLE_TYPE, CLASS_NAME, PLUGIN_NAME, TYPE_NAME, PERSISTENT_EXISTS | registry of every value table (see §5) |
| `data/persistent_fields.xml` | PERSISTENT_FIELD_ID, PERSISTENT_ID, FIELD_NAME, FIELD_DATABASE_NAME, FIELD_ID, FIELD_EXISTS, FIELD_TYPE, FIELD_AUTOSET, FIELD_PRIMARY | column registry for each value table |
| `data/application_preferencies.xml` | OPTION_KEY, OPTION_VALUE | flat app settings |
| `data/streams.xml` | STREAM_ID | index of every raw-attachment path used elsewhere in the zip (see §11) |
| `data/formulas.xml` | ELEMENT_ID, ATTRIBUTE_ID, AUTORECALCULATE, FORMULA | Eval-plugin formula text, keyed by the cell it's attached to |
| `data/formula_dependences.xml` | SOURCE_ELEMENT_ID, SOURCE_ATTRIBUTE_ID, ELEMENT_ID, ATTRIBUTE_ID | formula dependency graph edges |

Newer files (2.0+, per `update4.sql`) may additionally carry: `data/branches.xml`,
`data/attributes_history.xml`, `data/qualifiers_history.xml`,
`data/attributes_data_metadata.xml`, `data/formulas_data_metadata.xml`,
`data/formula_dependences_data_metadata.xml` — the model-branching
("compare/merge model versions") feature. **None of these were present in
any of the three real sample files** (all pre-date that feature), and per
§12 they're entirely optional for files targeting a single branch/trunk.

### Attribute-type value tables (Core plugin)

| zip path | columns | Java class | cardinality |
|---|---|---|---|
| `data/Core/attribute_texts.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(CLOB) | `TextPersistent` | one |
| `data/Core/attribute_longs.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(BIGINT) | `LongPersistent` | one |
| `data/Core/attribute_doubles.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(DOUBLE) | `DoublePersistent` | one |
| `data/Core/attribute_dates.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(TIMESTAMP) | `DatePersistent` | one |
| `data/Core/attribute_currencies.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(DOUBLE) | `CurrencyPersistent` | one |
| `data/Core/attribute_booleans.xml`* | ATTRIBUTE_ID, ELEMENT_ID, VALUE(INTEGER 0/1) | `BooleanPersistent` | one |
| `data/Core/attribute_variants.xml` | ATTRIBUTE_ID, ELEMENT_ID, VARIANT_ID(BIGINT) | `VariantPersistent` | one |
| `data/Core/attribute_variant_properties.xml` | ATTRIBUTE, POSITION, VALUE, VARIANT_ID | `VariantPropertyPersistent` | list — the option list backing a Variant-type attribute |
| `data/Core/attribute_icons.xml` | ATTRIBUTE_ID, ELEMENT_ID, ICON(bytes), NAME | `IconPersistent` | one |
| `data/Core/attribute_attached_files.xml` | ATTRIBUTE_ID, ELEMENT_ID, LAST_MODIFIED_TIME, NAME, PATH, UPLOAD_TIME | `FilePersistent` (metadata only — file bytes are a stream, §11) | one |
| `data/Core/attribute_other_elements.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_ELEMENT(BIGINT) | `OtherElementPersistent` | **list** (ONE_TO_MANY) |
| `data/Core/attribute_other_element_properties.xml` | ATTRIBUTE, QUALIFIER, QUALIFIER_ATTRIBUTE | `OtherElementPropertyPersistent` | per-qualifier config, not per-element |
| `data/Core/attribute_hierarchicals.xml` | ATTRIBUTE_ID, ELEMENT_ID, ICON_ID, PARENT_ELEMENT_ID, PREVIOUS_ELEMENT_ID | `HierarchicalPersistent` | **list** (ONE_TO_MANY); `-1`/`0` sentinel = no parent/no previous sibling — used to build tree/order UI for elements of a qualifier |
| `data/Core/attribute_element_lists.xml` | ATTRIBUTE_ID, ELEMENT1_ID, ELEMENT2_ID | `ElementListPersistent` | many-to-many edge table (+ optional CONNECTION_TYPE text) |
| `data/Core/attribute_element_list_properties.xml` | ATTRIBUTE_ID, QUALIFIER1, QUALIFIER2 | `ElementListPropertyPersistent` | which qualifier pairs a given ElementList-type attribute may connect |

\* not present in any sample inspected (no Boolean-type attribute happened to be used), but derived directly from `BooleanPersistent.java`; column names may need on-the-fly confirmation if you rely on it.

`Core.HTMLText` (rich-text "Description" fields) and `Core.File` (arbitrary
attachments) are **not** EAV rows at all — see §11.

### Attribute-type value tables (IDEF0 plugin)

| zip path | columns | Java class | cardinality |
|---|---|---|---|
| `data/IDEF0/attribute_rectangles.xml` | ATTRIBUTE_ID, ELEMENT_ID, HEIGHT, WIDTH, X, Y (all DOUBLE) | `FRectanglePersistent` | one — box position/size |
| `data/IDEF0/attribute_colors.xml` | ATTRIBUTE_ID, ELEMENT_ID, COLOR(INTEGER) | `ColorPersistent` | one — packed ARGB, see §8 |
| `data/IDEF0/attribute_fonts.xml` | ATTRIBUTE_ID, ELEMENT_ID, NAME(CLOB), SIZE(INTEGER), STYLE(INTEGER) | `FontPersistent` | one — STYLE is AWT `Font` style bits (0=plain,1=bold,2=italic,3=bold+italic) |
| `data/IDEF0/attribute_statuses.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_NAME(CLOB), TYPE(INTEGER) | `StatusPersistent` | one |
| `data/IDEF0/attribute_function_types.xml` | ATTRIBUTE_ID, ELEMENT_ID, TYPE(INTEGER) | `FunctionTypePersistent` | one — this is what `F_TYPE` uses |
| `data/IDEF0/attribute_function_ouners.xml` | ATTRIBUTE_ID, ELEMENT_ID, OUNER_ID(BIGINT) | `FunctionOunerPersistent` | one (`OUNER_ID`, sic — original code's spelling) |
| `data/IDEF0/attribute_decomposition_types.xml` | ATTRIBUTE_ID, ELEMENT_ID, TYPE(INTEGER) | `DecompositionTypePersistent` | one |
| `data/IDEF0/attribute_visual_datas.xml` | ATTRIBUTE_ID, ELEMENT_ID, DATA(bytes) | `VisualDataPersisitent` | one — opaque cached-rendering blob, safe to leave unset (F_VISUAL_DATA is used in only one legacy code path, `NFunction.PROPERTIES`) |
| `data/IDEF0/attribute_any_to_any_elements.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_ELEMENT(BIGINT) | `AnyToAnyPersistent` | list |
| `data/IDEF0/attribute_model_preferences.xml` | ATTRIBUTE_ID, CHANGE_DATE, CREATE_DATE, DEFINITION, ELEMENT_ID, PROJECT_AUTOR, PROJECT_NAME, USED_AT | `IDEF0ModelPreferencesPersistent` | one — the model-info fields shown in Ramus's "Model Properties" dialog |
| `data/IDEF0/attribute_readers.xml` | ATTRIBUTE_ID, DATE, ELEMENT_ID, READER(CLOB) | `ReaderPersistent` | one row per reviewer entry, keyed additionally somehow — treat as list |
| `data/IDEF0/attribute_sectors.xml` | ALTERNATIVE_TEXT, ATTRIBUTE_ID, CREATE_POS, CREATE_STATE, ELEMENT_ID, SHOW_TEXT, VISUAL_ATTRIBUTES(bytes)[, TEXT_ALIGMENT — newer files] | `SectorPersistent` | one — see §10, arrows |
| `data/IDEF0/attribute_sector_borders.xml` | ATTRIBUTE_ID, BORDER_TYPE, CROSSPOINT, ELEMENT_ID, FUNCTION, FUNCTION_TYPE, TUNNEL_SOFT | `SectorBorderPersistent` | one — see §10 |
| `data/IDEF0/attribute_sector_points.xml`† | ATTRIBUTE_ID, ELEMENT_ID, X_ORDINATE_ID, Y_ORDINATE_ID, X_POSITION, Y_POSITION, POINT_TYPE, POSITION | `SectorPointPersistent` | **list**, extra PK columns — see §10 |
| `data/IDEF0/attribute_sector_properties.xml`† | ATTRIBUTE_ID, ELEMENT_ID, SHOW_TILDA, SHOW_TEXT, TRANSPARENT, TILDA_POS, TEXT_X, TEXT_Y, TEXT_WIDTH, TEXT_HIEGHT (sic) | `SectorPropertiesPersistent` | one |

† not present in the sample files inspected (they predate this table /
never used it); column list derived directly from the Java source.

### Other plugins seen

| zip path | columns | notes |
|---|---|---|
| `data/Eval/attribute_functions.xml` | ATTRIBUTE_ID, AUTOCHANGE, ELEMENT_ID, FUNCTION(CLOB), QUALIFIER_ATTRIBUTE_ID, QUALIFIER_TABLE_ATTRIBUTE_ID | formula-plugin per-cell config |

## 7. ID allocation and why external edits are safe

`ELEMENT_ID` / `QUALIFIER_ID` / `ATTRIBUTE_ID` are each their own
independent counter. At runtime Ramus uses real SQL sequences
(`CREATE SEQUENCE ramus_elements_sequence START 1`, etc.) — but **those
sequences are not part of the exported file** and are *not* restored from
`sequences.xml` (that file only ever holds the two IDEF0-plugin custom
counters, `crosspoint_sequence`/`ordinates__sequence`; it has nothing to do
with element/qualifier/attribute IDs).

So how does Ramus avoid ID collisions after loading a file whose IDs were
inserted directly (bypassing the sequence) and are way ahead of the fresh
DB's sequence counter (which restarts at 1 every time)? Every creation
path re-syncs on the fly, e.g. `IEngineImpl.createElement()`:

```java
if (elementId == -1) {
    elementId = nextValue("elements_sequence");
    long id = template.queryForLong("SELECT MAX(ELEMENT_ID) FROM " + prefix + "elements;");
    while (id >= elementId) {
        elementId = template.nextVal(prefix + "elements_sequence");
    }
}
```

i.e. it keeps drawing from the sequence until the value exceeds the
current `MAX(id)` in the table. **Practical consequence: any tool
(including this one) can safely assign new IDs by taking
`max(existing ids in that table) + 1`.** Ramus will never hand out a
colliding ID later, no matter how far "ahead" your externally-assigned IDs
are. `rsf_model.Model.new_element_id()` / `new_qualifier_id()` /
`new_attribute_id()` do exactly this.

(This was verified by reading the Java source for `createElement`,
`createAttribute`, `createQualifier` — all three follow the identical
pattern — not by running the app; see [Verification](#verification) for
what *was* tested end-to-end.)

## 8. The IDEF0 "function box" attribute set

Whenever a qualifier represents an IDEF0 function-box container (an
"is-a-diagram-page" qualifier), `IDEF0Plugin.checkIDEF0Attributes()`
guarantees it carries this exact attribute set (confirmed against real
file data — this is qualifier 9, "Enterprise activity", the root diagram,
in the English sample):

| ATTRIBUTE_NAME | plugin.type | meaning | value shape |
|---|---|---|---|
| `Name` | Core.Text | box label (also mirrored into `elements.ELEMENT_NAME`) | string |
| `Description` | Core.HTMLText | rich-text notes | stream, see §11 |
| `F_VISUAL_DATA` | IDEF0.VisualData | opaque render cache | bytes, safe to omit |
| `F_BACKGROUND` | IDEF0.Color | fill color | packed ARGB int, see below |
| `F_FOREGROUND` | IDEF0.Color | border/text color | packed ARGB int |
| `F_BOUNDS` | IDEF0.FRectangle | position + size on the page | `{X, Y, WIDTH, HEIGHT}` doubles |
| `F_FONT` | IDEF0.Font | label font | `{NAME, STYLE, SIZE}` |
| `F_STATUS` | IDEF0.Status | review/workflow status | `{TYPE:int, OTHER_NAME:str}` |
| `F_TYPE` | IDEF0.Type | box kind (function/`3` seen on every ordinary box in the samples; other values are DFD-related — not enumerated here) | int |
| `F_OUNER_ID` | IDEF0.OunerId | (sic) some kind of owner reference — not fully traced, see §9 | long |
| `F_DECOMPOSITION_TYPE` | IDEF0.DecompositionType | IDEF0 vs DFD vs ... for this box's child diagram | int |
| `F_AUTHOR` | Core.Text | | string |
| `F_CREATE_DATE` / `F_REV_DATE` / `F_SYSTEM_REV_DATE` | Core.Date | | timestamp string |
| `F_LINK` | Core.Long | cross-reference to another element (glossary term, etc.) | long |
| `F_SECTOR_FUNCTION`, `F_SECTOR_STREAM`, `F_STREAM_NAME`, `F_SECTOR_ATTRIBUTE`, `F_SECTOR_BORDER_START`, `F_SECTOR_BORDER_END`, `F_STREAM_ADDED` | various | arrow-routing plumbing | see §10 |
| `F_BASE_FUNCTION_QUALIFIER_ID` | Core.Long | **only actually attached to the `F_BASE_FUNCTIONS` system qualifier**, not to ordinary boxes — see §9 | long |
| `F_PROJECT_PREFERENCES` | IDEF0.ProjectPreferences | model metadata (only meaningful on the model-root entry) | struct |

**Color encoding**: `java.awt.Color.getRGB()` = packed `0xAARRGGBB`,
reinterpreted as a **signed 32-bit int**. Pure opaque green
(`0xFF00FF00`, Ramus's default function-box fill) is `-16711936`; opaque
black is `-16777216`. Confirmed against every sample file (every ordinary
function box uses exactly these two values for background/foreground).
`rsf_model.argb(r, g, b, a=255)` / `unpack_argb(value)` convert between
0–255 RGBA and this representation.

## 9. Decomposition hierarchy (partially understood)

**Confirmed, from real file data:** there is a system qualifier named
`F_BASE_FUNCTIONS` (id 8 in the sample). Its **elements** (not ordinary
function boxes — separate bookkeeping elements, blank `ELEMENT_NAME`) each
carry `F_BASE_FUNCTION_QUALIFIER_ID` pointing at the qualifier that is a
**top-level model's root diagram**. In the sample: element 3 under
qualifier 8 has `F_BASE_FUNCTION_QUALIFIER_ID = 9`, and qualifier 9 is
indeed "Enterprise activity", the root page, whose elements are the boxes
you see when you open the file. `qualifiers_attributes.xml` confirms
`F_BASE_FUNCTION_QUALIFIER_ID` (attribute id 35) is attached **only** to
qualifier 8 — no ordinary function-box qualifier carries it.

**Not confirmed / explicitly out of scope:** how an *ordinary* function
box (e.g. element 80, "Administrative processes", sitting on the root
page) gets linked to *its own* child decomposition diagram when a user
double-clicks it in the GUI and draws a lower-level diagram. Tracing
`idef0-common/.../pb/data/negine/NDataPlugin.java` and
`IDEF0Plugin.isFunction()` / `findElementForBaseFunction()` shows this
goes through more GUI-side virtualization logic (a `RowSet`/`NFunction`
wrapper keyed off `IDEF0Plugin.getBaseFunctions()`) than a single stamped
attribute value, and involves `F_OUNER_ID` in a way that wasn't fully
pinned down from static reading alone — this would need either running the
actual Java app and diffing file state before/after using "Decompose", or
substantially more time tracing `NDataPlugin`/`NFunction`/`SectorRefactor`.

**What the toolkit gives you instead:**
- `Model.clone_qualifier_as_container(source_qualifier_id, name)` — the
  practical way to get a *valid new diagram page*: it copies the entire
  attribute set from an existing, known-good Function qualifier (found in
  a template file) onto a brand-new qualifier, rather than trying to
  bootstrap the IDEF0 system-attribute set from nothing. This was tested
  end-to-end (§14).
- `Model.register_model_root(base_functions_element_id, root_qualifier_id)`
  — sets up a *new top-level model* the same way element 3 does in the
  sample, so a freshly cloned diagram at least shows up as its own
  independent model root.
- Explicitly **not provided**: a "link this box to that child diagram"
  call, because it isn't verified. If you need this, the honest next step
  is tracing `NDataPlugin.getRowSet()` / `NFunction` further, or
  instrumenting a real Ramus build.

## 10. Drawing new arrows (sectors / streams / crosspoints)

IDEF0 arrows (data/resource flows between boxes, boundary ICOM arrows,
tunneled arrows, etc.) are modeled through `IDEF0.Sector` /
`IDEF0.SectorBorder` / `IDEF0.SectorPoint` / `IDEF0.SectorProperties`, plus
a "crosspoint" concept (`crosspoint_sequence` in `sequences.xml`) and, in
at least the 2009-era sample file, an "ordinates" concept that doesn't even
appear as its own table (no `attribute_sector_points.xml` in that file at
all — `IDEF0Plugin` source shows active migration/cleanup code for an even
older "`F_QUALIFIER_CROSSPOINT`" scheme, meaning this part of the format
visibly **changed across Ramus versions**).

**Creating a brand-new arrow is now supported** (`Model.add_arrow()` /
`Model.add_boundary_arrow()`), unlike in earlier revisions of this
document. This section previously said doing so safely wasn't practical
without a running Ramus to test against; that changed once the actual
Ramus source (github.com/Vitaliy-Yakovchuk/ramus) became fetchable from
this environment, so the arrow-creation code path itself could be read
directly instead of re-guessed from the container format alone:

- `idef0-common/.../pb/idef/elements/SectorRefactor.java` — `createNewSector()`
  is literally "the user just finished dragging a new arrow" in the real
  GUI; `createMiss()`/`createBorderPoints()` are its helpers.
- `idef0-common/.../pb/data/negine/{NSector,NSectorBorder,NCrosspoint}.java`,
  `AbstractCrosspoint.java`, `pb/Crosspoint.java`, `pb/data/SectorBorder.java`
  — the actual data-model semantics: what a border's `BORDER_TYPE` /
  `FUNCTION` / `FUNCTION_TYPE` / `CROSSPOINT` fields mean and how a
  crosspoint links sector borders into a connectivity graph.
- `idef0-core/.../idef0/IDEF0Plugin.java` — confirms `F_FUNCTION_SECTOR`
  (declared, real files populate it) is **never actually read anywhere**
  in the app; `Model.add_arrow()` deliberately leaves it unset rather than
  guess at a value nothing consults.
- `com/dsoft/utils/{DataSaver,DataLoader}.java` — the exact binary format
  of `IDEF0.Sector`'s `VISUAL_ATTRIBUTES` blob (a small custom
  little-endian serialization of a stroke/font/color, not Java object
  serialization).

Every piece of that was then **cross-checked against the real, populated
`attribute_sectors.xml`/`attribute_sector_borders.xml` data in all three
bundled sample files** — not just read in isolation:

- A Python decoder mirroring `DataLoader`'s exact byte layout was run
  against real sectors' `VISUAL_ATTRIBUTES` blobs and left **zero leftover
  bytes**, confirming the format byte-for-byte (stroke: line width, cap,
  join, dash phase, miter limit, dash array; then font name/size/style;
  then RGB color).
- The simplest, most common real arrow shape — a straight box-to-box
  connection — was isolated and found to be **one `Sector` element with
  both borders `TYPE_FUNCTION`** (`BORDER_TYPE=-1`, `FUNCTION=<box
  element id>`, `FUNCTION_TYPE=<side>`, each with its own freshly-minted
  `CROSSPOINT`); this is what 283 of the 288 arrows in "Enterprise
  activity.rsf" actually look like.
- A boundary arrow (one end on a box, one end on the diagram's own edge)
  was isolated the same way: `BORDER_TYPE` on the boundary end reuses the
  *same* side encoding as `FUNCTION_TYPE` (confirmed via
  `MovingPanel.{RIGHT=0,BOTTOM=1,LEFT=2,TOP=3}`, which `SectorRefactor`
  compares a border's `FUNCTION_TYPE` against directly).
- Critically: **no unmodified real arrow in any of the three sample files
  has any `attribute_sector_points.xml` row at all** — meaning Ramus
  computes a straight/default route between two edge points at *paint
  time*, and only a manually bent/dragged arrow ends up with stored
  ordinates. `add_arrow()`/`add_boundary_arrow()` reproduce exactly that
  unmodified, auto-routed state (no path data written), which is what
  every arrow starts as.
- `Model.new_crosspoint_id()` deliberately does **not** trust the
  persisted `crosspoint_sequence` value the way §7 shows element/
  qualifier/attribute ids can be trusted to self-heal: reading
  `NDataPlugin.createCrosspoint()`, Ramus's own crosspoint sequence has no
  `MAX(existing)`-resync loop the way `IEngineImpl.createElement()` etc.
  do (confirmed from source) — and indeed the bundled sample file's own
  `crosspoint_sequence` (`31`) is far below its actual highest used
  `CROSSPOINT` value (`54927`), almost certainly stale from a
  pre-migration counter reset. `new_crosspoint_id()` instead derives a
  safe value from `MAX(CROSSPOINT)` already present in the loaded file's
  own border data — tested by adding a new arrow to the real, unmodified
  "Enterprise activity.rsf" and confirming the freshly allocated
  crosspoint ids don't collide with any of its 260 pre-existing ones.
- Round-tripped: added arrows survive `Model.save()` → `Model.load()`
  with every field intact, on both a from-scratch file
  (`template.new_model()`, which needed `F_SECTORS`/`F_STREAMS` and their
  attribute set bootstrapped from nothing — see
  `Model.ensure_arrow_support()`) and the real sample file (which already
  has them, as every real Ramus file does).

**What's provided:**

- `Model.add_arrow(from_element_id, from_side, to_element_id, to_side, *,
  name="", tunnel=False)` — a straight arrow directly between two function
  boxes on the same diagram. `from_side`/`to_side` are `ArrowSide` values
  (`LEFT`=Input, `TOP`=Control, `RIGHT`=Output, `BOTTOM`=Mechanism, or the
  `INPUT`/`CONTROL`/`OUTPUT`/`MECHANISM` aliases). Returns the new
  Stream element id (the arrow's own identity/label).
- `Model.add_boundary_arrow(element_id, box_side, page_side, *,
  direction="in", name="", tunnel=False)` — an ICOM arrow between a
  function box and the diagram page's own edge (entering or leaving the
  diagram from outside).
- `Model.ensure_arrow_support()` — bootstraps `F_SECTORS`/`F_STREAMS` and
  their attribute set on a file that doesn't have them yet (called
  automatically by the two methods above).
- `encode_sector_visual_attributes(...)` — build a custom
  `VISUAL_ATTRIBUTES` blob (line width, cap/join, dash, font, color) if
  you don't want the verified real-Ramus-default look
  `add_arrow()`/`add_boundary_arrow()` use otherwise.

**What's still *not* provided, and why:**

- **Multi-segment / bent arrows.** Real files do chain several `Sector`
  elements into one arrow via a shared `CROSSPOINT` at the join (verified
  against a real 4-sector stream), so the mechanism is understood, but
  it wasn't built into a public helper — the routing choices a bend
  implies (which crosspoint is `TYPE_ONE_IN` vs `TYPE_ONE_OUT`, i.e. which
  end fans out) go beyond what's needed for the common case and weren't
  exercised against enough real multi-segment examples to be as confident
  in as the single-segment shapes above. `Model.table(...)` can still get
  you there by hand, following the same borders/crosspoint fields.
- **Linking a function box to its own child decomposition diagram** —
  unrelated to arrows, still unimplemented; see §9.
- Still unconfirmed by an actual Ramus GUI render (see §14) — everything
  above is "matches real saved data and the code that produces it"
  confidence, not "watched Ramus draw it" confidence.

Columns are fully documented in §6 (`attribute_sectors.xml`,
`attribute_sector_borders.xml`, `attribute_sector_points.xml`), and the
generic table API (`Model.table(path)`) can read and edit any of them like
any other table for anything the helpers above don't cover — e.g. renaming
an existing arrow's `ALTERNATIVE_TEXT`, or hand-building a multi-segment
route.

## 11. File-attribute / HTML-text streams

`Core.File` and `Core.HTMLText`-typed attributes (e.g. the `Description`
field on a function box) are **not** stored as EAV rows. From
`AbstractFilePlugin.java`:

```java
public String getFilePath(long elementId, long attributeId) {
    return "/elements/" + elementId + "/" + attributeId + "/Core/" + getFileName();
}
// HTMLTextPlugin.getFileName() -> "index.html"
```

i.e. the raw bytes (HTML for `Description`, or the original filename's
bytes for a generic file attachment) are written as their own zip entry at
that literal path (leading `/` stripped when actually written to the zip,
per `FileIEngineImpl.createZipEntry()`), and a matching row is added to
`data/streams.xml` (`STREAM_ID` = the same path, **with** the leading
`/`). The real sample files confirm this general stream-storage mechanism
(e.g. `/elements/767/17/report.0.xml` entries exist for a *different*
feature, the report-template editor, using the identical
`/elements/<id>/<n>/...` convention) but happen not to have any function
box with a non-empty `Description`, so this specific path was not observed
populated in a real file — it is derived directly from `AbstractFilePlugin`
/ `HTMLTextPlugin` source, not confirmed byte-for-byte against a real
`Description` value. `Model.set_value(element_id, description_attr_id, html_bytes)`
implements exactly this (see `Model._stream_path` / `_set_stream` in
`rsf_model.py`), and was tested mechanically (write + reload gets the
bytes back, streams-table bookkeeping stays consistent) but **not**
against a real Ramus GUI render.

## 12. Old-format compatibility (branches/versioning)

The 2009-era sample files have **no** `branches`, `attributes_history`,
`qualifiers_history`, `*_data_metadata` tables at all (those were added in
`update4.sql`, part of a later "model branching" feature). Loading code
tolerates every one of these being absent (`loadTable` skips missing
entries silently), and `created_branch_id`/`removed_branch_id` columns
that do exist on `elements`/`qualifiers`/`attributes`/`streams` default
sensibly when absent from a row's `<fields>` (`XMLToTable`'s SAX handler
pre-fills `0` / `Integer.MAX_VALUE` for any `*_branch_id` column not
explicitly present in a row). **Practical consequence: you can emit the
simpler pre-2.0 table shapes (3–4 columns, no branch bookkeeping at all)
and current Ramus (2.0.x) will still load the file correctly**, getting
implicit trunk/branch-0 semantics for free. This is what the toolkit does
by default (it never adds branch-related tables/columns unless they were
already present in the file you loaded).

## 13. The toolkit

Three files, no third-party dependencies (pure Python 3, stdlib only:
`zipfile`, `xml.etree.ElementTree`):

### `rsf_core.py` — container layer

- `Table` — one parsed `data/**/*.xml` file: `.fields` (name/type/id),
  `.rows` (list of `{COLUMN_NAME: value}` dicts, values already decoded to
  native Python types per §4), plus `.find_rows(**eq)` and `.max_int(col)`
  helpers. `.to_xml_bytes()` re-serializes it, matching the real format
  exactly (verified, §14).
- `RsfArchive` — the whole zip: `.tables` (dict path→`Table`),
  `.properties` (dict path→dict, for the two Properties-XML files),
  `.raw` (dict path→bytes, for everything else — GUI state, attachments,
  print settings — preserved byte-for-byte on save unless you touch it).
  `.load(path)` / `.save(path)`.
- `bytes_to_rsf_hex` / `rsf_hex_to_bytes` — the byte↔hex codec from §4.
- `parse_rsf_date` / `format_rsf_date` — the timestamp format from §4.
- This layer is **fully generic** — it doesn't know or care what IDEF0 is.
  It can load, inspect, and losslessly re-save *any* `.rsf` file,
  including future ones with tables this document doesn't mention.

### `rsf_model.py` — semantic (EAV) layer

Built on top of `rsf_core`. Key pieces:

- `TYPE_MAP` — the `(plugin, type) -> (table path, mode, columns)` table
  from §5/§6, `mode` ∈ `{scalar, struct, list, stream}`.
- `Model(archive)` / `Model.load(path)` — indexes qualifiers / elements /
  attributes / qualifier-attribute links on construction (`.refresh()` to
  re-index after raw edits via `.table(...)`).
- Generic value access: `get_value(element_id, attribute_id)` /
  `set_value(element_id, attribute_id, value)` / `delete_value(...)` —
  dispatches on the attribute's declared type via `TYPE_MAP`, so this
  works for *any* mapped type, not just the IDEF0 ones.
- Lookups: `find_qualifier(name)`, `find_attribute(qualifier_id, name)`,
  `element_qualifier(element_id)`, `attribute_type(attribute_id)`.
- Structure edits: `add_element(qualifier_id, name)`,
  `set_element_name`, `delete_element`,
  `clone_qualifier_as_container(source_qualifier_id, new_name)` (§9),
  `register_model_root(...)` (§9), `new_element_id()` /
  `new_qualifier_id()` / `new_attribute_id()` (§7-safe ID allocation).
- IDEF0 function-box convenience wrappers (§8): `set_name`, `set_bounds`,
  `set_background`, `set_foreground`, `set_font`, `set_status`, and the
  one-shot `add_function_box(qualifier_id, name, x, y, width, height, ...)`.
- `argb(r,g,b,a=255)` / `unpack_argb(value)` — color codec from §8.
- Arrows (§10): `add_arrow(from_element_id, from_side, to_element_id,
  to_side, name="", tunnel=False)` (box-to-box), `add_boundary_arrow(
  element_id, box_side, page_side, direction="in", name="", tunnel=False)`
  (box-to-page-edge), `ensure_arrow_support()` (bootstraps `F_SECTORS`/
  `F_STREAMS` if the file doesn't have them), `ArrowSide`/`TunnelType`
  constants, `encode_sector_visual_attributes(...)` for custom arrow
  styling.
- `dump_model(model, include_system_qualifiers=False)` — a full,
  JSON-serialisable snapshot of the whole model (every qualifier → every
  element → every resolved attribute), meant for feeding to a human or an
  AI, not as a round-trip edit format.
- `apply_json_dump(model, data)` — the inverse: patches `dump_model()`-
  shaped JSON (e.g. hand-edited/redacted) back onto the model, matching
  qualifiers/elements by id; see `LLM_REDACTION_GUIDE.md` for the exact
  rules an editor (human or AI) should follow.
- `Model.table(path)` — escape hatch to any raw table for anything not
  covered by the semantic helpers (multi-segment arrows, etc., per §10).

### `rsf_cli.py` — command-line front-end

```
python3 rsf_cli.py dump FILE.rsf [--all] [--pretty]      # whole model as JSON
python3 rsf_cli.py qualifiers FILE.rsf                    # list qualifiers
python3 rsf_cli.py elements FILE.rsf QUALIFIER_ID          # list elements under one
python3 rsf_cli.py show FILE.rsf ELEMENT_ID                 # one element's attributes
python3 rsf_cli.py tables FILE.rsf                          # every raw table + row count
python3 rsf_cli.py table FILE.rsf TABLE_PATH                # dump one raw table
python3 rsf_cli.py rename FILE.rsf ELEMENT_ID NEW_NAME OUT.rsf
```

### Example: read an existing file

```python
from rsf_model import Model, dump_model
import json

m = Model.load("MyModel.rsf")
print(m.qualifier_name(9))                 # -> "Enterprise activity"
print(m.element_attributes(79))             # -> {'Name': ..., 'F_BOUNDS': {...}, ...}
json.dump(dump_model(m), open("dump.json", "w"), ensure_ascii=False, indent=2)
```

### Example: edit an existing file

```python
from rsf_model import Model

m = Model.load("MyModel.rsf")
m.set_name(80, "Renamed box")
m.set_bounds(80, x=100, y=100, width=140, height=90)
m.save("MyModel_edited.rsf")
```

### Example: generate a brand-new diagram from a template

```python
from rsf_model import Model

# any existing .rsf works as a template -- it just needs one qualifier
# that already has the full IDEF0 function-box attribute set (any real
# diagram page qualifies).
m = Model.load("template.rsf")
root = m.find_qualifier("Enterprise activity")

new_qid = m.clone_qualifier_as_container(root, "My New Process")
m.add_function_box(new_qid, "Receive Order",  x=40,  y=40, width=140, height=80)
m.add_function_box(new_qid, "Process Order",  x=240, y=40, width=140, height=80)
m.add_function_box(new_qid, "Ship Order",     x=440, y=40, width=140, height=80)

# optional: register it as its own top-level model in the navigator
bf = m.find_base_functions_qualifier()
root_elem = m.add_element(bf, name="")
m.register_model_root(root_elem, new_qid)

m.save("new_diagram.rsf")
```

### Example: connect two boxes with a new arrow

```python
from rsf_model import Model, ArrowSide

m = Model.load("MyModel.rsf")
root = m.find_qualifier("Enterprise activity")
boxes = {m.elements[eid]["ELEMENT_NAME"]: eid
         for eid in m.elements_by_qualifier[root]}

# a straight arrow from "Receive Order"'s Output side to "Process Order"'s Input side
m.add_arrow(boxes["Receive Order"], ArrowSide.OUTPUT,
            boxes["Process Order"], ArrowSide.INPUT,
            name="Order")

# a Control arrow entering "Receive Order" from the top of the page
m.add_boundary_arrow(boxes["Receive Order"], ArrowSide.CONTROL, ArrowSide.TOP,
                      direction="in", name="Company policy")

m.save("MyModel_with_arrows.rsf")
```

## 14. Verification

No JVM/Gradle build of Ramus itself was available in the environment this
was built in (the sandbox's network allowlist doesn't include Maven
Central, so `./gradlew runLocal` cannot fetch dependencies) — so nothing
here was confirmed by opening the output in the actual Ramus GUI. What
*was* done instead, which is the strongest verification practical without
that:

1. **Static-analysis-only claims were held to a higher bar**: every table
   schema and encoding rule in this document was cross-checked against
   the **actual bytes of three real `.rsf` files** shipped in the Ramus
   repository itself (not synthetic examples) — `dest/doc/en/Enterprise
   activity.rsf`, `dest/doc/ru/Model example.rsf`,
   `dest/doc/ru/Пример модели.rsf`.
2. **Lossless round-trip test**: both English and Russian sample files
   were loaded with `RsfArchive.load()`, immediately saved back out with
   no edits, and every table's rows (and every raw/property entry) were
   compared field-by-field against the original — **zero mismatches**,
   including full-width Cyrillic text and empty-vs-null field
   distinctions.
3. **Edit round-trip test**: loaded the English sample, renamed an
   existing function box, added a brand-new one with full visual
   attributes (bounds/colors/font/status/type) under the *existing* root
   diagram qualifier, saved, reloaded, and confirmed every written value
   matches what was set. Diffing the saved file against the original
   showed **only the tables actually touched had changed** — all 25
   non-table entries (GUI state, streams, attachments) were preserved
   byte-for-byte.
4. **New-diagram-from-template test**: cloned the root qualifier's
   attribute set into a brand-new qualifier, added three function boxes to
   it, saved, reloaded, and confirmed the new qualifier + elements +
   attributes all read back correctly and the zip passes
   `zipfile.ZipFile.testzip()`.
5. **Model-root registration test**: added a new `F_BASE_FUNCTIONS`
   element and pointed it at a freshly cloned qualifier via
   `register_model_root`, saved, reloaded, confirmed the link.
6. **Color codec test**: `argb(0,255,0) == -16711936` and
   `argb(0,0,0) == -16777216` — matching the literal integer values seen
   on every function box's `F_BACKGROUND`/`F_FOREGROUND` in the real
   sample files.
7. **Arrow creation** (§10, added later once the real Ramus source became
   fetchable from this environment): the arrow-creation Java source was
   read directly rather than inferred, and every claim built from it was
   cross-checked against real data the same way as everything else here —
   a `VISUAL_ATTRIBUTES` blob decoder mirroring the real binary format
   read real sectors' blobs with zero leftover bytes; the simple box-to-
   box and box-to-boundary arrow shapes this module produces were
   isolated from and matched against hundreds of real arrows in
   "Enterprise activity.rsf"; a new arrow was added to that *unmodified
   real file* (not just a synthetic one) and its freshly allocated
   crosspoint ids were confirmed not to collide with any of the file's
   260 pre-existing ones; and the result round-tripped through
   save/reload with every field intact, both on that real file and on a
   from-scratch one via `template.new_model()` (whose `F_SECTORS`/
   `F_STREAMS` bootstrapping this exercised too, via
   `ensure_arrow_support()`).

What was **not** verified (clearly flagged inline above too): per-box
decomposition linking (§9), multi-segment/bent arrows and the exact byte
layout of a populated `Core.HTMLText` stream (§11) — these are read/write-
capable at the raw-table level but their higher-level "is this what
Ramus's GUI expects" correctness is unconfirmed. And more broadly: nothing
in this document, arrows included, has been confirmed by opening the
result in the actual Ramus GUI (no JVM/Gradle toolchain was available to
build and run it) — "matches real saved data and the source that produces
it" is the ceiling of what was verified here.

## 15. Source-file cross-reference

For anyone who wants to verify or extend this against the source directly
(all paths relative to the repo root):

| topic | file |
|---|---|
| save/load orchestration, zip layout | `core/src/main/java/com/ramussoft/core/impl/FileIEngineImpl.java` |
| table → XML export | `core/src/main/java/com/ramussoft/core/impl/TableToXML.java` |
| XML → table import | `core/src/main/java/com/ramussoft/core/impl/XMLToTable.java` |
| core SQL schema | `database-storage/src/main/resources/com/ramussoft/jdbc/database.sql` + `update1..5.sql` |
| ID allocation (`createElement`/`createAttribute`/`createQualifier`) | `core/src/main/java/com/ramussoft/core/impl/IEngineImpl.java` |
| persistent-object annotations (`@Table`, `@Text`, `@Long`, ...) | `common/src/main/java/com/ramussoft/common/persistent/*.java` |
| simple Core attribute types | `core-simple-attributes/src/main/java/com/ramussoft/core/attribute/simple/*.java` |
| file/HTML-text stream storage | `core-simple-attributes/.../simple/AbstractFilePlugin.java`, `HTMLTextPlugin.java` |
| IDEF0 system attribute set (`F_*` constants, `checkIDEF0Attributes`) | `idef0-core/src/main/java/com/ramussoft/idef0/IDEF0Plugin.java` |
| IDEF0 attribute persistents (Rectangle/Color/Font/Status/...) | `idef0-core/src/main/java/com/ramussoft/idef0/attribute/*.java` |
| GUI-side decomposition/row-set logic (unfinished tracing, §9) | `idef0-common/src/main/java/com/ramussoft/pb/data/negine/NDataPlugin.java`, `NFunction.java` |
| arrow creation entry point ("user just finished drawing"), §10 | `idef0-common/src/main/java/com/ramussoft/pb/idef/elements/SectorRefactor.java` |
| sector/border/crosspoint data model, §10 | `idef0-common/src/main/java/com/ramussoft/pb/data/negine/{NSector,NSectorBorder,NCrosspoint}.java`, `pb/data/AbstractCrosspoint.java`, `pb/data/SectorBorder.java`, `pb/Crosspoint.java`, `pb/Sector.java` |
| box/page-edge side constants (`ArrowSide`), §10 | `idef0-common/src/main/java/com/ramussoft/pb/idef/visual/MovingPanel.java` |
| `VISUAL_ATTRIBUTES` blob binary format, §10 | `idef0-common/src/main/java/com/dsoft/utils/{DataSaver,DataLoader}.java` |
| crosspoint id sequence (no resync-from-data, unlike element/etc ids), §7 & §10 | `idef0-core/src/main/java/com/ramussoft/idef0/IDEF0Plugin.java` (`getNextCrosspointId`), `idef0-common/.../negine/NDataPlugin.java` (`createCrosspoint`) |
| file-extension / launcher plumbing | `local-client/src/main/java/com/ramussoft/local/FilePlugin.java` |
| real sample files used for verification | `dest/doc/en/Enterprise activity.rsf`, `dest/doc/ru/Model example.rsf`, `dest/doc/ru/Пример модели.rsf` |

---

*Everything in this document was derived from the GPL-3.0-licensed Ramus
source and from `.rsf` sample files distributed in that same repository.*

---

## 16. GUI-specific addendum (this repository)

Everything above documents the file format and the reverse-engineered
Python toolkit as originally written. This repository adds a Qt-based GUI
(`ramus_rsf_tool/gui/`) and one new module, `ramus_rsf_tool/template.py`,
on top of it. Notes specific to those additions:

- **`template.py: new_model()`** bootstraps a minimal-but-valid archive
  from scratch (no template file required) so File > New in the GUI has
  something to start from: it hand-builds `qualifiers`/`elements`/
  `attributes`/`qualifiers_attributes` with the standard IDEF0 function-box
  attribute set (§8) on one root diagram qualifier, plus an
  `F_BASE_FUNCTIONS` bookkeeping element registering it as a model root
  (§9). This follows the same "pre-2.0 minimal table shapes" approach
  documented in §12, and is covered by `tests/test_rsf_model.py` (built,
  saved, reloaded, values verified) — but, like the rest of the toolkit,
  has not been opened in a real Ramus GUI.
- **The GUI's "Raw Tables" tab** is a thin, generic spreadsheet view over
  `Model.table(path)` (§13) — it has no special knowledge of any table's
  semantics, which is what makes it usable as the escape hatch §10
  recommends for arrow/sector editing and anything else with no dedicated
  editor in the "Attributes" tab.
- **The "Attributes" tab** dispatches purely on `TYPE_MAP` mode
  (`scalar`/`struct`/`list`/`stream`) plus each physical column's declared
  SQL type (§4), with a handful of nicer dedicated widgets for the
  well-known IDEF0 types (`Color`, `FRectangle`, `Font`, `Status`) — so any
  attribute type not specifically named there (including ones this
  document doesn't cover) still gets a usable, if generic, editor rather
  than being hidden.
