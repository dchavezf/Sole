# Design: Theme System — Zero Hardcode Refactor

**Date:** 2026-06-07  
**Status:** Approved

## Problem

The md_converter has Solé-specific logic embedded in generic Python exporters:

1. `html_exporter.py` detects directive names (`caso`, `card-propuesta`, `cover`) and routes to specialized renderers with hardcoded HTML structures, SVG icons, CSS class names, and Spanish text strings.
2. Field parsers search for hardcoded Spanish marker strings (`**Caso:**`, `**Situación →**`, `**Para quién:**`).
3. `_CALLOUT_DEFAULT_ICONS` and `_CALLOUT_DEFAULT_LABELS` duplicate data from the theme JSON, creating drift risk and encoding a Spanish-language assumption in generic code.
4. The `cover` renderer hardcodes `"Propuesta · Reglamento Interno"` and `"Fraccionamiento Solé · Junio 2026"`.

**Goal:** The Python exporters must contain zero project-specific knowledge. All styling, field definitions, HTML structure, and DOCX rendering rules live in the theme JSON and companion template files.

---

## Architecture

### Responsibility split (before → after)

| Responsibility | Before | After |
|---|---|---|
| Directive field markers | Hardcoded Python strings | `customDirectives[name].fields` in theme JSON |
| HTML structure of complex directives | Python methods per directive | Jinja2 template files referenced by theme |
| DOCX rendering of complex directives | Generic fallback only | `docx.fieldSequence` in theme JSON |
| Callout default labels/icons | Python dicts (`_CALLOUT_DEFAULT_LABELS`) | Solely from `elements.callout[type].label/icon` in theme |
| Cover metadata | Hardcoded strings in Python | `fields.meta` labeled-list + template |

### New components

- **`core/field_extractor.py`** — Generic field extraction from a block's token stream, driven by a `fields` schema from the theme. No knowledge of any specific directive.
- **`templates/directives/*.html.jinja2`** — Built-in HTML templates for standard complex directives (`caso`, `card-propuesta`, `cover`). Themes can override by placing templates in `{theme_dir}/directives/`.
- **Extended `customDirectives` schema** — Adds `fields`, `html.template`, `docx.fieldSequence` keys.

---

## File Structure

```
md_converter/
  core/
    field_extractor.py        ← NEW
    theme.py                  ← no changes
    parser.py                 ← no changes
    ast_walker.py             ← no changes
  exporters/
    html_exporter.py          ← remove _render_caso/card_propuesta/cover, _CALLOUT_DEFAULT_*
    docx_exporter.py          ← remove _CALLOUT_DEFAULT_LABELS
    pdf_exporter.py           ← no changes
  templates/
    base.html.jinja2          ← no changes
    directives/               ← NEW directory
      caso.html.jinja2
      card-propuesta.html.jinja2
      cover.html.jinja2

themes/
  sole.theme.json             ← add fields + template paths + docx.fieldSequence
  sole.css                    ← no changes
  directives/                 ← optional per-theme template overrides
```

### Template resolution order

For `"template": "directives/caso.html.jinja2"`:
1. `{theme.base_dir}/directives/caso.html.jinja2` — theme override
2. `{md_converter}/templates/directives/caso.html.jinja2` — built-in fallback

---

## Field Extraction System (`core/field_extractor.py`)

### Field marker types

| `marker` value | Matches |
|---|---|
| `"heading"` | A heading block (`#`, `##`, etc.) |
| `"bold-line"` | A paragraph containing only `**text**` (no colon) |
| `"italic-line"` | A paragraph containing only `*text*` |
| `"**Label:**"` (literal) | A line starting with the exact string |

### Field types

| `type` value | Returns |
|---|---|
| (default / omitted) | `str` — the text content of the matched line/block |
| `"labeled-list"` | `list[{label: str, value: str}]` — all `**Key:** value` lines not claimed by another field |
| `"remainder"` | Pre-rendered HTML of all blocks not matched by any field |

### Output

```python
FieldResult = {
    "fields": {
        "title": str,
        "meta": list[{"label": str, "value": str}],
        "_content": str,    # pre-rendered HTML
        ...
    },
    "unmatched": list[Block]   # blocks not captured by any field
}
```

---

## Extended Directive Schema in Theme JSON

### Simple directive (no change)

```jsonc
"example": {
  "description": "Generic example block",
  "label": "Ejemplo",
  "allowedContent": "all",
  "html": { "tag": "div", "style": { ... } },
  "docx": { "paragraph": { ... } }
}
```

### Complex directive — `caso`

```jsonc
"caso": {
  "description": "Bloque de caso de estudio",
  "label": "",
  "allowedContent": "all",

  "fields": {
    "title":     { "marker": "**Caso:**",       "required": true },
    "situacion": { "marker": "**Situación →**", "required": false },
    "accion":    { "marker": "**Acción →**",    "required": false },
    "resultado": { "marker": "**Resultado →**", "required": false }
  },

  "html": {
    "template": "directives/caso.html.jinja2"
  },

  "docx": {
    "fieldSequence": [
      { "field": "title",     "renderAs": "bold-prefix", "prefix": "Caso" },
      { "field": "situacion", "renderAs": "bold-prefix", "prefix": "Situación →" },
      { "field": "accion",    "renderAs": "bold-prefix", "prefix": "Acción →" },
      { "field": "resultado", "renderAs": "bold-prefix", "prefix": "Resultado →" },
      { "field": "_body",     "renderAs": "paragraph" }
    ],
    "paragraph": {
      "shading": { "type": "clear", "fill": "{{colors.caso-bg}}" },
      "border":  { "left": { "style": "single", "size": 20, "space": 8, "color": "{{colors.accent}}" } },
      "indent":  { "left": 360 }
    }
  }
}
```

### Complex directive — `card-propuesta`

```jsonc
"card-propuesta": {
  "fields": {
    "title":    { "marker": "heading" },
    "para_quien": { "marker": "**Para quién:**" },
    "sabras":     { "marker": "**Al terminar esta parte sabrás:**" },
    "_body": { "type": "remainder" }
  },
  "html": { "template": "directives/card-propuesta.html.jinja2" },
  "docx": {
    "fieldSequence": [
      { "field": "title",       "renderAs": "heading", "level": 2 },
      { "field": "para_quien",  "renderAs": "bold-prefix", "prefix": "Para quién" },
      { "field": "_body",       "renderAs": "paragraph" },
      { "field": "sabras",      "renderAs": "bold-prefix", "prefix": "Al terminar sabrás" }
    ],
    "paragraph": {
      "shading": { "type": "clear", "fill": "F5F5F5" },
      "border":  { "top": { "style": "single", "size": 24, "space": 4, "color": "{{colors.primary}}" } },
      "indent":  { "left": 360, "right": 360 }
    }
  }
}
```

### Complex directive — `cover` (generic)

```jsonc
"cover": {
  "fields": {
    "title":    { "marker": "heading",       "required": true },
    "subtitle": { "marker": "italic-line" },
    "author":   { "marker": "bold-line" },
    "meta":  { "type": "labeled-list" },
    "_body": { "type": "remainder" }
  },
  "html": { "template": "directives/cover.html.jinja2" },
  "docx": {
    "fieldSequence": [
      { "field": "title",    "renderAs": "heading", "level": 1 },
      { "field": "subtitle", "renderAs": "paragraph" },
      { "field": "author",   "renderAs": "paragraph" },
      { "field": "meta",     "renderAs": "labeled-list" },
      { "field": "_body",    "renderAs": "paragraph" }
    ]
  }
}
```

---

## HTML Template System

### Template context

Every directive template receives:

```python
{
    "fields": {
        "title": str,
        "meta": list[{"label": str, "value": str}],   # if labeled-list
        "_content": str,                               # pre-rendered HTML
        ...
    },
    "directive_name": str,
    "theme_vars": dict,   # resolved theme variables (colors, fonts, etc.)
}
```

### Example: `caso.html.jinja2`

```jinja2
{% set step_keys = [("situacion", "Situación"), ("accion", "Acción"), ("resultado", "Resultado")] %}
<article class="md-card caso">
  <header class="caso-header">
    <span class="caso-badge">Caso</span>
    <h3 class="caso-title">{{ fields.title }}</h3>
  </header>
  <div class="caso-body">
    <div class="caso-steps">
      {% for key, label in step_keys %}
        {% if fields.get(key) %}
        <div class="caso-step step-{{ loop.index }}">
          <div class="step-indicator">
            <div class="step-dot">{{ "◉" if loop.last else "→" }}</div>
            {% if not loop.last %}<div class="step-connector"></div>{% endif %}
          </div>
          <div class="step-content">
            <span class="step-label">{{ label }}</span>
            <p class="step-text">{{ fields[key] }}</p>
          </div>
        </div>
        {% endif %}
      {% endfor %}
    </div>
    {% if fields.get("_content") %}{{ fields._content }}{% endif %}
  </div>
</article>
```

---

## DOCX Field Rendering

### `renderAs` types

| Value | Behavior |
|---|---|
| `"bold-prefix"` | Paragraph: `[prefix]: ` in bold + field value as normal run |
| `"heading"` | `doc.add_heading(field_value, level=N)` |
| `"paragraph"` | Plain paragraph with field text; for `_body`/`_content`, renders pre-collected blocks |
| `"labeled-list"` | One paragraph per `{label, value}` item: label bold + value normal |

### Generic DOCX rendering flow

```
_render_directive(doc, block)
  → name = directive_name(block)
  → cfg = theme.get_directive(name)
  → if cfg has "fields":
      result = field_extractor.extract(block, cfg["fields"])
      _render_directive_with_fields(doc, result, cfg["docx"])
    else:
      _render_directive_generic(doc, block, cfg["docx"])   ← current behavior
```

---

## Callout Defaults — Cleanup

**Remove from Python:**
- `_CALLOUT_DEFAULT_ICONS` dict in `html_exporter.py`
- `_CALLOUT_DEFAULT_LABELS` in both `html_exporter.py` and `docx_exporter.py`

**New rule:** If `theme.get_callout(ct)` returns no `label` → render without label. If no `icon` → render without icon. The theme is the sole source of truth.

**Required change to `sole.theme.json`:** Verify all callout variants define both `label` and `icon`. They currently do — no data migration needed.

---

## Schema Updates

The `notas/md-conversion-template.schema.json` needs new definitions for:
- `customDirectives[name].fields` — map of field name → `{marker, required, type}`
- `customDirectives[name].html.template` — string path
- `customDirectives[name].docx.fieldSequence` — array of `{field, renderAs, prefix?, level?}`

Marker type is `string` (literal prefix) or one of the enum values: `"heading"`, `"bold-line"`, `"italic-line"`.

Field type is `"labeled-list"` or `"remainder"` (default: plain string extraction).

---

## Backward Compatibility

- Simple directives (no `fields`, no `template`) continue working exactly as today — generic styled-div with no changes to their config.
- The `pagebreak` directive remains as-is (special-cased by token type, not by name).
- Themes that don't define `label`/`icon` on callouts will render without them (not a regression for Solé since it defines all of them).
