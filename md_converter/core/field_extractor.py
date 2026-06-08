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
    unmatched: list[Any] = field(default_factory=list)


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
        "labeled-list"  — collects **Key:** value lines into [{label, value}]
        "remainder"     — unmatched blocks (populated in result.unmatched)
    """
    result = FieldResult()

    heading_field: str | None = None
    bold_line_field: str | None = None
    italic_line_field: str | None = None
    labeled_list_key: str | None = None
    literal_fields: dict[str, str] = {}

    for field_name, field_cfg in fields_schema.items():
        ftype  = field_cfg.get("type", "")
        marker = field_cfg.get("marker", "")
        if ftype == "labeled-list":
            labeled_list_key = field_name
            result.fields[field_name] = []
        elif ftype == "remainder":
            pass  # remainder is just result.unmatched, no pre-init needed
        elif marker == "heading":
            heading_field = field_name
        elif marker == "bold-line":
            bold_line_field = field_name
        elif marker == "italic-line":
            italic_line_field = field_name
        elif marker:
            literal_fields[marker] = field_name

    for child in block.children:
        # Heading blocks matched at block level
        if heading_field and isinstance(child, Block) and is_heading(child.open):
            inline = first_inline(child)
            result.fields[heading_field] = get_inline_text(inline).strip() if inline else ""
            continue

        # Extract raw text
        if isinstance(child, Block):
            inline = first_inline(child)
            raw_text = get_inline_text(inline) if inline else ""
        elif isinstance(child, Token) and child.type == "inline":
            raw_text = child.content
        else:
            result.unmatched.append(child)
            continue

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
    """Try to match a single text line. Returns True if matched."""
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
