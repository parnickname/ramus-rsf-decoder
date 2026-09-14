# Формат файла Ramus `.rsf` — заметки реверс-инжиниринга и набор инструментов

**Изученный исходный код:** [`Vitaliy-Yakovchuk/ramus`](https://github.com/Vitaliy-Yakovchuk/ramus)
(GPL-3.0), Java-моделировщик бизнес-процессов IDEF0/DFD. `.rsf` — его
родной формат сохранения.

**Метод:** весь репозиторий был склонирован и прочитан (а не угадан по
бинарникам) — в частности, `core/.../FileIEngineImpl.java`,
`core/.../TableToXML.java` / `XMLToTable.java` (точный код
экспорта/импорта), `common/.../persistent/*` (мини-ORM на аннотациях),
файлы SQL-схемы в `database-storage/.../*.sql`, и
`idef0-core/idef0-common` (специфичные для IDEF0 типы атрибутов). Каждое
утверждение ниже затем было **перепроверено на трёх реальных файлах
`.rsf`, входящих в сам репозиторий**
(`dest/doc/en/Enterprise activity.rsf`, `dest/doc/ru/Model example.rsf`,
`dest/doc/ru/Пример модели.rsf`) путём их распаковки и изучения реального
XML. Там, где что-то выведено из исходного кода, но *не* подтверждено на
реальном файле или запущенном Ramus, это явно помечено.

Сопутствующий набор инструментов на Python (`rsf_core.py`, `rsf_model.py`,
`rsf_cli.py`) поставляется в виде отдельных файлов и реализует всё
описанное здесь. Он был протестирован циклическим сохранением/загрузкой и
редактированием реальных образцов файлов (подробности в
[разделе «Проверка»](#14-проверка)).

---

## Оглавление

1. [Общая картина](#1-общая-картина)
2. [Формат контейнера: это ZIP](#2-формат-контейнера-это-zip)
3. [Обобщённый XML-формат таблицы](#3-обобщённый-xml-формат-таблицы)
4. [Правила кодирования значений по SQL-типам](#4-правила-кодирования-значений-по-sql-типам)
5. [Модель данных: самоописывающаяся EAV-база данных](#5-модель-данных-самоописывающаяся-eav-база-данных)
6. [Полный справочник таблиц](#6-полный-справочник-таблиц)
7. [Выделение ID и почему внешние правки безопасны](#7-выделение-id-и-почему-внешние-правки-безопасны)
8. [Набор атрибутов «функционального блока» IDEF0](#8-набор-атрибутов-функционального-блока-idef0)
9. [Иерархия декомпозиции (изучена частично)](#9-иерархия-декомпозиции-изучена-частично)
10. [Отрисовка новых стрелок (секторы / потоки / точки пересечения)](#10-отрисовка-новых-стрелок-секторы--потоки--точки-пересечения)
11. [Потоки файловых атрибутов / HTML-текста](#11-потоки-файловых-атрибутов--html-текста)
12. [Совместимость со старым форматом (ветки/версионирование)](#12-совместимость-со-старым-форматом-веткиверсионирование)
13. [Набор инструментов](#13-набор-инструментов)
14. [Проверка](#14-проверка)
15. [Перекрёстные ссылки на исходные файлы](#15-перекрёстные-ссылки-на-исходные-файлы)

---

## 1. Общая картина

Слой хранения Ramus (`core`, `database-storage`, `common/persistent`) —
это собственный маленький встроенный фреймворк реляционной базы данных.
Во время работы он хранит всё в настоящей SQL-базе данных (изначально в
стиле HSQLDB); файл `.rsf` — это просто **дамп каждой таблицы этой базы
данных в виде XML, упакованный в ZIP**, плюс горстка «сырых» бинарных
«потоков» (вложения, состояние GUI, настройки печати), хранящихся по
собственным путям внутри того же архива.

Важно, что формат дампа **самоописывающийся**: XML каждой таблицы несёт
собственные имена столбцов и SQL-типы прямо внутри себя, а *набор
существующих таблиц* сам перечислен в одной из таблиц (`persistents`).
Именно это делает формат пригодным для чтения и записи извне — не нужен
файл схемы, схему можно узнать прямо из самого файла.

Реальные данные приложения (функциональные блоки IDEF0, элементы DFD,
стрелки, позиции, цвета, шрифты, заметки — всё) хранятся как обобщённая
модель **«сущность–атрибут–значение» (Entity–Attribute–Value, EAV)**:
`qualifiers` — это примерно «классы», `elements` — «экземпляры» одного
квалификатора, `attributes` — «поля», и каждый *тип* атрибута (Text,
Long, Rectangle, Color, Font, ...) имеет собственную физическую таблицу
значений с ключом `(attribute_id, element_id)`.

## 2. Формат контейнера: это ZIP

Откройте любой `.rsf` обычным ZIP-инструментом (`unzip`,
`zipfile.ZipFile`, 7-Zip и т. д.) — никаких специальных библиотек не
нужно. Структура (по реальному образцу на 69 КБ, 38 таблиц / 25 прочих
файлов):

```
data/
  application_metadata.xml     Java Properties XML: имя/версия приложения, список плагинов
  sequences.xml                Java Properties XML: пара пользовательских счётчиков ID
  application_preferencies.xml настройки приложения в виде «ключ/значение»
  qualifiers.xml                <-- EAV-таблицы (см. §6)
  elements.xml
  attributes.xml
  qualifiers_attributes.xml
  persistents.xml
  persistent_fields.xml
  streams.xml
  formulas.xml
  formula_dependences.xml
  Core/
    attribute_texts.xml         <-- по одному файлу на пару (плагин, тип атрибута)
    attribute_longs.xml
    attribute_doubles.xml
    attribute_dates.xml
    attribute_hierarchicals.xml
    attribute_other_elements.xml
    ... (полный список реально встреченных — в §6)
  IDEF0/
    attribute_rectangles.xml
    attribute_colors.xml
    attribute_fonts.xml
    attribute_statuses.xml
    ...
  Eval/
    attribute_functions.xml
elements/<element_id>/<attribute_id>/<plugin>/<file>   сырые байты вложений/HTML (см. §11)
properties/...             разные настройки приложения (размер страницы, опции просмотра IDEF0)
user/...                   состояние, относящееся только к GUI: расположение окон, ширина
                            столбцов таблиц, настройки проверки орфографии — никогда не трогайте
                            это, Ramus регенерирует это и не проверяет строго
```

Именно такую структуру производит
`FileIEngineImpl.writeToStream()` / `saveToFileNotCloseFile()`
(`core/src/main/java/com/ramussoft/core/impl/FileIEngineImpl.java`), и
её же читает обратно `FileIEngineImpl.open()` в том же файле. Загрузка
**терпима к отсутствующим записям**: `loadTable()` просто молча
пропускает таблицу, если её записи нет в zip
(`InputStream stream = zFile.getInputStream(ze); if (stream != null) ...`).
Эта терпимость используется по всему документу (например, в §12), чтобы
держать генерируемые файлы минимальными.

## 3. Обобщённый XML-формат таблицы

Каждый файл `data/**/*.xml`, **кроме** `application_metadata.xml` и
`sequences.xml` (это обычный `java.util.Properties` XML, см. ниже), имеет
именно такую форму, которую производит
`core/.../impl/TableToXML.java::store()` и потребляет
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

Правила (проверены на реальных файлах):

- `<fields>` объявляет каждый столбец **только для этого файла**, с
  небольшим позиционным `id` (это не то же самое, что данные какой-либо
  строки!), используемым исключительно для сопоставления `<f id="...">`
  внутри `<row>` с именем столбца. Порядок столбцов в `<fields>` **не
  обязан** совпадать с физическим порядком столбцов в БД — сопоставление
  происходит по **имени** (без учёта регистра) при импорте, поэтому тот,
  кто пишет файл, волен объявлять столбцы в любом порядке, пока `id`,
  используемые в `<fields>` и в `<row><f id="...">`, согласованы друг с
  другом.
- `<f id="N">значение</f>` строки присутствует **только если базовое
  SQL-значение не `NULL`**. Присутствующая, но пустая строка записывается
  как самозакрывающийся тег: `<f id="1"/>`. **Полностью отсутствующий
  `<f id="N">` для этой строки означает SQL `NULL`.** Это различие важно,
  и набор инструментов его сохраняет (сигнальное значение `rsf_core.NULL`
  в отличие от `""`).
- `prefix="ramus_"` — это префикс имён таблиц БД, который Ramus
  использует внутренне; он записывается в XML, но фактически не нужен для
  разбора файла (физический префикс никогда не встречается в *путях*
  внутри zip, только в этом атрибуте, который набор инструментов сохраняет
  дословно, но иначе игнорирует).
- `generate-time` — информационное поле (формат Java
  `new Date().toString()`, зависящий от локали/часового пояса) —
  косметическое, безопасно оставлять устаревшим или регенерировать.

### `application_metadata.xml` и `sequences.xml`

Эти два файла — стандартный `java.util.Properties` XML
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
... по одной записи на плагин ...
</properties>
```

- `FileOpenMinimumVersion` сверяется с версией запущенного приложения при
  открытии (`FileIEngineImpl.checkFileVersion()`); низкое значение вроде
  `1.0` максимально совместимо и безопасно для генерируемых файлов.
- Список `Plugin_N` сверяется с набором плагинов, реально загруженных в
  *запущенном* приложении (`FileVersionException`, если перечисленного
  плагина не хватает) — поэтому не перечисляйте несуществующие плагины.
  Придерживаться стандартного набора плагинов `Core` + `IDEF0` (+`Eval`,
  `Autochange`, если используются формулы), как в реальных образцах
  файлов, безопасно.
- `sequences.xml` в образцах файлов хранил только **один**
  пользовательский счётчик (`crosspoint_sequence`). Это *не* то место,
  где живут счётчики id элементов/квалификаторов/атрибутов — см. §7.

## 4. Правила кодирования значений по SQL-типам

`type="..."` у каждого `<field>` управляет кодированием, в точности
повторяя классы `Converter` из `TableToXML` (все сравнения регистро-
независимы):

| объявленный `type`                    | Python/смысл                          | Кодирование в тексте `<f>` |
|---|---|---|
| `BIGINT`, `INTEGER`, `int4`, `LONG`, `int8` | целое число | обычное десятичное, например `144` |
| `BOOLEAN`, `bool`                  | логическое значение | **`TRUE` / `FALSE`** (в верхнем регистре) |
| `DOUBLE`, `float8`                 | число с плавающей точкой   | Java `Double.toString()`, например `80.0`, `-124.5` |
| `CLOB`, `CHAR`, `TEXT`, `bpchar`   | строка  | обычный текст, экранированный по правилам XML |
| `TIMESTAMP`                        | дата/время | см. ниже |
| `BLOB`, `VARBINARY`, `bytea`       | байты   | нестандартный hex, см. ниже |

**Логические значения записываются как `TRUE`/`FALSE` в верхнем
регистре**, а *не* `true`/`false`. На первый взгляд это похоже на баг —
собственный `BoolConverter` в `TableToXML` вызывает обычный
`Object.toString()` на упакованном `java.lang.Boolean`, для которого JDK
всегда определяет строчные буквы — но фактическая диспетчеризация по типу
специально обрабатывает только столбцы, чьё имя JDBC-типа точно равно
`"bool"` (`meta.getColumnTypeName(...).equalsIgnoreCase("bool")`);
настоящие булевы столбцы сообщают о себе как `"BOOLEAN"`, что **не
совпадает**, поэтому они молча попадают в обобщённый строковый
конвертер, который вызывает `ResultSet.getString()` на булевом столбце —
и именно это фактически производит `"TRUE"`/`"FALSE"`. Подтверждено
побайтово на реальных файлах. Читатель в `XMLToTable`
(`Boolean.parseBoolean(...)`) в любом случае регистронезависим, поэтому на
это безопасно полагаться, но набор инструментов **пишет в верхнем
регистре**, следуя соглашению.

**Байтовые массивы** (`BLOB`/`VARBINARY`/`bytea` — значки, blob'ы
«визуальных атрибутов» стрелок, `VisualData`) используют самодельную
hex-схему из `TableToXML.ByteAConverter` / `XMLToTable.ByteAConverter`:

```java
// кодирование: для каждого знакового байта b пишем hex от (b + 128)
int j = bytes[i]; j += 128; retString.append(digits[j]);   // digits[0..255] = "00".."FF"
// декодирование: в обратном порядке
bs[i/2] = (byte) (val - 128);
```

Поскольку `128 == 0x80`, «прибавить 128 по модулю 256» и «инвертировать
старший бит» — это одна и та же операция, поэтому это ровно
`hex(байт XOR 0x80)` / `hex⁻¹(...) XOR 0x80`. Реализовано в наборе
инструментов как `rsf_core.bytes_to_rsf_hex` / `rsf_core.rsf_hex_to_bytes`.
**Это не стандартное hex-кодирование** — если скормить эти данные
обычному hex-инструменту, он молча выдаст мусор.

**Временны́е метки** используют
`DateFormat.getDateTimeInstance(SHORT, SHORT, Locale.ENGLISH)`, что на
JDK, под который приложение собиралось/тестировалось (данные локали
старого стиля «COMPAT» до JDK9), отображается как `9/3/09 5:23 PM` — без
запятой, двузначный год, без ведущих нулей, 12-часовой формат.
**Подтверждено на реальных данных файлов.** Примечание: JDK 9+ переключил
провайдер данных локали по умолчанию на CLDR, чей короткий шаблон для
`en` *добавляет запятую* (`9/3/09, 5:23 PM`) — так что файлы, записанные
сборкой Ramus, работающей на более новом JDK, могут здесь отличаться.
Читатель набора инструментов принимает обе формы; его писатель выдаёт
устаревшую форму без запятой, соответствующую каждому реально изученному
образцу файла.

## 5. Модель данных: самоописывающаяся EAV-база данных

Основу составляют четыре таблицы (`database-storage/.../database.sql`):

```sql
qualifiers(QUALIFIER_ID, QUALIFIER_NAME, QUALIFIER_SYSTEM, ATTRIBUTE_FOR_NAME)
elements(ELEMENT_ID, ELEMENT_NAME, QUALIFIER_ID)
attributes(ATTRIBUTE_ID, ATTRIBUTE_NAME, ATTRIBUTE_TYPE_PLUGIN_NAME,
           ATTRIBUTE_TYPE_NAME, ATTRIBUTE_TYPE_COMPARABLE, ATTRIBUTE_SYSTEM)
qualifiers_attributes(QUALIFIER_ID, ATTRIBUTE_ID, ATTRIBUTE_SYSTEM, ATTRIBUTE_POSITION)
```

Читайте их так: *«`qualifier` — это класс; `element` — экземпляр одного
квалификатора; `qualifiers_attributes` говорит, какие `attribute`
(поля) прикреплены к какому квалификатору (классу)»*. Одна страница
диаграммы IDEF0 — это один квалификатор; каждый функциональный блок,
нарисованный на ней — один элемент под этим квалификатором.

**Где живут реальные значения?** Не в `elements` (в этой таблице есть
только ID, отображаемое имя и владеющий квалификатор). У каждого *типа
атрибута* (`(ATTRIBUTE_TYPE_PLUGIN_NAME, ATTRIBUTE_TYPE_NAME)`, например
`("Core","Text")`, `("IDEF0","FRectangle")`) есть **своя собственная
физическая таблица** с ключом `(ATTRIBUTE_ID, ELEMENT_ID)`. Это
сопоставление зарегистрировано ещё в двух самоописывающихся таблицах:

```sql
persistents(PERSISTENT_ID, TABLE_NAME, TABLE_TYPE, CLASS_NAME, PLUGIN_NAME, TYPE_NAME, PERSISTENT_EXISTS)
persistent_fields(PERSISTENT_FIELD_ID, PERSISTENT_ID, FIELD_NAME, FIELD_DATABASE_NAME,
                   FIELD_ID, FIELD_EXISTS, FIELD_TYPE, FIELD_AUTOSET, FIELD_PRIMARY)
```

например, реальная строка `persistents`:

```
PERSISTENT_ID=4  TABLE_NAME=ramus_attribute_texts  CLASS_NAME=com.ramussoft.core.attribute.simple.TextPersistent
                 PLUGIN_NAME=Core  TYPE_NAME=Text
```

...то есть: каждый атрибут, чей `(ATTRIBUTE_TYPE_PLUGIN_NAME,
ATTRIBUTE_TYPE_NAME) == ("Core","Text")`, хранит своё значение как строку
в `data/Core/attribute_texts.xml`. **Это означает, что файл сам
рассказывает вам свою схему** — этот документ вам вообще не нужен, чтобы
сделать *обобщённое* чтение любого файла `.rsf` (слой `rsf_core.py`
набора инструментов делает именно это, с нулевым жёстко закодированным
знанием об IDEF0). Этот документ и `TYPE_MAP` в `rsf_model.py`
существуют для того, чтобы избавить вас от *повторного выведения* того,
какая таблица/столбцы соответствуют какому типу атрибута, и дать типовые
хелперы get/set вместо сырых словарей строк.

Форма строки каждой физической таблицы значений была прочитана из
соответствующего Java-класса с аннотацией `@Table` в `common/persistent/`
и `core-simple-attributes` / `idef0-core`, например:

```java
@Table(name = "rectangles")
public class FRectanglePersistent extends AbstractPersistent {
    @Double(id = 2) double x;
    @Double(id = 3) double y;
    @Double(id = 4) double width;
    @Double(id = 5) double height;
}
```

Сам `AbstractPersistent` предоставляет столбцы ключа
`(attribute_id, element_id)`, которые есть у каждой таблицы значений.
Имя физической таблицы — `ramus_attribute_<name>` → путь в zip
`data/<plugin>/attribute_<name>.xml`.

**Кардинальность строк на `(attribute_id, element_id)` различается по
типу:** у большинства типов ровно **одна строка** (`ONE_TO_ONE`, значение
аннотации по умолчанию) — у функционального блока ровно один
прямоугольник, один цвет, один статус. У нескольких типов явно указано
`ONE_TO_MANY` (`OtherElementPersistent`, `HierarchicalPersistent`), либо
есть дополнительные столбцы первичного ключа сверх
`(attribute_id, element_id)` (`SectorPointPersistent` добавляет
`x_ordinate_id, y_ordinate_id`) — у них может быть **много** строк с
одним и тем же `(attribute_id, element_id)`, например все точки маршрута
одной стрелки. `TYPE_MAP` набора инструментов помечает каждый тип как
`'scalar'` (единственный столбец значения), `'struct'` (одна строка,
несколько именованных столбцов) или `'list'` (любое количество строк)
соответственно.

## 6. Полный справочник таблиц

Каждая таблица ниже встречалась хотя бы в одном из трёх реальных образцов
файлов (в основном в английском образце «Enterprise activity»); столбцы
приведены точно в том виде, в каком они объявлены в собственных
`<fields>` этого файла.

### Основные таблицы (не специфичные для типа атрибута)

| путь в zip | столбцы | примечания |
|---|---|---|
| `data/qualifiers.xml` | QUALIFIER_ID, QUALIFIER_NAME, QUALIFIER_SYSTEM, ATTRIBUTE_FOR_NAME | ATTRIBUTE_FOR_NAME указывает на атрибут «Name», используемый для подписи элементов этого квалификатора |
| `data/elements.xml` | ELEMENT_ID, ELEMENT_NAME, QUALIFIER_ID | |
| `data/attributes.xml` | ATTRIBUTE_ID, ATTRIBUTE_NAME, ATTRIBUTE_TYPE_PLUGIN_NAME, ATTRIBUTE_TYPE_NAME, ATTRIBUTE_TYPE_COMPARABLE, ATTRIBUTE_SYSTEM | |
| `data/qualifiers_attributes.xml` | QUALIFIER_ID, ATTRIBUTE_ID, ATTRIBUTE_SYSTEM, ATTRIBUTE_POSITION | какие атрибуты есть у какого квалификатора и порядок их отображения |
| `data/persistents.xml` | PERSISTENT_ID, TABLE_NAME, TABLE_TYPE, CLASS_NAME, PLUGIN_NAME, TYPE_NAME, PERSISTENT_EXISTS | реестр каждой таблицы значений (см. §5) |
| `data/persistent_fields.xml` | PERSISTENT_FIELD_ID, PERSISTENT_ID, FIELD_NAME, FIELD_DATABASE_NAME, FIELD_ID, FIELD_EXISTS, FIELD_TYPE, FIELD_AUTOSET, FIELD_PRIMARY | реестр столбцов для каждой таблицы значений |
| `data/application_preferencies.xml` | OPTION_KEY, OPTION_VALUE | плоские настройки приложения |
| `data/streams.xml` | STREAM_ID | индекс каждого сырого пути вложения, используемого где-либо ещё в архиве (см. §11) |
| `data/formulas.xml` | ELEMENT_ID, ATTRIBUTE_ID, AUTORECALCULATE, FORMULA | текст формулы плагина Eval, с ключом на ту ячейку, к которой она прикреплена |
| `data/formula_dependences.xml` | SOURCE_ELEMENT_ID, SOURCE_ATTRIBUTE_ID, ELEMENT_ID, ATTRIBUTE_ID | рёбра графа зависимостей формул |

Более новые файлы (2.0+, по `update4.sql`) могут дополнительно содержать:
`data/branches.xml`, `data/attributes_history.xml`,
`data/qualifiers_history.xml`, `data/attributes_data_metadata.xml`,
`data/formulas_data_metadata.xml`,
`data/formula_dependences_data_metadata.xml` — функцию ветвления модели
(«сравнение/слияние версий модели»). **Ни одной из них не было ни в одном
из трёх реальных образцов файлов** (все они старше этой функции), и,
согласно §12, они полностью опциональны для файлов, нацеленных на одну
ветку/ствол.

### Таблицы значений по типу атрибута (плагин Core)

| путь в zip | столбцы | Java-класс | кардинальность |
|---|---|---|---|
| `data/Core/attribute_texts.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(CLOB) | `TextPersistent` | одна |
| `data/Core/attribute_longs.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(BIGINT) | `LongPersistent` | одна |
| `data/Core/attribute_doubles.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(DOUBLE) | `DoublePersistent` | одна |
| `data/Core/attribute_dates.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(TIMESTAMP) | `DatePersistent` | одна |
| `data/Core/attribute_currencies.xml` | ATTRIBUTE_ID, ELEMENT_ID, VALUE(DOUBLE) | `CurrencyPersistent` | одна |
| `data/Core/attribute_booleans.xml`* | ATTRIBUTE_ID, ELEMENT_ID, VALUE(INTEGER 0/1) | `BooleanPersistent` | одна |
| `data/Core/attribute_variants.xml` | ATTRIBUTE_ID, ELEMENT_ID, VARIANT_ID(BIGINT) | `VariantPersistent` | одна |
| `data/Core/attribute_variant_properties.xml` | ATTRIBUTE, POSITION, VALUE, VARIANT_ID | `VariantPropertyPersistent` | list — список вариантов, на котором держится атрибут типа Variant |
| `data/Core/attribute_icons.xml` | ATTRIBUTE_ID, ELEMENT_ID, ICON(байты), NAME | `IconPersistent` | одна |
| `data/Core/attribute_attached_files.xml` | ATTRIBUTE_ID, ELEMENT_ID, LAST_MODIFIED_TIME, NAME, PATH, UPLOAD_TIME | `FilePersistent` (только метаданные — байты файла — это поток, см. §11) | одна |
| `data/Core/attribute_other_elements.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_ELEMENT(BIGINT) | `OtherElementPersistent` | **список** (ONE_TO_MANY) |
| `data/Core/attribute_other_element_properties.xml` | ATTRIBUTE, QUALIFIER, QUALIFIER_ATTRIBUTE | `OtherElementPropertyPersistent` | конфигурация на квалификатор, а не на элемент |
| `data/Core/attribute_hierarchicals.xml` | ATTRIBUTE_ID, ELEMENT_ID, ICON_ID, PARENT_ELEMENT_ID, PREVIOUS_ELEMENT_ID | `HierarchicalPersistent` | **список** (ONE_TO_MANY); сигнальное значение `-1`/`0` = нет родителя/нет предыдущего соседа — используется для построения UI дерева/порядка элементов квалификатора |
| `data/Core/attribute_element_lists.xml` | ATTRIBUTE_ID, ELEMENT1_ID, ELEMENT2_ID | `ElementListPersistent` | таблица рёбер «многие-ко-многим» (+ опциональный текст CONNECTION_TYPE) |
| `data/Core/attribute_element_list_properties.xml` | ATTRIBUTE_ID, QUALIFIER1, QUALIFIER2 | `ElementListPropertyPersistent` | какие пары квалификаторов может соединять данный атрибут типа ElementList |

\* не встречено ни в одном изученном образце (не оказалось использованного
атрибута типа Boolean), но выведено напрямую из `BooleanPersistent.java`;
имена столбцов могут потребовать подтверждения «на лету», если вы на них
полагаетесь.

`Core.HTMLText` (форматированные текстовые поля «Description») и
`Core.File` (произвольные вложения) — это **вообще не** строки EAV — см.
§11.

### Таблицы значений по типу атрибута (плагин IDEF0)

| путь в zip | столбцы | Java-класс | кардинальность |
|---|---|---|---|
| `data/IDEF0/attribute_rectangles.xml` | ATTRIBUTE_ID, ELEMENT_ID, HEIGHT, WIDTH, X, Y (все DOUBLE) | `FRectanglePersistent` | одна — позиция/размер блока |
| `data/IDEF0/attribute_colors.xml` | ATTRIBUTE_ID, ELEMENT_ID, COLOR(INTEGER) | `ColorPersistent` | одна — упакованный ARGB, см. §8 |
| `data/IDEF0/attribute_fonts.xml` | ATTRIBUTE_ID, ELEMENT_ID, NAME(CLOB), SIZE(INTEGER), STYLE(INTEGER) | `FontPersistent` | одна — STYLE — это биты стиля AWT `Font` (0=обычный,1=жирный,2=курсив,3=жирный+курсив) |
| `data/IDEF0/attribute_statuses.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_NAME(CLOB), TYPE(INTEGER) | `StatusPersistent` | одна |
| `data/IDEF0/attribute_function_types.xml` | ATTRIBUTE_ID, ELEMENT_ID, TYPE(INTEGER) | `FunctionTypePersistent` | одна — именно это использует `F_TYPE` |
| `data/IDEF0/attribute_function_ouners.xml` | ATTRIBUTE_ID, ELEMENT_ID, OUNER_ID(BIGINT) | `FunctionOunerPersistent` | одна (`OUNER_ID`, да, так в оригинальном коде — опечатка сохранена) |
| `data/IDEF0/attribute_decomposition_types.xml` | ATTRIBUTE_ID, ELEMENT_ID, TYPE(INTEGER) | `DecompositionTypePersistent` | одна |
| `data/IDEF0/attribute_visual_datas.xml` | ATTRIBUTE_ID, ELEMENT_ID, DATA(байты) | `VisualDataPersisitent` | одна — непрозрачный кэшированный blob отрисовки, безопасно оставлять неустановленным (F_VISUAL_DATA используется только в одном устаревшем пути кода, `NFunction.PROPERTIES`) |
| `data/IDEF0/attribute_any_to_any_elements.xml` | ATTRIBUTE_ID, ELEMENT_ID, OTHER_ELEMENT(BIGINT) | `AnyToAnyPersistent` | список |
| `data/IDEF0/attribute_model_preferences.xml` | ATTRIBUTE_ID, CHANGE_DATE, CREATE_DATE, DEFINITION, ELEMENT_ID, PROJECT_AUTOR, PROJECT_NAME, USED_AT | `IDEF0ModelPreferencesPersistent` | одна — поля информации о модели, показываемые в диалоге Ramus «Свойства модели» |
| `data/IDEF0/attribute_readers.xml` | ATTRIBUTE_ID, DATE, ELEMENT_ID, READER(CLOB) | `ReaderPersistent` | одна строка на запись рецензента, с дополнительным ключом каким-то образом — считать списком |
| `data/IDEF0/attribute_sectors.xml` | ALTERNATIVE_TEXT, ATTRIBUTE_ID, CREATE_POS, CREATE_STATE, ELEMENT_ID, SHOW_TEXT, VISUAL_ATTRIBUTES(байты)[, TEXT_ALIGMENT — в более новых файлах] | `SectorPersistent` | одна — см. §10, стрелки |
| `data/IDEF0/attribute_sector_borders.xml` | ATTRIBUTE_ID, BORDER_TYPE, CROSSPOINT, ELEMENT_ID, FUNCTION, FUNCTION_TYPE, TUNNEL_SOFT | `SectorBorderPersistent` | одна — см. §10 |
| `data/IDEF0/attribute_sector_points.xml`† | ATTRIBUTE_ID, ELEMENT_ID, X_ORDINATE_ID, Y_ORDINATE_ID, X_POSITION, Y_POSITION, POINT_TYPE, POSITION | `SectorPointPersistent` | **список**, дополнительные столбцы первичного ключа — см. §10 |
| `data/IDEF0/attribute_sector_properties.xml`† | ATTRIBUTE_ID, ELEMENT_ID, SHOW_TILDA, SHOW_TEXT, TRANSPARENT, TILDA_POS, TEXT_X, TEXT_Y, TEXT_WIDTH, TEXT_HIEGHT (да, опечатка) | `SectorPropertiesPersistent` | одна |

† не встречены в изученных образцах файлов (они старше этой таблицы /
никогда её не использовали); список столбцов выведен напрямую из
исходного кода Java.

### Другие встреченные плагины

| путь в zip | столбцы | примечания |
|---|---|---|
| `data/Eval/attribute_functions.xml` | ATTRIBUTE_ID, AUTOCHANGE, ELEMENT_ID, FUNCTION(CLOB), QUALIFIER_ATTRIBUTE_ID, QUALIFIER_TABLE_ATTRIBUTE_ID | конфигурация плагина формул на каждую ячейку |

## 7. Выделение ID и почему внешние правки безопасны

`ELEMENT_ID` / `QUALIFIER_ID` / `ATTRIBUTE_ID` — каждый со своим
независимым счётчиком. Во время работы Ramus использует настоящие
SQL-последовательности (`CREATE SEQUENCE ramus_elements_sequence START
1` и т. д.) — но **эти последовательности не входят в экспортированный
файл** и *не* восстанавливаются из `sequences.xml` (в этом файле живут
только два пользовательских счётчика плагина IDEF0,
`crosspoint_sequence`/`ordinates__sequence`; он не имеет никакого
отношения к ID элементов/квалификаторов/атрибутов).

Так как же Ramus избегает коллизий ID после загрузки файла, чьи ID были
вставлены напрямую (в обход последовательности) и далеко опережают
счётчик последовательности свежей БД (который каждый раз перезапускается
с 1)? Каждый путь создания синхронизируется на лету, например
`IEngineImpl.createElement()`:

```java
if (elementId == -1) {
    elementId = nextValue("elements_sequence");
    long id = template.queryForLong("SELECT MAX(ELEMENT_ID) FROM " + prefix + "elements;");
    while (id >= elementId) {
        elementId = template.nextVal(prefix + "elements_sequence");
    }
}
```

то есть он продолжает брать значения из последовательности, пока
значение не превысит текущий `MAX(id)` в таблице. **Практическое
следствие: любой инструмент (включая этот) может безопасно назначать
новые ID, беря `max(существующие id в этой таблице) + 1`.** Ramus
никогда впоследствии не выдаст коллизирующий ID, как бы далеко
«впереди» ни были ваши внешне назначенные ID.
`rsf_model.Model.new_element_id()` / `new_qualifier_id()` /
`new_attribute_id()` делают именно это.

(Это было проверено чтением исходного кода Java для `createElement`,
`createAttribute`, `createQualifier` — все три следуют идентичному
шаблону — а не запуском приложения; что *было* проверено
сквозным тестированием, см. [раздел «Проверка»](#14-проверка).)

## 8. Набор атрибутов «функционального блока» IDEF0

Всякий раз, когда квалификатор представляет контейнер функционального
блока IDEF0 (квалификатор «является страницей диаграммы»),
`IDEF0Plugin.checkIDEF0Attributes()` гарантирует, что у него есть именно
этот набор атрибутов (подтверждено на реальных данных файла — это
квалификатор 9, «Enterprise activity», корневая диаграмма, в английском
образце):

| ATTRIBUTE_NAME | plugin.type | значение | форма значения |
|---|---|---|---|
| `Name` | Core.Text | подпись блока (также отражается в `elements.ELEMENT_NAME`) | строка |
| `Description` | Core.HTMLText | форматированные текстовые заметки | поток, см. §11 |
| `F_VISUAL_DATA` | IDEF0.VisualData | непрозрачный кэш отрисовки | байты, можно опускать |
| `F_BACKGROUND` | IDEF0.Color | цвет заливки | упакованное целое ARGB, см. ниже |
| `F_FOREGROUND` | IDEF0.Color | цвет границы/текста | упакованное целое ARGB |
| `F_BOUNDS` | IDEF0.FRectangle | положение + размер на странице | числа с плавающей точкой `{X, Y, WIDTH, HEIGHT}` |
| `F_FONT` | IDEF0.Font | шрифт подписи | `{NAME, STYLE, SIZE}` |
| `F_STATUS` | IDEF0.Status | статус рецензирования/рабочего процесса | `{TYPE:int, OTHER_NAME:str}` |
| `F_TYPE` | IDEF0.Type | вид блока (function/`3` встречается на каждом обычном блоке в образцах; остальные значения относятся к DFD — здесь не перечислены) | int |
| `F_OUNER_ID` | IDEF0.OunerId | (да, опечатка в оригинале) какая-то ссылка на владельца — прослежено не полностью, см. §9 | long |
| `F_DECOMPOSITION_TYPE` | IDEF0.DecompositionType | IDEF0 против DFD против ... для дочерней диаграммы этого блока | int |
| `F_AUTHOR` | Core.Text | | строка |
| `F_CREATE_DATE` / `F_REV_DATE` / `F_SYSTEM_REV_DATE` | Core.Date | | строка временной метки |
| `F_LINK` | Core.Long | перекрёстная ссылка на другой элемент (термин глоссария и т. п.) | long |
| `F_SECTOR_FUNCTION`, `F_SECTOR_STREAM`, `F_STREAM_NAME`, `F_SECTOR_ATTRIBUTE`, `F_SECTOR_BORDER_START`, `F_SECTOR_BORDER_END`, `F_STREAM_ADDED` | разные | внутренняя механика маршрутизации стрелок | см. §10 |
| `F_BASE_FUNCTION_QUALIFIER_ID` | Core.Long | **фактически прикреплён только к системному квалификатору `F_BASE_FUNCTIONS`**, а не к обычным блокам — см. §9 | long |
| `F_PROJECT_PREFERENCES` | IDEF0.ProjectPreferences | метаданные модели (имеют смысл только на записи-корне модели) | struct |

**Кодирование цвета**: `java.awt.Color.getRGB()` = упакованное
`0xAARRGGBB`, переинтерпретированное как **знаковое 32-битное целое**.
Чистый непрозрачный зелёный (`0xFF00FF00`, цвет заливки блока по
умолчанию в Ramus) — это `-16711936`; непрозрачный чёрный — это
`-16777216`. Подтверждено на каждом образце файла (каждый обычный
функциональный блок использует именно эти два значения для фона/переднего
плана). `rsf_model.argb(r, g, b, a=255)` / `unpack_argb(value)`
преобразуют между 0–255 RGBA и этим представлением.

## 9. Иерархия декомпозиции (изучена частично)

**Подтверждено, по реальным данным файла:** существует системный
квалификатор с именем `F_BASE_FUNCTIONS` (id 8 в образце). Каждый его
**элемент** (не обычные функциональные блоки — отдельные учётные
элементы, с пустым `ELEMENT_NAME`) несёт
`F_BASE_FUNCTION_QUALIFIER_ID`, указывающий на квалификатор, являющийся
**корневой диаграммой модели верхнего уровня**. В образце: элемент 3 под
квалификатором 8 имеет `F_BASE_FUNCTION_QUALIFIER_ID = 9`, и квалификатор
9 — это действительно «Enterprise activity», корневая страница, чьи
элементы — это те блоки, которые вы видите при открытии файла.
`qualifiers_attributes.xml` подтверждает, что
`F_BASE_FUNCTION_QUALIFIER_ID` (id атрибута 35) прикреплён **только** к
квалификатору 8 — ни один обычный квалификатор функционального блока его
не несёт.

**Не подтверждено / явно вне рамок:** как *обычный* функциональный блок
(например, элемент 80, «Administrative processes», лежащий на корневой
странице) связывается с *собственной* дочерней диаграммой декомпозиции,
когда пользователь дважды кликает по нему в GUI и рисует диаграмму более
низкого уровня. Отслеживание
`idef0-common/.../pb/data/negine/NDataPlugin.java` и
`IDEF0Plugin.isFunction()` / `findElementForBaseFunction()` показывает,
что это проходит через больше логики виртуализации на стороне GUI
(обёртка `RowSet`/`NFunction`, привязанная к
`IDEF0Plugin.getBaseFunctions()`), чем через единственное проставленное
значение атрибута, и как-то вовлекает `F_OUNER_ID`, что не было полностью
установлено одним лишь статическим чтением — для этого потребовалось бы
либо запустить настоящее Java-приложение и сравнить состояние файла
до/после использования «Decompose», либо существенно больше времени на
трассировку `NDataPlugin`/`NFunction`/`SectorRefactor`.

**Что вместо этого даёт набор инструментов:**
- `Model.clone_qualifier_as_container(source_qualifier_id, name)` —
  практичный способ получить *валидную новую страницу диаграммы*: он
  копирует весь набор атрибутов с существующего, заведомо корректного
  квалификатора Function (найденного в файле-шаблоне) на совершенно
  новый квалификатор, вместо попытки собрать системный набор атрибутов
  IDEF0 с нуля. Это было протестировано сквозным образом (§14).
- `Model.register_model_root(base_functions_element_id, root_qualifier_id)`
  — настраивает *новую модель верхнего уровня* так же, как это делает
  элемент 3 в образце, чтобы свежеклонированная диаграмма как минимум
  отображалась как собственный независимый корень модели.
- Явно **не предоставляется**: вызов «связать этот блок с той дочерней
  диаграммой», потому что он не проверен. Если он вам нужен, честный
  следующий шаг — дальше трассировать
  `NDataPlugin.getRowSet()` / `NFunction`, либо инструментировать
  настоящую сборку Ramus.

## 10. Отрисовка новых стрелок (секторы / потоки / точки пересечения)

Стрелки IDEF0 (потоки данных/ресурсов между блоками, граничные
ICOM-стрелки, туннелированные стрелки и т. д.) моделируются через
`IDEF0.Sector` / `IDEF0.SectorBorder` / `IDEF0.SectorPoint` /
`IDEF0.SectorProperties`, плюс концепцию «точки пересечения»
(«crosspoint», `crosspoint_sequence` в `sequences.xml`) и, как минимум в
образце файла эпохи 2009 года, концепцию «ординат», которая даже не
появляется как собственная таблица (в этом файле вообще нет
`attribute_sector_points.xml` — исходный код `IDEF0Plugin` показывает
активный код миграции/зачистки для ещё более старой схемы
«`F_QUALIFIER_CROSSPOINT`», а значит, эта часть формата заметно
**менялась между версиями Ramus**).

**Создание совершенно новой стрелки теперь поддерживается**
(`Model.add_arrow()` / `Model.add_boundary_arrow()`), в отличие от более
ранних редакций этого документа. В этом разделе раньше говорилось, что
делать это безопасно без запущенного Ramus для тестирования непрактично;
это изменилось, как только настоящий исходный код Ramus
(github.com/Vitaliy-Yakovchuk/ramus) стал доступен для загрузки из этого
окружения, так что сам код создания стрелок удалось прочитать напрямую,
а не заново угадывать по одному лишь формату контейнера:

- `idef0-common/.../pb/idef/elements/SectorRefactor.java` —
  `createNewSector()` — это буквально «пользователь только что закончил
  тянуть новую стрелку» в реальном GUI; `createMiss()`/`createBorderPoints()`
  — его вспомогательные функции.
- `idef0-common/.../pb/data/negine/{NSector,NSectorBorder,NCrosspoint}.java`,
  `AbstractCrosspoint.java`, `pb/Crosspoint.java`, `pb/data/SectorBorder.java`
  — фактическая семантика модели данных: что означают поля `BORDER_TYPE` /
  `FUNCTION` / `FUNCTION_TYPE` / `CROSSPOINT` границы и как точка
  пересечения связывает границы секторов в граф связности.
- `idef0-core/.../idef0/IDEF0Plugin.java` — подтверждает, что
  `F_FUNCTION_SECTOR` (объявлен, реальные файлы его заполняют) **нигде
  фактически не читается** в приложении; `Model.add_arrow()` намеренно
  оставляет его неустановленным, вместо того чтобы угадывать значение,
  которое никто не использует.
- `com/dsoft/utils/{DataSaver,DataLoader}.java` — точный бинарный формат
  blob'а `VISUAL_ATTRIBUTES` у `IDEF0.Sector` (небольшая пользовательская
  little-endian сериализация штриха/шрифта/цвета, а не сериализация
  объектов Java).

Каждый из этих фрагментов затем был **перепроверен на реальных,
заполненных данных `attribute_sectors.xml`/`attribute_sector_borders.xml`
во всех трёх поставляемых образцах файлов** — а не просто прочитан
изолированно:

- Python-декодер, зеркалирующий точную байтовую раскладку `DataLoader`,
  был прогнан на реальных blob'ах `VISUAL_ATTRIBUTES` секторов и не
  оставил **ни одного лишнего байта**, подтвердив формат побайтово (штрих:
  ширина линии, окончание, соединение, фаза штрихового пунктира, предел
  острого угла, массив штрихов; затем имя/размер/стиль шрифта; затем цвет
  RGB).
- Простейшая, самая распространённая форма реальной стрелки — прямое
  соединение блок-к-блоку — была выделена и оказалась **одним элементом
  Sector с обеими границами `TYPE_FUNCTION`**
  (`BORDER_TYPE=-1`, `FUNCTION=<id элемента блока>`,
  `FUNCTION_TYPE=<сторона>`, у каждой — своя свежесозданная
  `CROSSPOINT`); именно так выглядят 283 из 288 стрелок в «Enterprise
  activity.rsf».
- Граничная стрелка (один конец на блоке, другой — на собственном крае
  диаграммы) была выделена тем же способом: `BORDER_TYPE` на граничном
  конце переиспользует *ту же* кодировку стороны, что и `FUNCTION_TYPE`
  (подтверждено через `MovingPanel.{RIGHT=0,BOTTOM=1,LEFT=2,TOP=3}`,
  которую `SectorRefactor` напрямую сравнивает с `FUNCTION_TYPE`
  границы).
- Критически важно: **ни одна немодифицированная реальная стрелка ни в
  одном из трёх образцов файлов не имеет вообще ни одной строки в
  `attribute_sector_points.xml`** — то есть Ramus вычисляет
  прямой/маршрут по умолчанию между двумя точками края *во время
  отрисовки*, и только вручную изогнутая/перетащенная стрелка
  заканчивается сохранёнными ординатами. `add_arrow()`/
  `add_boundary_arrow()` воспроизводят именно это немодифицированное,
  автоматически проложенное состояние (данные пути не пишутся), с
  которого начинается каждая стрелка.
- `Model.new_crosspoint_id()` намеренно **не** доверяет сохранённому
  значению `crosspoint_sequence` так, как §7 показывает, что можно
  доверять самовосстановлению id элемента/квалификатора/атрибута: чтение
  `NDataPlugin.createCrosspoint()` показывает, что у собственной
  последовательности точек пересечения Ramus нет цикла ресинхронизации
  `MAX(existing)`, в отличие от `IEngineImpl.createElement()` и т. п.
  (подтверждено по исходному коду) — и действительно, собственный
  `crosspoint_sequence` поставляемого образца файла (`31`) намного ниже
  его фактического максимального использованного значения `CROSSPOINT`
  (`54927`), почти наверняка устарел после сброса счётчика до миграции.
  `new_crosspoint_id()` вместо этого выводит безопасное значение из
  `MAX(CROSSPOINT)`, уже присутствующего в данных границ загруженного
  файла — протестировано добавлением новой стрелки к реальному,
  немодифицированному «Enterprise activity.rsf» и подтверждением, что
  свежевыделенные id точек пересечения не сталкиваются ни с одним из его
  260 уже существующих.
- Проверен цикл сохранения/загрузки: добавленные стрелки переживают
  `Model.save()` → `Model.load()` со всеми полями нетронутыми, как на
  файле, созданном с нуля (`template.new_model()`, которому потребовалось
  собрать набор атрибутов `F_SECTORS`/`F_STREAMS` с нуля — см.
  `Model.ensure_arrow_support()`), так и на реальном образце файла
  (который уже их имеет, как и любой настоящий файл Ramus).

**Что предоставляется:**

- `Model.add_arrow(from_element_id, from_side, to_element_id, to_side, *,
  name="", tunnel=False)` — прямая стрелка напрямую между двумя
  функциональными блоками на одной диаграмме. `from_side`/`to_side` —
  значения `ArrowSide` (`LEFT`=Input, `TOP`=Control, `RIGHT`=Output,
  `BOTTOM`=Mechanism, либо псевдонимы
  `INPUT`/`CONTROL`/`OUTPUT`/`MECHANISM`). Возвращает id нового элемента
  Stream (собственная идентичность/подпись стрелки).
- `Model.add_boundary_arrow(element_id, box_side, page_side, *,
  direction="in", name="", tunnel=False)` — стрелка ICOM между
  функциональным блоком и краем самой страницы диаграммы (входящая в
  диаграмму или выходящая из неё извне).
- `Model.ensure_arrow_support()` — собирает `F_SECTORS`/`F_STREAMS` и их
  набор атрибутов на файле, у которого их ещё нет (вызывается
  автоматически двумя методами выше).
- `encode_sector_visual_attributes(...)` — построить пользовательский
  blob `VISUAL_ATTRIBUTES` (ширина линии, окончание/соединение, штрих,
  шрифт, цвет), если вам не нужен проверенный вид «по умолчанию как в
  настоящем Ramus», который иначе используют `add_arrow()`/
  `add_boundary_arrow()`.

**Что всё ещё *не* предоставляется, и почему:**

- **Многосегментные / изогнутые стрелки.** Реальные файлы действительно
  соединяют цепочкой несколько элементов `Sector` в одну стрелку через
  общую `CROSSPOINT` в месте соединения (проверено на реальном потоке из
  4 секторов), так что механизм понятен, но он не был встроен в
  публичный хелпер — решения по маршрутизации, которые подразумевает
  изгиб (какая точка пересечения — `TYPE_ONE_IN`, а какая —
  `TYPE_ONE_OUT`, то есть какой конец «веерится»), выходят за рамки
  нужного для типичного случая и не были опробованы на достаточном
  количестве реальных многосегментных примеров, чтобы быть настолько же
  уверенными, как в односегментных формах выше. `Model.table(...)`
  по-прежнему может довести вас туда вручную, следуя тем же полям
  границ/точек пересечения.
- **Связывание функционального блока с его собственной дочерней
  диаграммой декомпозиции** — не связано со стрелками, всё ещё не
  реализовано; см. §9.
- Всё ещё не подтверждено фактической отрисовкой в GUI Ramus (см. §14)
  — всё вышеописанное имеет уверенность уровня «совпадает с реальными
  сохранёнными данными и с кодом, который их производит», а не
  «наблюдал, как Ramus это рисует».

Столбцы полностью документированы в §6
(`attribute_sectors.xml`, `attribute_sector_borders.xml`,
`attribute_sector_points.xml`), и обобщённый API таблиц
(`Model.table(path)`) может читать и редактировать любую из них так же,
как любую другую таблицу, для всего, что не покрыто хелперами выше —
например, переименование `ALTERNATIVE_TEXT` существующей стрелки, или
ручное построение многосегментного маршрута.

## 11. Потоки файловых атрибутов / HTML-текста

Атрибуты типа `Core.File` и `Core.HTMLText` (например, поле `Description`
у функционального блока) хранятся **не** как строки EAV. Из
`AbstractFilePlugin.java`:

```java
public String getFilePath(long elementId, long attributeId) {
    return "/elements/" + elementId + "/" + attributeId + "/Core/" + getFileName();
}
// HTMLTextPlugin.getFileName() -> "index.html"
```

то есть сырые байты (HTML для `Description`, либо байты оригинального
имени файла для обычного файлового вложения) записываются как
собственная запись zip по этому буквальному пути (ведущий `/` отбрасывается
при фактической записи в zip, согласно
`FileIEngineImpl.createZipEntry()`), и в `data/streams.xml` добавляется
соответствующая строка (`STREAM_ID` = тот же путь, **с** ведущим `/`).
Реальные образцы файлов подтверждают этот общий механизм хранения
потоков (например, записи `/elements/767/17/report.0.xml` существуют для
*другой* функции — редактора шаблонов отчётов, использующего ту же самую
конвенцию `/elements/<id>/<n>/...`), но так получилось, что среди них нет
ни одного функционального блока с непустым `Description`, так что этот
конкретный путь не наблюдался заполненным в реальном файле — он выведен
напрямую из исходного кода `AbstractFilePlugin` / `HTMLTextPlugin`, а не
подтверждён побайтово на реальном значении `Description`.
`Model.set_value(element_id, description_attr_id, html_bytes)` реализует
именно это (см. `Model._stream_path` / `_set_stream` в `rsf_model.py`) и
было протестировано механически (запись + перезагрузка возвращает те же
байты, учёт в таблице потоков остаётся согласованным), но **не** на
реальной отрисовке в GUI Ramus.

## 12. Совместимость со старым форматом (ветки/версионирование)

В образцах файлов эпохи 2009 года **нет вовсе** таблиц `branches`,
`attributes_history`, `qualifiers_history`, `*_data_metadata` (они были
добавлены в `update4.sql`, часть более поздней функции «ветвления
модели»). Код загрузки терпимо относится к отсутствию любой из них
(`loadTable` молча пропускает отсутствующие записи), а столбцы
`created_branch_id`/`removed_branch_id`, которые всё-таки существуют в
`elements`/`qualifiers`/`attributes`/`streams`, разумно принимают
значения по умолчанию при отсутствии в `<fields>` строки (SAX-обработчик
`XMLToTable` заранее заполняет `0` / `Integer.MAX_VALUE` для любого
столбца `*_branch_id`, явно не присутствующего в строке).
**Практическое следствие: вы можете выдавать более простые формы таблиц
до версии 2.0 (3–4 столбца, вообще без учёта веток), и современный
Ramus (2.0.x) всё равно корректно загрузит файл**, получая неявную
семантику ствола/ветки-0 бесплатно. Именно так набор инструментов
поступает по умолчанию (он никогда не добавляет таблицы/столбцы,
связанные с ветками, если только они уже не присутствовали в загруженном
вами файле).

## 13. Набор инструментов

Три файла, без сторонних зависимостей (чистый Python 3, только стандартная
библиотека: `zipfile`, `xml.etree.ElementTree`):

### `rsf_core.py` — слой контейнера

- `Table` — один разобранный файл `data/**/*.xml`: `.fields` (имя/тип/id),
  `.rows` (список словарей `{ИМЯ_СТОЛБЦА: значение}`, значения уже
  декодированы в нативные типы Python по §4), плюс хелперы `.find_rows(**eq)`
  и `.max_int(col)`. `.to_xml_bytes()` пересериализует её, в точности
  совпадая с реальным форматом (проверено, §14).
- `RsfArchive` — весь архив zip: `.tables` (словарь путь→`Table`),
  `.properties` (словарь путь→словарь, для двух файлов Properties-XML),
  `.raw` (словарь путь→байты, для всего остального — состояние GUI,
  вложения, настройки печати — сохраняется побайтово при сохранении, если
  вы это не трогаете). `.load(path)` / `.save(path)`.
- `bytes_to_rsf_hex` / `rsf_hex_to_bytes` — кодек байты↔hex из §4.
- `parse_rsf_date` / `format_rsf_date` — формат временной метки из §4.
- Этот слой **полностью обобщённый** — он не знает и не заботится о том,
  что такое IDEF0. Он может загружать, изучать и без потерь пересохранять
  *любой* файл `.rsf`, включая будущие, с таблицами, о которых этот
  документ не упоминает.

### `rsf_model.py` — семантический (EAV) слой

Построен поверх `rsf_core`. Ключевые части:

- `TYPE_MAP` — таблица `(plugin, type) -> (путь таблицы, режим, столбцы)`
  из §5/§6, `mode` ∈ `{scalar, struct, list, stream}`.
- `Model(archive)` / `Model.load(path)` — индексирует квалификаторы /
  элементы / атрибуты / связи квалификатор-атрибут при создании
  (`.refresh()` — переиндексировать после сырых правок через `.table(...)`).
- Обобщённый доступ к значениям: `get_value(element_id, attribute_id)` /
  `set_value(element_id, attribute_id, value)` / `delete_value(...)` —
  диспетчеризует по объявленному типу атрибута через `TYPE_MAP`, так что
  это работает для *любого* сопоставленного типа, не только IDEF0.
- Поиск: `find_qualifier(name)`, `find_attribute(qualifier_id, name)`,
  `element_qualifier(element_id)`, `attribute_type(attribute_id)`.
- Структурные правки: `add_element(qualifier_id, name)`,
  `set_element_name`, `delete_element`,
  `clone_qualifier_as_container(source_qualifier_id, new_name)` (§9),
  `register_model_root(...)` (§9), `new_element_id()` /
  `new_qualifier_id()` / `new_attribute_id()` (безопасное выделение ID
  по §7).
- Вспомогательные функции для функционального блока IDEF0 (§8):
  `set_name`, `set_bounds`, `set_background`, `set_foreground`,
  `set_font`, `set_status`, и разовый
  `add_function_box(qualifier_id, name, x, y, width, height, ...)`.
- `argb(r,g,b,a=255)` / `unpack_argb(value)` — кодек цвета из §8.
- Стрелки (§10): `add_arrow(from_element_id, from_side, to_element_id,
  to_side, name="", tunnel=False)` (блок-к-блоку), `add_boundary_arrow(
  element_id, box_side, page_side, direction="in", name="", tunnel=False)`
  (блок-к-краю-страницы), `ensure_arrow_support()` (собирает
  `F_SECTORS`/`F_STREAMS`, если в файле их нет), константы
  `ArrowSide`/`TunnelType`, `encode_sector_visual_attributes(...)` для
  пользовательского оформления стрелок.
- `dump_model(model, include_system_qualifiers=False)` — полный,
  сериализуемый в JSON снимок всей модели (каждый квалификатор → каждый
  элемент → каждый разрешённый атрибут), предназначенный для передачи
  человеку или ИИ, а не как формат для цикла редактирования с сохранением.
- `apply_json_dump(model, data)` — обратная операция: патчит JSON в
  форме `dump_model()` (например, отредактированный/отцензурированный
  вручную) обратно в модель, сопоставляя квалификаторы/элементы по id;
  см. `LLM_REDACTION_GUIDE.md` для точных правил, которым должен следовать
  редактор (человек или ИИ).
- `Model.table(path)` — аварийный люк к любой сырой таблице для всего, что
  не покрыто семантическими хелперами (многосегментные стрелки и т. д.,
  по §10).

### `rsf_cli.py` — интерфейс командной строки

```
python3 rsf_cli.py dump FILE.rsf [--all] [--pretty]      # вся модель как JSON
python3 rsf_cli.py qualifiers FILE.rsf                    # список квалификаторов
python3 rsf_cli.py elements FILE.rsf QUALIFIER_ID          # список элементов одного квалификатора
python3 rsf_cli.py show FILE.rsf ELEMENT_ID                 # атрибуты одного элемента
python3 rsf_cli.py tables FILE.rsf                          # каждая сырая таблица + число строк
python3 rsf_cli.py table FILE.rsf TABLE_PATH                # дамп одной сырой таблицы
python3 rsf_cli.py rename FILE.rsf ELEMENT_ID NEW_NAME OUT.rsf
```

### Пример: чтение существующего файла

```python
from rsf_model import Model, dump_model
import json

m = Model.load("MyModel.rsf")
print(m.qualifier_name(9))                 # -> "Enterprise activity"
print(m.element_attributes(79))             # -> {'Name': ..., 'F_BOUNDS': {...}, ...}
json.dump(dump_model(m), open("dump.json", "w"), ensure_ascii=False, indent=2)
```

### Пример: редактирование существующего файла

```python
from rsf_model import Model

m = Model.load("MyModel.rsf")
m.set_name(80, "Переименованный блок")
m.set_bounds(80, x=100, y=100, width=140, height=90)
m.save("MyModel_edited.rsf")
```

### Пример: создание совершенно новой диаграммы из шаблона

```python
from rsf_model import Model

# в качестве шаблона подойдёт любой существующий .rsf -- нужен лишь один
# квалификатор, у которого уже есть полный набор атрибутов функционального
# блока IDEF0 (подходит любая настоящая страница диаграммы).
m = Model.load("template.rsf")
root = m.find_qualifier("Enterprise activity")

new_qid = m.clone_qualifier_as_container(root, "Мой новый процесс")
m.add_function_box(new_qid, "Принять заказ",  x=40,  y=40, width=140, height=80)
m.add_function_box(new_qid, "Обработать заказ",  x=240, y=40, width=140, height=80)
m.add_function_box(new_qid, "Отгрузить заказ",     x=440, y=40, width=140, height=80)

# опционально: зарегистрировать её как собственную модель верхнего уровня в навигаторе
bf = m.find_base_functions_qualifier()
root_elem = m.add_element(bf, name="")
m.register_model_root(root_elem, new_qid)

m.save("new_diagram.rsf")
```

### Пример: соединить два блока новой стрелкой

```python
from rsf_model import Model, ArrowSide

m = Model.load("MyModel.rsf")
root = m.find_qualifier("Enterprise activity")
boxes = {m.elements[eid]["ELEMENT_NAME"]: eid
         for eid in m.elements_by_qualifier[root]}

# прямая стрелка со стороны Output блока "Принять заказ" на сторону Input блока "Обработать заказ"
m.add_arrow(boxes["Принять заказ"], ArrowSide.OUTPUT,
            boxes["Обработать заказ"], ArrowSide.INPUT,
            name="Заказ")

# стрелка Control, входящая в "Принять заказ" сверху страницы
m.add_boundary_arrow(boxes["Принять заказ"], ArrowSide.CONTROL, ArrowSide.TOP,
                      direction="in", name="Политика компании")

m.save("MyModel_with_arrows.rsf")
```

## 14. Проверка

В окружении, в котором это разрабатывалось, не было доступно сборки
Ramus на JVM/Gradle (белый список сети песочницы не включает Maven
Central, поэтому `./gradlew runLocal` не может скачать зависимости) —
так что ничего здесь не было подтверждено открытием результата в
настоящем GUI Ramus. Вот что *было* сделано вместо этого, что является
самой сильной практически возможной проверкой без этого:

1. **Утверждения, основанные только на статическом анализе, проверялись
   по более высокой планке**: каждая схема таблицы и правило кодирования
   в этом документе были перепроверены на **фактических байтах трёх
   реальных файлов `.rsf`**, поставляемых в самом репозитории Ramus (не
   синтетических примерах) — `dest/doc/en/Enterprise activity.rsf`,
   `dest/doc/ru/Model example.rsf`, `dest/doc/ru/Пример модели.rsf`.
2. **Тест бесшовного цикла сохранения/загрузки**: и английский, и русский
   образцы файлов были загружены через `RsfArchive.load()`, немедленно
   сохранены обратно без правок, и строки каждой таблицы (и каждая
   сырая/property-запись) были сравнены поле за полем с оригиналом —
   **нулевые расхождения**, включая текст на кириллице во всю ширину и
   различие «пусто против null» в полях.
3. **Тест цикла с редактированием**: загружен английский образец,
   переименован существующий функциональный блок, добавлен совершенно
   новый со всеми визуальными атрибутами (границы/цвета/шрифт/
   статус/тип) под *существующим* корневым квалификатором диаграммы,
   сохранено, перезагружено, и подтверждено, что каждое записанное
   значение совпадает с установленным. Сравнение сохранённого файла с
   оригиналом показало, что **изменились только фактически затронутые
   таблицы** — все 25 записей, не являющихся таблицами (состояние GUI,
   потоки, вложения), были сохранены побайтово.
4. **Тест создания новой диаграммы из шаблона**: набор атрибутов
   корневого квалификатора клонирован в совершенно новый квалификатор, к
   нему добавлены три функциональных блока, сохранено, перезагружено, и
   подтверждено, что новый квалификатор + элементы + атрибуты
   считываются обратно корректно, а архив проходит
   `zipfile.ZipFile.testzip()`.
5. **Тест регистрации корня модели**: добавлен новый элемент
   `F_BASE_FUNCTIONS` и указан на свежеклонированный квалификатор через
   `register_model_root`, сохранено, перезагружено, связь подтверждена.
6. **Тест кодека цвета**: `argb(0,255,0) == -16711936` и
   `argb(0,0,0) == -16777216` — совпадает с буквальными целыми
   значениями, встреченными в `F_BACKGROUND`/`F_FOREGROUND` каждого
   функционального блока в реальных образцах файлов.
7. **Создание стрелок** (§10, добавлено позже, как только настоящий
   исходный код Ramus стал доступен для загрузки из этого окружения):
   исходный код Java для создания стрелок был прочитан напрямую, а не
   выведен, и каждое построенное на нём утверждение было перепроверено
   на реальных данных так же, как и всё остальное здесь — декодер blob'а
   `VISUAL_ATTRIBUTES`, зеркалирующий реальный бинарный формат, прочитал
   blob'ы реальных секторов без единого лишнего байта; простые формы
   стрелок блок-к-блоку и блок-к-границе, которые производит этот модуль,
   были выделены из и сопоставлены с сотнями реальных стрелок в
   «Enterprise activity.rsf»; новая стрелка была добавлена в этот
   *немодифицированный реальный файл* (а не только в синтетический), и
   подтверждено, что её свежевыделенные id точек пересечения не
   сталкиваются ни с одним из 260 уже существующих в файле; и результат
   прошёл цикл сохранения/перезагрузки со всеми полями нетронутыми, как
   на этом реальном файле, так и на созданном с нуля через
   `template.new_model()` (что заодно проверило сборку
   `F_SECTORS`/`F_STREAMS` через `ensure_arrow_support()`).

Что **не** было проверено (что также явно отмечено по тексту выше):
связывание декомпозиции на уровне блока (§9), многосегментные/изогнутые
стрелки и точная байтовая раскладка заполненного потока `Core.HTMLText`
(§11) — они читаемы/редактируемы на уровне сырой таблицы, но их более
высокоуровневая корректность «это то, что ожидает GUI Ramus» не
подтверждена. И в более широком смысле: ничто в этом документе, включая
стрелки, не было подтверждено открытием результата в настоящем GUI Ramus
(не было доступно инструментов JVM/Gradle, чтобы собрать и запустить его)
— «совпадает с реально сохранёнными данными и исходным кодом, который их
производит» — это потолок того, что здесь было проверено.

## 15. Перекрёстные ссылки на исходные файлы

Для тех, кто хочет проверить или расширить это, сверяясь напрямую с
исходным кодом (все пути — относительно корня репозитория):

| тема | файл |
|---|---|
| оркестрация сохранения/загрузки, структура zip | `core/src/main/java/com/ramussoft/core/impl/FileIEngineImpl.java` |
| экспорт таблицы → XML | `core/src/main/java/com/ramussoft/core/impl/TableToXML.java` |
| импорт XML → таблица | `core/src/main/java/com/ramussoft/core/impl/XMLToTable.java` |
| основная SQL-схема | `database-storage/src/main/resources/com/ramussoft/jdbc/database.sql` + `update1..5.sql` |
| выделение ID (`createElement`/`createAttribute`/`createQualifier`) | `core/src/main/java/com/ramussoft/core/impl/IEngineImpl.java` |
| аннотации persistent-объектов (`@Table`, `@Text`, `@Long`, ...) | `common/src/main/java/com/ramussoft/common/persistent/*.java` |
| простые типы атрибутов Core | `core-simple-attributes/src/main/java/com/ramussoft/core/attribute/simple/*.java` |
| хранение потоков файл/HTML-текст | `core-simple-attributes/.../simple/AbstractFilePlugin.java`, `HTMLTextPlugin.java` |
| системный набор атрибутов IDEF0 (константы `F_*`, `checkIDEF0Attributes`) | `idef0-core/src/main/java/com/ramussoft/idef0/IDEF0Plugin.java` |
| persistent-классы атрибутов IDEF0 (Rectangle/Color/Font/Status/...) | `idef0-core/src/main/java/com/ramussoft/idef0/attribute/*.java` |
| логика декомпозиции/row-set на стороне GUI (трассировка не завершена, §9) | `idef0-common/src/main/java/com/ramussoft/pb/data/negine/NDataPlugin.java`, `NFunction.java` |
| точка входа создания стрелки («пользователь только что закончил рисовать»), §10 | `idef0-common/src/main/java/com/ramussoft/pb/idef/elements/SectorRefactor.java` |
| модель данных сектор/граница/точка пересечения, §10 | `idef0-common/src/main/java/com/ramussoft/pb/data/negine/{NSector,NSectorBorder,NCrosspoint}.java`, `pb/data/AbstractCrosspoint.java`, `pb/data/SectorBorder.java`, `pb/Crosspoint.java`, `pb/Sector.java` |
| константы сторон блока/края страницы (`ArrowSide`), §10 | `idef0-common/src/main/java/com/ramussoft/pb/idef/visual/MovingPanel.java` |
| бинарный формат blob'а `VISUAL_ATTRIBUTES`, §10 | `idef0-common/src/main/java/com/dsoft/utils/{DataSaver,DataLoader}.java` |
| последовательность id точек пересечения (без ресинхронизации по данным, в отличие от id элементов и т. п.), §7 и §10 | `idef0-core/src/main/java/com/ramussoft/idef0/IDEF0Plugin.java` (`getNextCrosspointId`), `idef0-common/.../negine/NDataPlugin.java` (`createCrosspoint`) |
| механика расширения файла / запуска | `local-client/src/main/java/com/ramussoft/local/FilePlugin.java` |
| реальные образцы файлов, использованные для проверки | `dest/doc/en/Enterprise activity.rsf`, `dest/doc/ru/Model example.rsf`, `dest/doc/ru/Пример модели.rsf` |

---

*Всё в этом документе выведено из исходного кода Ramus (лицензия
GPL-3.0) и из образцов файлов `.rsf`, распространяемых в том же
репозитории.*

---

## 16. Приложение по GUI (этот репозиторий)

Всё вышесказанное описывает формат файла и реконструированный набор
инструментов на Python в том виде, в каком он изначально был написан.
Этот репозиторий добавляет поверх него GUI на основе Qt
(`ramus_rsf_tool/gui/`) и один новый модуль, `ramus_rsf_tool/template.py`.
Заметки, относящиеся конкретно к этим дополнениям:

- **`template.py: new_model()`** собирает минимальный, но валидный архив
  с нуля (файл-шаблон не требуется), чтобы пункту «Файл > Создать» в GUI
  было с чего начать: он вручную строит `qualifiers`/`elements`/
  `attributes`/`qualifiers_attributes` со стандартным набором атрибутов
  функционального блока IDEF0 (§8) на одном корневом квалификаторе
  диаграммы, плюс учётный элемент `F_BASE_FUNCTIONS`, регистрирующий его
  как корень модели (§9). Это следует тому же подходу «минимальных форм
  таблиц до версии 2.0», задокументированному в §12, и покрыто
  `tests/test_rsf_model.py` (построено, сохранено, перезагружено,
  значения проверены) — но, как и остальной набор инструментов, не было
  открыто в настоящем GUI Ramus.
- **Вкладка «Сырые таблицы» в GUI** — это тонкий обобщённый табличный вид
  поверх `Model.table(path)` (§13) — у неё нет специального знания о
  семантике какой-либо таблицы, что и делает её пригодной в качестве
  аварийного люка, который §10 рекомендует для редактирования
  стрелок/секторов и всего прочего, для чего нет выделенного редактора
  на вкладке «Атрибуты».
- **Вкладка «Атрибуты»** диспетчеризует исключительно по режиму
  `TYPE_MAP` (`scalar`/`struct`/`list`/`stream`) плюс по объявленному
  SQL-типу каждого физического столбца (§4), с горсткой более приятных
  выделенных виджетов для хорошо известных типов IDEF0 (`Color`,
  `FRectangle`, `Font`, `Status`) — так что любой тип атрибута, конкретно
  здесь не названный (в том числе те, что не охвачены этим документом),
  всё равно получает пригодный, пусть и обобщённый, редактор, а не
  скрывается.
