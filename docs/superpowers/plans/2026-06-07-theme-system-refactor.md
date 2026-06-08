# Theme System — Zero Hardcode Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all Solé-specific logic from the Python exporters, replacing it with a generic field extraction + Jinja2 template system driven entirely by the theme JSON.

**Architecture:** A new `core/field_extractor.py` parses structured fields from directive blocks using marker definitions in the theme. HTML exporters render Jinja2 templates (looked up from theme dir then built-in fallback). DOCX exporters use a declarative `fieldSequence` array in the theme JSON. Callout defaults move fully into the theme — no Python fallbacks.

**Tech Stack:** Python 3.11+, markdown-it-py, Jinja2, python-docx, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| CREATE | `md_converter/core/field_extractor.py` | Generic field extraction from directive blocks |
| CREATE | `md_converter/templates/directives/caso.html.jinja2` | HTML template for caso directive |
| CREATE | `md_converter/templates/directives/card-propuesta.html.jinja2` | HTML template for card-propuesta |
| CREATE | `md_converter/templates/directives/cover.html.jinja2` | HTML template for cover |
| CREATE | `tests/__init__.py` | Test package marker |
| CREATE | `tests/test_field_extractor.py` | Unit tests for field extractor |
| MODIFY | `md_converter/themes/sole.theme.json` | Add fields/template/fieldSequence to 3 directives |
| MODIFY | `md_converter/exporters/html_exporter.py` | Generic template rendering, remove Solé-specific methods |
| MODIFY | `md_converter/exporters/docx_exporter.py` | fieldSequence rendering, remove default labels |

---

## Task 1: Create `core/field_extractor.py`

**Files:**
- Create: `md_converter/core/field_extractor.py`
- Create: `tests/__init__.py`
- Create: `tests/test_field_extractor.py`

- [ ] **Step 1: Create test package and write failing tests**

Create `tests/__init__.py` (empty file).

Create `tests/test_field_extractor.py`:

```python
"""Unit tests for field_extractor.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "md_converter"))

import pytest
from markdown_it.token import Token
from core.ast_walker import Block
from core.field_extractor import extract


def _make_inline(content: str) -> Token:
    tok = Token("inline", "", 0)
    tok.content = content
    return tok


def _make_paragraph_block(content: str) -> Block:
    open_tok = Token("paragraph_open", "p", 1)
    close_tok = Token("paragraph_close", "p", -1)
    b = Block(open=open_tok, close=close_tok)
    b.children = [_make_inline(content)]
    return b


def _make_heading_block(content: str, level: int = 2) -> Block:
    open_tok = Token("heading_open", f"h{level}", 1)
    close_tok = Token("heading_close", f"h{level}", -1)
    b = Block(open=open_tok, close=close_tok)
    b.children = [_make_inline(content)]
    return b


def _make_directive_block(*children) -> Block:
    open_tok = Token("container_caso_open", "", 1)
    close_tok = Token("container_caso_close", "", -1)
    b = Block(open=open_tok, close=close_tok)
    b.children = list(children)
    return b


# ── literal marker ─────────────────────────────────────────────────────────

def test_literal_marker_extracts_field():
    fields_schema = {
        "title": {"marker": "**Caso:**", "required": True},
    }
    block = _make_directive_block(
        _make_paragraph_block("**Caso:** Un propietario quiere instalar un aljibe"),
    )
    result = extract(block, fields_schema)
    assert result["fields"]["title"] == "Un propietario quiere instalar un aljibe"
    assert result["unmatched"] == []


def test_unmatched_block_goes_to_unmatched():
    fields_schema = {
        "title": {"marker": "**Caso:**"},
    }
    extra = _make_paragraph_block("Este párrafo no tiene campo")
    block = _make_directive_block(
        _make_paragraph_block("**Caso:** Título"),
        extra,
    )
    result = extract(block, fields_schema)
    assert result["fields"]["title"] == "Título"
    assert extra in result["unmatched"]


# ── heading marker ─────────────────────────────────────────────────────────

def test_heading_marker_extracts_heading_block():
    fields_schema = {"title": {"marker": "heading"}}
    heading = _make_heading_block("Mi Título Principal", level=1)
    block = _make_directive_block(heading)
    result = extract(block, fields_schema)
    assert result["fields"]["title"] == "Mi Título Principal"


# ── bold-line and italic-line ──────────────────────────────────────────────

def test_bold_line_extracts_text_without_asterisks():
    fields_schema = {"author": {"marker": "bold-line"}}
    block = _make_directive_block(
        _make_paragraph_block("**Fraccionamiento Solé — El Toro**"),
    )
    result = extract(block, fields_schema)
    assert result["fields"]["author"] == "Fraccionamiento Solé — El Toro"


def test_italic_line_extracts_text_without_asterisks():
    fields_schema = {"subtitle": {"marker": "italic-line"}}
    block = _make_directive_block(
        _make_paragraph_block("*Propuesta de Reforma al Reglamento*"),
    )
    result = extract(block, fields_schema)
    assert result["fields"]["subtitle"] == "Propuesta de Reforma al Reglamento"


def test_bold_with_colon_not_captured_as_bold_line():
    """**Label:** value should NOT match bold-line (it has a colon)."""
    fields_schema = {"author": {"marker": "bold-line"}}
    block = _make_directive_block(
        _make_paragraph_block("**Presentado por:** Daniel Chávez"),
    )
    result = extract(block, fields_schema)
    assert "author" not in result["fields"]


# ── labeled-list ───────────────────────────────────────────────────────────

def test_labeled_list_collects_multiple_items():
    fields_schema = {"meta": {"type": "labeled-list"}}
    block = _make_directive_block(
        _make_paragraph_block(
            "**Presentado por:** Daniel Chávez\n"
            "**Contacto:** Tel. 444-105-8700\n"
            "**Fecha:** Junio 2026"
        ),
    )
    result = extract(block, fields_schema)
    meta = result["fields"]["meta"]
    assert len(meta) == 3
    assert meta[0] == {"label": "Presentado por", "value": "Daniel Chávez"}
    assert meta[1] == {"label": "Contacto", "value": "Tel. 444-105-8700"}
    assert meta[2] == {"label": "Fecha", "value": "Junio 2026"}


def test_labeled_list_does_not_steal_from_literal_marker():
    """A line matching a literal marker should NOT also go into labeled-list."""
    fields_schema = {
        "title":  {"marker": "**Caso:**"},
        "meta":   {"type": "labeled-list"},
    }
    block = _make_directive_block(
        _make_paragraph_block("**Caso:** Un propietario\n**Otro:** valor"),
    )
    result = extract(block, fields_schema)
    assert result["fields"]["title"] == "Un propietario"
    assert len(result["fields"]["meta"]) == 1
    assert result["fields"]["meta"][0]["label"] == "Otro"


# ── remainder ──────────────────────────────────────────────────────────────

def test_remainder_type_captures_unmatched_as_blocks():
    fields_schema = {
        "title": {"marker": "**Caso:**"},
        "_body": {"type": "remainder"},
    }
    extra = _make_paragraph_block("Párrafo de contenido libre")
    block = _make_directive_block(
        _make_paragraph_block("**Caso:** Título"),
        extra,
    )
    result = extract(block, fields_schema)
    assert extra in result["unmatched"]


# ── multiline paragraph with mixed content ─────────────────────────────────

def test_multiline_paragraph_splits_correctly():
    fields_schema = {
        "author":   {"marker": "bold-line"},
        "subtitle": {"marker": "italic-line"},
    }
    block = _make_directive_block(
        _make_paragraph_block(
            "**Fraccionamiento Solé — El Toro**\n"
            "*Propuesta de Reforma al Reglamento*"
        ),
    )
    result = extract(block, fields_schema)
    assert result["fields"]["author"] == "Fraccionamiento Solé — El Toro"
    assert result["fields"]["subtitle"] == "Propuesta de Reforma al Reglamento"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd c:\Claude\Sole
.venv\Scripts\python.exe -m pytest tests/test_field_extractor.py -v 2>&1 | head -30
```

Expected: `ImportError: No module named 'core.field_extractor'`

- [ ] **Step 3: Create `md_converter/core/field_extractor.py`**

```python
"""
Generic field extraction from directive blocks.

Reads a `fields` schema from the theme (customDirectives[name].fields)
and extracts structured content from a Block's children. Zero knowledge
of any specific directive or project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from markdown_it.token import Token
from core.ast_walker import Block, is_heading, first_inline, get_inline_text

# Matches **text** with no colon inside (bold-line marker)
_BOLD_LINE_RE = re.compile(r"^\*\*([^*:]+)\*\*$")
# Matches *text* (italic-line marker)
_ITALIC_LINE_RE = re.compile(r"^\*([^*]+)\*$")
# Matches **Label:** value (labeled-list entries)
_LABELED_RE = re.compile(r"^\*\*([^*]+):\*\*\s*(.+)$")


@dataclass
class FieldResult:
    fields: dict[str, Any] = field(default_factory=dict)
    unmatched: list = field(default_factory=list)


def extract(block: Block, fields_schema: dict) -> FieldResult:
    """
    Extract structured fields from a directive block.

    fields_schema maps field_name -> {marker?, type?, required?}

    Marker values:
        "heading"       — matches a heading block
        "bold-line"     — matches **text** (no colon)
        "italic-line"   — matches *text*
        "**Literal:**"  — matches lines starting with that exact string

    Type values (override marker):
        "labeled-list"  — collects **Key:** value lines as [{label, value}]
        "remainder"     — unmatched blocks (populated after extraction)
    """
    result = FieldResult()

    # Categorise fields by marker/type
    heading_field: str | None = None
    bold_line_field: str | None = None
    italic_line_field: str | None = None
    labeled_list_key: str | None = None
    remainder_key: str | None = None
    literal_fields: dict[str, str] = {}   # marker_str → field_name

    for field_name, field_cfg in fields_schema.items():
        ftype  = field_cfg.get("type", "")
        marker = field_cfg.get("marker", "")
        if ftype == "labeled-list":
            labeled_list_key = field_name
            result.fields[field_name] = []
        elif ftype == "remainder":
            remainder_key = field_name
        elif marker == "heading":
            heading_field = field_name
        elif marker == "bold-line":
            bold_line_field = field_name
        elif marker == "italic-line":
            italic_line_field = field_name
        elif marker:
            literal_fields[marker] = field_name

    # Process each child of the directive block
    for child in block.children:
        # Headings are matched at block level
        if heading_field and isinstance(child, Block) and is_heading(child.open):
            inline = first_inline(child)
            result.fields[heading_field] = get_inline_text(inline).strip() if inline else ""
            continue

        # Get inline text (handles Block wrapping a paragraph or bare inline token)
        if isinstance(child, Block):
            inline = first_inline(child)
            raw_text = inline.content if inline else ""
        elif isinstance(child, Token) and child.type == "inline":
            raw_text = child.content
        else:
            result.unmatched.append(child)
            continue

        # Split into lines; process each line independently
        lines = [ln.strip() for ln in raw_text.split("\n") if ln.strip()]
        child_has_match = False

        for line in lines:
            matched = _match_line(
                line, literal_fields, bold_line_field, italic_line_field,
                labeled_list_key, result
            )
            if matched:
                child_has_match = True

        if not child_has_match:
            result.unmatched.append(child)

    return result


def _match_line(
    line: str,
    literal_fields: dict[str, str],
    bold_line_field: str | None,
    italic_line_field: str | None,
    labeled_list_key: str | None,
    result: FieldResult,
) -> bool:
    """Try to match a single text line against field definitions. Returns True if matched."""
    # 1. Literal markers take priority
    for marker, field_name in literal_fields.items():
        if line.startswith(marker):
            result.fields[field_name] = line[len(marker):].strip()
            return True

    # 2. bold-line
    if bold_line_field:
        m = _BOLD_LINE_RE.match(line)
        if m:
            result.fields[bold_line_field] = m.group(1)
            return True

    # 3. italic-line
    if italic_line_field:
        m = _ITALIC_LINE_RE.match(line)
        if m:
            result.fields[italic_line_field] = m.group(1)
            return True

    # 4. labeled-list
    if labeled_list_key:
        m = _LABELED_RE.match(line)
        if m:
            result.fields[labeled_list_key].append({"label": m.group(1), "value": m.group(2)})
            return True

    return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd c:\Claude\Sole
.venv\Scripts\python.exe -m pytest tests/test_field_extractor.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
cd c:\Claude\Sole
rtk git add md_converter/core/field_extractor.py tests/__init__.py tests/test_field_extractor.py
rtk git commit -m "feat: add generic field_extractor for directive blocks"
```

---

## Task 2: Update `sole.theme.json` — Add directive config

**Files:**
- Modify: `md_converter/themes/sole.theme.json`

- [ ] **Step 1: Replace `card-propuesta` directive config**

In `md_converter/themes/sole.theme.json`, replace the entire `"card-propuesta"` block inside `"customDirectives"` with:

```jsonc
"card-propuesta": {
  "description": "Tarjeta de sección de propuesta con borde y fondo suave",
  "label": "",
  "allowedContent": "all",

  "fields": {
    "title":      { "marker": "heading" },
    "para_quien": { "marker": "**Para quién:**" },
    "sabras":     { "marker": "**Al terminar esta parte sabrás:**" },
    "_body":      { "type": "remainder" }
  },

  "html": {
    "template": "directives/card-propuesta.html.jinja2"
  },

  "docx": {
    "fieldSequence": [
      { "field": "title",      "renderAs": "heading",     "level": 2 },
      { "field": "para_quien", "renderAs": "bold-prefix", "prefix": "Para quién" },
      { "field": "_body",      "renderAs": "paragraph" },
      { "field": "sabras",     "renderAs": "bold-prefix", "prefix": "Al terminar esta parte sabrás" }
    ],
    "paragraph": {
      "shading": { "type": "clear", "fill": "F5F5F5" },
      "border":  { "top": { "style": "single", "size": 24, "space": 4, "color": "{{colors.primary}}" } },
      "indent":  { "left": 360, "right": 360 }
    }
  }
},
```

- [ ] **Step 2: Replace `caso` directive config**

Replace the entire `"caso"` block inside `"customDirectives"` with:

```jsonc
"caso": {
  "description": "Bloque de caso de estudio con borde izquierdo de acento",
  "label": "",
  "allowedContent": "all",

  "fields": {
    "title":     { "marker": "**Caso:**",       "required": true },
    "situacion": { "marker": "**Situación →**", "required": false },
    "accion":    { "marker": "**Acción →**",    "required": false },
    "resultado": { "marker": "**Resultado →**", "required": false },
    "_body":     { "type": "remainder" }
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
},
```

- [ ] **Step 3: Add `cover` directive config**

Add a new `"cover"` entry inside `"customDirectives"` (before the closing `}` of that object):

```jsonc
"cover": {
  "description": "Portada del documento. Extrae título, subtítulo, autor, lista de metadatos y contenido libre.",
  "label": "",
  "allowedContent": "all",

  "fields": {
    "title":    { "marker": "heading",       "required": true },
    "subtitle": { "marker": "italic-line" },
    "author":   { "marker": "bold-line" },
    "meta":     { "type": "labeled-list" },
    "_body":    { "type": "remainder" }
  },

  "html": {
    "template": "directives/cover.html.jinja2"
  },

  "docx": {
    "fieldSequence": [
      { "field": "title",    "renderAs": "heading",       "level": 1 },
      { "field": "subtitle", "renderAs": "paragraph" },
      { "field": "author",   "renderAs": "paragraph" },
      { "field": "meta",     "renderAs": "labeled-list" },
      { "field": "_body",    "renderAs": "paragraph" }
    ]
  }
},
```

- [ ] **Step 4: Remove the old `cover` directive CSS reference**

The old `cover` used CSS classes like `card-cover`, `cover-hero`, etc. that are still needed by the new template. No CSS changes needed — the template will output the same classes.

- [ ] **Step 5: Verify the theme validates**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe -c "from core.theme import load_theme; t = load_theme('themes/sole.theme.json'); print('OK', list(t.get_all_directives().keys()))"
```

Expected output: `OK ['card-propuesta', 'caso', 'example', 'pagebreak', 'details', 'cover']`

Note: If jsonschema validation fails, it's because the schema doesn't yet allow `fields`/`template`/`fieldSequence`. That's fine — schema update is Task 6. Temporarily add `"additionalProperties": true` to the directive schema or skip validation; revert after Task 6.

- [ ] **Step 6: Commit**

```bash
cd c:\Claude\Sole
rtk git add md_converter/themes/sole.theme.json
rtk git commit -m "feat: add fields/template/fieldSequence to caso, card-propuesta, cover directives"
```

---

## Task 3: Update `html_exporter.py`

**Files:**
- Modify: `md_converter/exporters/html_exporter.py`

Remove `_render_card_propuesta`, `_render_caso`, `_render_cover`, `_CALLOUT_DEFAULT_ICONS`, `_CALLOUT_DEFAULT_LABELS`. Add generic template-based rendering.

- [ ] **Step 1: Remove module-level default dicts and unused import**

Delete lines 32–47 in `html_exporter.py` (the `_CALLOUT_DEFAULT_ICONS` and `_CALLOUT_DEFAULT_LABELS` dicts). The file starts with:

```python
"""
HTML Exporter: renders a markdown-it token list to a self-contained HTML5 file.
...
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, ChoiceLoader
from markdown_it import MarkdownIt
from markdown_it.token import Token

from core.theme import Theme
from core.ast_walker import (
    iter_blocks, Block,
    is_heading, heading_level,
    is_callout, callout_type,
    is_directive, directive_name,
    is_table,
    get_inline_text,
    first_inline,
    css_dict_to_string, merge_css_classes
)
from core.field_extractor import extract

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
```

Note: add `ChoiceLoader` to the jinja2 import and add `from core.field_extractor import extract`.

- [ ] **Step 2: Update `__init__` to use ChoiceLoader for template resolution**

Replace the `__init__` method:

```python
def __init__(self, theme: Theme) -> None:
    self.theme = theme
    self._jinja = Environment(
        loader=ChoiceLoader([
            FileSystemLoader(str(theme.base_dir)),
            FileSystemLoader(str(_TEMPLATES_DIR)),
        ]),
        autoescape=False,
    )
```

- [ ] **Step 3: Replace `_render_directive` with generic implementation**

Replace the entire `_render_directive` method (currently lines 313–336) with:

```python
def _render_directive(self, block: Block) -> str:
    name = directive_name(block)

    if name == "pagebreak":
        return '<div class="page-break"></div>\n'

    cfg = self.theme.get_directive(name)
    html_cfg = cfg.get("html", {})
    template_path = html_cfg.get("template")
    fields_schema = cfg.get("fields", {})

    if template_path and fields_schema:
        return self._render_directive_templated(block, cfg, template_path, fields_schema)

    # Generic fallback: styled div
    tag = html_cfg.get("tag", "div")
    base_cls = merge_css_classes(f"directive directive-{name}", html_cfg.get("className", ""))
    label = cfg.get("label", "")
    icon_cfg = cfg.get("icon", {})
    icon = icon_cfg.get("html") or icon_cfg.get("unicode") or ""
    header = f'  <div class="directive-header">{icon} {label}</div>\n' if (label or icon) else ""
    body = "".join(self._render_item(c) for c in block.children)
    return f'<{tag} class="{base_cls}">\n{header}{body}</{tag}>\n'

def _render_directive_templated(
    self, block: Block, cfg: dict, template_path: str, fields_schema: dict
) -> str:
    result = extract(block, fields_schema)

    # Pre-render unmatched blocks for _body / remainder fields
    body_html = "".join(self._render_item(b) for b in result.unmatched)

    fields = dict(result.fields)
    for field_name, field_cfg in fields_schema.items():
        if field_cfg.get("type") == "remainder":
            fields[field_name] = body_html
            break

    template = self._jinja.get_template(template_path)
    return template.render(
        fields=fields,
        directive_name=directive_name(block),
        theme_vars=self.theme.get_variables(),
    )
```

- [ ] **Step 4: Update `_render_callout` to remove default label/icon fallbacks**

Replace the `_render_callout` method:

```python
def _render_callout(self, block: Block) -> str:
    ct = callout_type(block)
    cfg = self.theme.get_callout(ct)
    icon_cfg = cfg.get("icon", {})
    icon_html = icon_cfg.get("html") or icon_cfg.get("unicode") or ""
    label = cfg.get("label") or ""

    title_content = f"{icon_html} {label}".strip()
    title_html = f'  <div class="callout-title">{title_content}</div>\n' if title_content else ""

    body = "".join(self._render_item(c) for c in block.children)
    return (
        f'<div class="callout callout-{ct}">\n'
        f'{title_html}'
        f'  <div class="callout-body">\n{body}</div>\n'
        f'</div>\n'
    )
```

- [ ] **Step 5: Delete the three Solé-specific renderer methods**

Delete the following methods entirely from `html_exporter.py`:
- `_render_card_propuesta` (lines ~349–418)
- `_render_caso` (lines ~420–481)
- `_render_cover` (lines ~483–611)

Also delete the "Card Components Logic" section comment.

- [ ] **Step 6: Verify the exporter imports and runs without errors**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe -c "from exporters.html_exporter import HtmlExporter; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
cd c:\Claude\Sole
rtk git add md_converter/exporters/html_exporter.py
rtk git commit -m "refactor: generic template-based directive rendering in html_exporter, remove Sole-specific methods"
```

---

## Task 4: Create HTML directive templates

**Files:**
- Create: `md_converter/templates/directives/caso.html.jinja2`
- Create: `md_converter/templates/directives/card-propuesta.html.jinja2`
- Create: `md_converter/templates/directives/cover.html.jinja2`

- [ ] **Step 1: Create `caso.html.jinja2`**

Create `md_converter/templates/directives/caso.html.jinja2`:

```jinja2
{% set step_keys = [("situacion", "Situación"), ("accion", "Acción"), ("resultado", "Resultado")] %}
<article class="md-card caso">
  <header class="caso-header">
    <span class="caso-badge">Caso</span>
    <h3 class="caso-title">{{ fields.get("title", "") }}</h3>
  </header>
  <div class="caso-body">
    <div class="caso-steps">
      {% for key, label in step_keys %}
        {% if fields.get(key) %}
        {% set loop_last = loop.last %}
        <div class="caso-step step-s{{ loop.index }}">
          <div class="step-indicator">
            <div class="step-dot">{{ "◉" if loop_last else "→" }}</div>
            {% if not loop_last %}<div class="step-connector"></div>{% endif %}
          </div>
          <div class="step-content">
            <div class="step-label-row">
              <span class="step-label">{{ label }}</span>
            </div>
            <p class="step-text">{{ fields[key] }}</p>
          </div>
        </div>
        {% endif %}
      {% endfor %}
    </div>
    {% if fields.get("_body") %}{{ fields["_body"] }}{% endif %}
  </div>
</article>
```

- [ ] **Step 2: Create `card-propuesta.html.jinja2`**

Create `md_converter/templates/directives/card-propuesta.html.jinja2`:

```jinja2
{% set title = fields.get("title", "") %}
{% set para_quien = fields.get("para_quien", "") %}
{% set sabras = fields.get("sabras", "") %}
{% set body_html = fields.get("_body", "") %}
{% set part_match = title | regex_search("Parte\\s+(\\d+)") %}
{% if part_match %}
  {% set part_num = part_match[0] | int %}
  {% set part_label = "0" ~ part_num if part_num < 10 else part_num | string %}
{% else %}
  {% set part_label = "01" %}
{% endif %}
<article class="md-card card-propuesta">
  <div class="cp-inner">
    <div class="cp-top">
      <h2>{{ title }}</h2>
      <span class="cp-chip">Parte {{ part_label }}</span>
    </div>
    {% if para_quien %}
    <div class="cp-para-quien">
      <span class="cp-pq-label">Para quién</span>
      <span class="cp-pq-text">{{ para_quien }}</span>
    </div>
    {% endif %}
    <div class="cp-body">{{ body_html }}</div>
  </div>
  {% if sabras %}
  <footer class="cp-footer">
    <div class="cp-footer-icon">
      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
        <path d="M6.5 1L8.2 4.5L12 5.1L9.25 7.8L9.9 11.6L6.5 9.8L3.1 11.6L3.75 7.8L1 5.1L4.8 4.5L6.5 1Z" fill="currentColor"/>
      </svg>
    </div>
    <div class="cp-footer-content">
      <div class="cp-footer-label">Al terminar esta parte sabrás</div>
      <p class="cp-footer-text">{{ sabras }}</p>
    </div>
  </footer>
  {% endif %}
</article>
```

Note: The `regex_search` filter is not built into Jinja2. Replace the part-number extraction with a simpler approach:

```jinja2
{% set title = fields.get("title", "") %}
{% set para_quien = fields.get("para_quien", "") %}
{% set sabras = fields.get("sabras", "") %}
{% set body_html = fields.get("_body", "") %}
{# Extract part number from title like "Parte 1 — ..." or "Parte 12 — ..." #}
{% set part_label = "01" %}
{% for word in title.split() %}
  {% if loop.previtem == "Parte" or loop.previtem == "parte" %}
    {% set n = word | int(0) %}
    {% if n > 0 %}
      {% set part_label = ("0" ~ n) if n < 10 else n | string %}
    {% endif %}
  {% endif %}
{% endfor %}
<article class="md-card card-propuesta">
  <div class="cp-inner">
    <div class="cp-top">
      <h2>{{ title }}</h2>
      <span class="cp-chip">Parte {{ part_label }}</span>
    </div>
    {% if para_quien %}
    <div class="cp-para-quien">
      <span class="cp-pq-label">Para quién</span>
      <span class="cp-pq-text">{{ para_quien }}</span>
    </div>
    {% endif %}
    <div class="cp-body">{{ body_html }}</div>
  </div>
  {% if sabras %}
  <footer class="cp-footer">
    <div class="cp-footer-icon">
      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
        <path d="M6.5 1L8.2 4.5L12 5.1L9.25 7.8L9.9 11.6L6.5 9.8L3.1 11.6L3.75 7.8L1 5.1L4.8 4.5L6.5 1Z" fill="currentColor"/>
      </svg>
    </div>
    <div class="cp-footer-content">
      <div class="cp-footer-label">Al terminar esta parte sabrás</div>
      <p class="cp-footer-text">{{ sabras }}</p>
    </div>
  </footer>
  {% endif %}
</article>
```

- [ ] **Step 3: Create `cover.html.jinja2`**

Create `md_converter/templates/directives/cover.html.jinja2`:

```jinja2
{% set title    = fields.get("title", "") %}
{% set subtitle = fields.get("subtitle", "") %}
{% set author   = fields.get("author", "") %}
{% set meta     = fields.get("meta", []) %}
{% set body_html = fields.get("_body", "") %}
<article class="card-cover">
  <div class="cover-hero">
    <div class="cover-corners">
      <span class="cover-corner tl"></span><span class="cover-corner tr"></span>
      <span class="cover-corner bl"></span><span class="cover-corner br"></span>
    </div>
    {% if author %}
    <div class="cover-eyebrow">
      <span class="cover-eyebrow-line"></span>
      <span class="cover-eyebrow-text">{{ author }}</span>
    </div>
    {% endif %}
    <h1 class="cover-title">{{ title }}</h1>
    {% if subtitle or author %}
    <div class="cover-project-row">
      {% if author %}<span class="cover-project-name">{{ author }}</span>{% endif %}
      {% if author and subtitle %}<span class="cover-project-sep"></span>{% endif %}
      {% if subtitle %}<span class="cover-project-type">{{ subtitle }}</span>{% endif %}
    </div>
    {% endif %}
  </div>
  {% if meta or body_html %}
  <div class="cover-meta">
    {% if meta %}
    <dl class="meta-grid">
      {% for item in meta %}
      <div class="meta-item">
        <dt class="meta-label">{{ item.label }}</dt>
        <dd><span class="meta-primary">{{ item.value }}</span></dd>
      </div>
      {% endfor %}
    </dl>
    {% endif %}
    {% if body_html %}{{ body_html }}{% endif %}
  </div>
  {% endif %}
</article>
```

- [ ] **Step 4: Commit templates**

```bash
cd c:\Claude\Sole
rtk git add md_converter/templates/directives/
rtk git commit -m "feat: add Jinja2 HTML templates for caso, card-propuesta, cover directives"
```

---

## Task 5: Update `docx_exporter.py`

**Files:**
- Modify: `md_converter/exporters/docx_exporter.py`

- [ ] **Step 1: Add import and remove `_CALLOUT_DEFAULT_LABELS`**

At the top of `docx_exporter.py`, add the import after the existing ast_walker imports:

```python
from core.field_extractor import extract
```

Delete the `_CALLOUT_DEFAULT_LABELS` dict (lines 66–73). It currently looks like:

```python
_CALLOUT_DEFAULT_LABELS = {
    "note":      "Nota",
    "tip":       "Consejo",
    "warning":   "Advertencia",
    "caution":   "Precaución",
    "important": "Importante",
    "danger":    "Peligro",
}
```

- [ ] **Step 2: Update `_render_callout` to use theme only**

Replace `_render_callout` method:

```python
def _render_callout(self, doc: "Document", block: Block) -> None:
    ct = callout_type(block)
    cfg = self.theme.get_callout(ct)
    docx_cfg = cfg.get("docx", {})
    label = cfg.get("label") or ""

    if label:
        title_p = doc.add_paragraph()
        title_run = title_p.add_run(f"  {label.upper()}")
        title_run.bold = True
        _apply_callout_border(title_p, docx_cfg, is_title=True)
        shading = docx_cfg.get("paragraph", {}).get("shading", {})
        if shading:
            _apply_shading(title_p, shading)

    shading = docx_cfg.get("paragraph", {}).get("shading", {})
    for child in block.children:
        p = doc.add_paragraph()
        if isinstance(child, Token) and child.type == "inline":
            self._render_inline_token(p, child)
        elif isinstance(child, Block):
            inner = first_inline(child)
            if inner:
                self._render_inline_token(p, inner)
        _apply_callout_border(p, docx_cfg, is_title=False)
        if shading:
            _apply_shading(p, shading)
```

- [ ] **Step 3: Replace `_render_directive` with field-aware version**

Replace the entire `_render_directive` method:

```python
def _render_directive(self, doc: "Document", block: Block) -> None:
    name = directive_name(block)
    cfg = self.theme.get_directive(name)
    docx_cfg = cfg.get("docx", {})
    fields_schema = cfg.get("fields", {})

    if fields_schema and docx_cfg.get("fieldSequence"):
        self._render_directive_with_fields(doc, block, cfg)
        return

    # Generic fallback
    label = cfg.get("label", "")
    if label:
        lp = doc.add_paragraph()
        lp.add_run(label).bold = True
        _apply_callout_border(lp, docx_cfg, is_title=True)

    for child in block.children:
        p = doc.add_paragraph()
        if isinstance(child, Token) and child.type == "inline":
            self._render_inline_token(p, child)
        elif isinstance(child, Block):
            inner = first_inline(child)
            if inner:
                self._render_inline_token(p, inner)
        shading = docx_cfg.get("paragraph", {}).get("shading", {})
        if shading:
            _apply_shading(p, shading)
        _apply_callout_border(p, docx_cfg, is_title=False)
```

- [ ] **Step 4: Add `_render_directive_with_fields` method**

Add this method to `DocxExporter` (after `_render_directive`):

```python
def _render_directive_with_fields(
    self, doc: "Document", block: Block, cfg: dict
) -> None:
    result = extract(block, cfg.get("fields", {}))
    fields = result.fields
    unmatched = result.unmatched

    docx_cfg = cfg.get("docx", {})
    para_cfg = docx_cfg.get("paragraph", {})
    field_sequence = docx_cfg.get("fieldSequence", [])

    for seq_item in field_sequence:
        field_key = seq_item["field"]
        render_as = seq_item.get("renderAs", "paragraph")

        if field_key == "_body":
            for child in unmatched:
                p = doc.add_paragraph()
                if isinstance(child, Token) and child.type == "inline":
                    self._render_inline_token(p, child)
                elif isinstance(child, Block):
                    inner = first_inline(child)
                    if inner:
                        self._render_inline_token(p, inner)
                if para_cfg:
                    _apply_paragraph_cfg(p, para_cfg)
            continue

        value = fields.get(field_key)
        if not value:
            continue

        if render_as == "heading":
            level = seq_item.get("level", 2)
            try:
                p = doc.add_heading("", level=level)
            except Exception:
                p = doc.add_paragraph()
            p.add_run(str(value)).bold = True

        elif render_as == "bold-prefix":
            prefix = seq_item.get("prefix", field_key)
            p = doc.add_paragraph()
            p.add_run(f"{prefix}: ").bold = True
            p.add_run(str(value))
            if para_cfg:
                _apply_paragraph_cfg(p, para_cfg)

        elif render_as == "labeled-list":
            for entry in (value if isinstance(value, list) else []):
                p = doc.add_paragraph()
                p.add_run(f"{entry['label']}: ").bold = True
                p.add_run(entry["value"])
                if para_cfg:
                    _apply_paragraph_cfg(p, para_cfg)

        elif render_as == "paragraph":
            p = doc.add_paragraph(str(value))
            if para_cfg:
                _apply_paragraph_cfg(p, para_cfg)
```

- [ ] **Step 5: Verify imports work**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe -c "from exporters.docx_exporter import DocxExporter; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd c:\Claude\Sole
rtk git add md_converter/exporters/docx_exporter.py
rtk git commit -m "refactor: fieldSequence-based directive rendering in docx_exporter, remove default callout labels"
```

---

## Task 6: Update JSON schema

**Files:**
- Modify: `notas/md-conversion-template.schema.json`

- [ ] **Step 1: Read the current customDirectives schema section**

Open `notas/md-conversion-template.schema.json` and locate the `"customDirectives"` property definition. It currently defines the directive item shape.

- [ ] **Step 2: Add field definitions to the directive item schema**

Within the `"customDirectives"` additionalProperties (the directive item object), add the following new optional properties to the existing `"properties"` block:

```jsonc
"fields": {
  "type": "object",
  "description": "Structured field extraction schema. Keys are field names; values define how to detect each field in the markdown content.",
  "additionalProperties": {
    "type": "object",
    "properties": {
      "marker": {
        "type": "string",
        "description": "How to detect this field. Use 'heading', 'bold-line', 'italic-line', or a literal string prefix like '**Caso:**'."
      },
      "type": {
        "type": "string",
        "enum": ["labeled-list", "remainder"],
        "description": "Special field type. 'labeled-list' collects **Key:** value lines into a list. 'remainder' receives all unmatched content."
      },
      "required": { "type": "boolean" }
    }
  }
},
```

- [ ] **Step 3: Extend `html` sub-object to allow `template`**

Find the `"html"` property in the directive item schema and add `"template"`:

```jsonc
"template": {
  "type": "string",
  "description": "Relative path to a Jinja2 template file. Resolved from theme dir first, then built-in templates dir."
}
```

- [ ] **Step 4: Extend `docx` sub-object to allow `fieldSequence`**

Find the `"docx"` property in the directive item schema and add:

```jsonc
"fieldSequence": {
  "type": "array",
  "description": "Ordered list of field render instructions for DOCX output.",
  "items": {
    "type": "object",
    "required": ["field", "renderAs"],
    "properties": {
      "field":     { "type": "string", "description": "Field name from 'fields' schema, or '_body' for unmatched content." },
      "renderAs":  { "type": "string", "enum": ["bold-prefix", "heading", "paragraph", "labeled-list"] },
      "prefix":    { "type": "string", "description": "Label text for bold-prefix renderAs." },
      "level":     { "type": "integer", "minimum": 1, "maximum": 6, "description": "Heading level for heading renderAs." }
    }
  }
}
```

- [ ] **Step 5: Validate sole.theme.json passes schema**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe -c "
from core.theme import load_theme
t = load_theme('themes/sole.theme.json')
print('Theme valid. Directives:', list(t.get_all_directives().keys()))
"
```

Expected: `Theme valid. Directives: ['card-propuesta', 'caso', 'example', 'pagebreak', 'details', 'cover']`

- [ ] **Step 6: Commit**

```bash
cd c:\Claude\Sole
rtk git add notas/md-conversion-template.schema.json
rtk git commit -m "feat: extend directive schema with fields, template, and fieldSequence"
```

---

## Task 7: End-to-end validation

**Files:** No file changes — validation only.

- [ ] **Step 1: Run full conversion on the Propuesta**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe md_converter.py \
  --input ..\Propuesta\Sole_02_00_Propuesta.md \
  --theme themes\sole.theme.json \
  --output html \
  --title "Propuesta Solé"
```

Expected: `[OK] HTML -> ...Propuesta\Sole_02_00_Propuesta.html`

- [ ] **Step 2: Visually verify HTML output**

Open the generated HTML file in a browser. Verify:
- `:::caso` blocks render with the step-indicator layout (dots, connector, labels, text)
- `:::card-propuesta` blocks render with the `cp-inner`, `cp-para-quien`, `cp-footer` structure
- `:::cover` blocks render with the hero + meta-grid structure

- [ ] **Step 3: Run DOCX export**

```bash
cd c:\Claude\Sole\md_converter
.venv\Scripts\python.exe md_converter.py \
  --input ..\Propuesta\Sole_02_00_Propuesta.md \
  --theme themes\sole.theme.json \
  --output docx \
  --title "Propuesta Solé"
```

Expected: `[OK] DOCX -> ...`

Open the DOCX. Verify:
- `caso` blocks show "Caso: [title]" bold prefix, then Situación/Acción/Resultado with bold prefixes
- `card-propuesta` shows the heading then "Para quién: ..." and "Al terminar sabrás: ..."
- `cover` shows title as Heading 1, then meta items with bold labels

- [ ] **Step 4: Run all field_extractor tests one final time**

```bash
cd c:\Claude\Sole
.venv\Scripts\python.exe -m pytest tests/test_field_extractor.py -v
```

Expected: All PASS.

- [ ] **Step 5: Final commit**

```bash
cd c:\Claude\Sole
rtk git add .
rtk git commit -m "feat: complete theme system refactor — zero hardcode in Python exporters"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Remove Solé-specific methods from html_exporter | Task 3 steps 4–5 |
| Generic field extraction from theme schema | Task 1 |
| Jinja2 template per directive (html) | Tasks 3–4 |
| Template resolution: theme dir first, built-in fallback | Task 3 step 2 |
| `fields` schema with marker types | Task 1 |
| `labeled-list` type | Task 1 test + implementation |
| `remainder` type | Task 1 test + implementation |
| DOCX `fieldSequence` rendering | Task 5 step 4 |
| DOCX `renderAs` types: bold-prefix, heading, paragraph, labeled-list | Task 5 step 4 |
| Callout defaults removed from Python | Tasks 3 step 4, 5 steps 1–2 |
| `cover` directive with generic fields | Task 2 step 3 |
| JSON schema update | Task 6 |
| Backward compat: simple directives unchanged | Task 3 step 3 (fallback path) |
| `pagebreak` unchanged | Task 3 step 3 (first branch) |

All requirements covered. No placeholders. Types consistent across tasks (`FieldResult.fields`, `FieldResult.unmatched`).
