# Guide for LLMs: redacting a Ramus RSF JSON dump

This document is written **for an LLM** (or a person scripting one) that has
been handed a JSON file produced by this app's dump/export feature and asked
to redact or otherwise edit sensitive text in it, so the result can be
re-imported and saved as a working `.rsf` file. If you are an LLM performing
this task, read this whole document before editing anything.

The JSON comes from `dump_model()` (`ramus_rsf_tool/rsf_model.py`) via either:

- the GUI's **Attributes / JSON Dump tab → Export to file…**, or
- `ramus-rsf-cli dump FILE.rsf [--all] [--pretty]`

...and goes back in via either:

- the GUI's **JSON Dump tab → Import from file…** (or **Apply edited text
  below**, if you're editing directly in the app), or
- `ramus-rsf-cli import-json FILE.rsf dump.json OUT.rsf`

Both import paths call the same function, `apply_json_dump()`, and that
function is a **patch**, not a full import/replace. Understanding exactly
what it does and doesn't do is the whole point of this guide — get it wrong
and your edits will either be silently skipped (annoying but safe) or, in
one specific case covered below, produce a file that no longer represents
what you intended.

## 1. The one rule that matters most

> **Editing a value in the JSON changes that value. Deleting or omitting a
> block does *nothing* — it does not delete the corresponding qualifier or
> element from the file.**

If your job is "redact sensitive information," the correct move for a
sensitive field is to **overwrite its value** (e.g. with `"[REDACTED]"`),
never to remove the JSON block around it. `apply_json_dump()` only patches
qualifiers/elements that are present in **both** the file and your JSON,
matched by numeric `id`. Anything in the file but missing from your JSON —
because you deleted it, or because the dump was taken with system
qualifiers excluded — is left completely untouched. There is no delete
operation in this workflow at all.

This also means: **never invent new `id` values or add new qualifier/
element/attribute blocks that weren't in the original dump.** They will be
looked up by id, not found, and silently skipped (reported as a warning,
not an error, but they will not appear in the saved file either).

## 2. The JSON shape

```json
{
  "qualifiers": [
    {
      "id": 9,
      "name": "Enterprise activity",
      "system": false,
      "elements": [
        {
          "id": 80,
          "name": "Administrative processes",
          "attributes": {
            "Name": "Administrative processes",
            "F_BOUNDS": {"X": 40.0, "Y": 40.0, "WIDTH": 140.0, "HEIGHT": 80.0},
            "F_BACKGROUND": -16711936,
            "F_FOREGROUND": -16777216,
            "F_FONT": {"NAME": "Dialog", "STYLE": 0, "SIZE": 12},
            "F_STATUS": {"TYPE": 0, "OTHER_NAME": "reviewed by J. Smith, ext. 4471"},
            "F_TYPE": 3,
            "F_AUTHOR": "J. Smith"
          }
        }
      ]
    }
  ]
}
```

- **Top level**: a single object with one key, `"qualifiers"` — a list.
  This exact wrapper is required; `apply_json_dump()`/the GUI import both
  reject anything that isn't `{"qualifiers": [...]}` at the top.
- **A qualifier** (`"id"`, `"name"`, `"system"`, `"elements"`): roughly a
  "class" — one IDEF0 diagram page, or one of the app's built-in system
  tables. `id` is the join key; `name` is its display name (editable —
  see §3); `system` is informational only, editing it has no effect.
- **An element** (`"id"`, `"name"`, `"attributes"`): an "instance" of its
  qualifier — a function box on a diagram, or a row in some other table.
  `id` is the join key; `name` mirrors the file's internal `ELEMENT_NAME`
  (editable — see §3); `attributes` is a dict of every value currently set
  on this element.
- **An attribute entry**: key = the attribute's name (e.g. `"Name"`,
  `"F_BOUNDS"`), or `"attr_<N>"` if it has no name. Value shape depends on
  the attribute's type — this is the part that needs care, covered next.

Only qualifiers/elements/attributes that actually have a value set appear
in the dump at all — nothing is padded out with nulls or empty entries.

## 3. What you can safely edit — and what happens if you don't

| JSON location | Safe to edit? | Effect when changed |
|---|---|---|
| `qualifiers[].id`, `elements[].id` | **No — never** | These are the only way changes get matched to the right place in the file. Change one and your edit (and every attribute under it) is silently skipped as "not found." |
| `qualifiers[].name` | Yes | Renames the qualifier (e.g. a diagram page's title). |
| `qualifiers[].system` | No effect either way | Read-only; ignored on import. |
| `elements[].name` | Yes | Renames the element (mirrors into the file's `ELEMENT_NAME` column, and into the `Name` attribute if one exists on that qualifier — you don't need to also edit `attributes.Name` separately, though doing so is fine too and takes priority if both are present). |
| `attributes.<X>` where the value is a **plain string** | **Yes — this is almost always what you're redacting** | e.g. `"Name"`, `F_AUTHOR`, `F_STATUS.OTHER_NAME`, `F_PROJECT_PREFERENCES.DEFINITION`/`PROJECT_AUTOR`, formula text, etc. |
| `attributes.<X>` where the value is a **number or boolean** | Technically yes, but don't unless you have a specific reason to | Positions, sizes, colors (packed signed ints, not RGB triples — see §5), font size/style, status codes, type codes. Redacting text should never require touching these. |
| `attributes.<X>` where the value is an **object** (`struct`-mode attribute, e.g. `F_BOUNDS`, `F_FONT`, `F_STATUS`, `F_PROJECT_PREFERENCES`) | Edit the individual string fields inside it | You may send back a partial object with just the field(s) you changed, or the whole object unchanged except for your edit — both work, since import merges by field. |
| `attributes.<X>` where the value is an **array of objects** (`list`-mode attribute) | **No — always ignored** | e.g. links/hierarchical/element-list attributes. These show up in the dump for visibility but importing never touches them (warned, not applied). If one of these needs redacting, that has to be done through the app's Raw Tables tab, not this JSON flow. |
| `attributes.<X>` equal to `{"__bytes_len__": N}` | **No — always ignored, and there is nothing to redact here anyway** | This is a placeholder for binary/file/rich-text content (icons, attachments, the `Description` HTML field, cached render data). **The dump never contains the actual bytes/text**, only their length, so if sensitive content lives in one of these fields, this JSON workflow cannot see it or redact it — you must flag it for the user to handle separately (the GUI's attribute editor has an "Edit as text…" button for `Description`/HTML fields specifically). Never delete this placeholder key thinking it clears the field; it does nothing. |
| An attribute simply **absent** from `attributes` | N/A | Means it has no value set in the file. Don't add it — new keys are not created by import. |

## 4. Type discipline

`apply_json_dump()` compares your new value to the current one with a
plain equality check, and writes it back using the same type you gave it.
To avoid warnings or, worse, writing the wrong kind of value into the file:

- **Keep the JSON type exactly as you found it.** A number stays a JSON
  number (`12`, `40.0`), not a quoted string (`"12"`). A boolean stays
  `true`/`false`, not `"true"`. Only strings should become different
  strings.
- **Don't reformat numbers you're not changing** (e.g. don't turn `40.0`
  into `40` or `40.00`) — unnecessary, and on a `struct` field it can
  trigger a spurious value-changed write for a field you didn't mean to
  touch. Simplest safe policy: **only rewrite the exact substrings/values
  you're redacting; leave every other byte of the JSON alone.**
- **Never change a key name** (`"Name"` must stay `"Name"`, `"attr_42"`
  must stay `"attr_42"` — the latter encodes an attribute id, not an
  arbitrary label).
- **Output must be syntactically valid JSON.** It's parsed strictly
  (`json.loads`); a trailing comma or unescaped quote fails the whole
  import with nothing applied.

## 5. Things that look sensitive-adjacent but aren't text to redact

- **Colors** (`F_BACKGROUND`, `F_FOREGROUND`, any `IDEF0.Color` attribute):
  a single signed 32-bit integer (packed ARGB, e.g. `-16711936` = opaque
  green), not an RGB string. Leave these numbers alone.
- **Positions/sizes** (`F_BOUNDS.X/Y/WIDTH/HEIGHT`): floats, geometry only.
- **Status/type codes** (`F_STATUS.TYPE`, `F_TYPE`, `F_FONT.STYLE`): small
  integers with fixed meanings (see `RAMUS_RSF_FORMAT.md` §8), not
  freeform data.
- **`attr_<N>` keys**: `<N>` is a numeric attribute id, not a redactable
  value — leave the key text itself untouched, only edit its value (if
  that value is itself a redactable string).

## 6. Attribute-shape cheat sheet

What you'll see in the dump, by the attribute's underlying storage mode
(`rsf_model.TYPE_MAP`), and whether import will act on your edit:

| Mode | Looks like in JSON | Editable via this workflow? |
|---|---|---|
| `scalar` | A plain string / number / boolean | Yes (if it's a string you're redacting) |
| `struct` | A JSON object of `{COLUMN: value}` | Yes, per string-valued field inside it |
| `list` | A JSON array of row objects | **No, always ignored** |
| `stream` (file/HTML text) | `{"__bytes_len__": N}`, or absent if unset | **No, always ignored** — real content isn't in the dump |
| any value that happens to be binary, even inside an otherwise-editable `scalar`/`struct` attribute (e.g. an icon's image bytes) | `{"__bytes_len__": N}` in that spot | **No, always ignored** — other string fields in the same struct are still editable |
| an attribute type with no entry in `TYPE_MAP` at all (e.g. some arrow/sector plumbing) | **Doesn't appear in the dump at all** | N/A — invisible to this workflow; use the Raw Tables tab in the GUI |

## 7. Worked example

**Input** (`dump.json`, one element with several kinds of sensitive text):

```json
{
  "qualifiers": [
    {
      "id": 9,
      "name": "Enterprise activity",
      "system": false,
      "elements": [
        {
          "id": 80,
          "name": "Alice Johnson - Account Review",
          "attributes": {
            "Name": "Alice Johnson - Account Review",
            "F_AUTHOR": "alice.johnson@example.com",
            "F_BOUNDS": {"X": 40.0, "Y": 40.0, "WIDTH": 140.0, "HEIGHT": 80.0},
            "F_BACKGROUND": -16711936,
            "F_STATUS": {"TYPE": 0, "OTHER_NAME": "approved by phone, SSN on file 123-45-6789"},
            "F_TYPE": 3
          }
        }
      ]
    }
  ]
}
```

**Correct redaction** — only the string values changed, everything else
(ids, numbers, structure, keys) byte-identical:

```json
{
  "qualifiers": [
    {
      "id": 9,
      "name": "Enterprise activity",
      "system": false,
      "elements": [
        {
          "id": 80,
          "name": "[REDACTED NAME] - Account Review",
          "attributes": {
            "Name": "[REDACTED NAME] - Account Review",
            "F_AUTHOR": "[REDACTED EMAIL]",
            "F_BOUNDS": {"X": 40.0, "Y": 40.0, "WIDTH": 140.0, "HEIGHT": 80.0},
            "F_BACKGROUND": -16711936,
            "F_STATUS": {"TYPE": 0, "OTHER_NAME": "approved by phone, [REDACTED SSN]"},
            "F_TYPE": 3
          }
        }
      ]
    }
  ]
}
```

Applying this patches exactly two attribute values plus the element name
(`Name` is deduplicated with the top-level `name` automatically, so this
counts as `Name` + `F_AUTHOR` + `F_STATUS` = 3 values updated on 1 element
— see §1's rule about `name` vs `attributes.Name`), and reports zero
warnings.

**What would go wrong with a naive approach** — deleting the element
instead of redacting its fields:

```json
{ "qualifiers": [ { "id": 9, "name": "Enterprise activity", "system": false, "elements": [] } ] }
```

This does **not** delete element 80 from the file. Element 80, with all
its original unredacted text, remains exactly as it was — the import
simply has nothing to say about an id it wasn't told about. If the goal
was to scrub Alice's data from the file, this leaves it fully intact. Use
the first form.

## 8. Checklist before handing back your redacted JSON

- [ ] Output is valid JSON, same top-level `{"qualifiers": [...]}` shape.
- [ ] No `id` field anywhere was changed.
- [ ] No qualifier/element/attribute block was added or removed — only
      values inside existing blocks were changed.
- [ ] Only string values were rewritten; every number, boolean, and
      `{"__bytes_len__": ...}` placeholder is untouched, exact type and
      all.
- [ ] `"system"` flags, `list`-mode arrays, and everything under a
      `{"__bytes_len__": ...}` placeholder were left alone (call these out
      to the user separately if they contain something that needs
      redacting — this workflow cannot reach them).
- [ ] Key names (`"Name"`, `"F_BOUNDS"`, `"attr_42"`, etc.) are unchanged.
- [ ] Nothing outside what you were actually asked to redact was modified
      — a smaller, more surgical diff is easier for the user to trust and
      to re-run if something needs adjusting.

## 9. Handing it back

Tell the user to re-import with either:

```sh
ramus-rsf-cli import-json ORIGINAL.rsf redacted-dump.json OUTPUT.rsf
```

or, in the GUI, **JSON Dump tab → Import from file…** (pick your redacted
JSON file) followed by **File → Save As…**. Either path reports a summary
— counts of what changed, plus any warnings for entries it couldn't apply
(wrong/unknown id, list/stream attribute, type mismatch) — worth relaying
back so the user can confirm nothing they expected to change was silently
skipped.
