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


def test_literal_marker_extracts_field():
    fields_schema = {
        "title": {"marker": "**Caso:**", "required": True},
    }
    block = _make_directive_block(
        _make_paragraph_block("**Caso:** Un propietario quiere instalar un aljibe"),
    )
    result = extract(block, fields_schema)
    assert result.fields["title"] == "Un propietario quiere instalar un aljibe"
    assert result.unmatched == []


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
    assert result.fields["title"] == "Título"
    assert extra in result.unmatched


def test_heading_marker_extracts_heading_block():
    fields_schema = {"title": {"marker": "heading"}}
    heading = _make_heading_block("Mi Título Principal", level=1)
    block = _make_directive_block(heading)
    result = extract(block, fields_schema)
    assert result.fields["title"] == "Mi Título Principal"


def test_bold_line_extracts_text_without_asterisks():
    fields_schema = {"author": {"marker": "bold-line"}}
    block = _make_directive_block(
        _make_paragraph_block("**Fraccionamiento Solé — El Toro**"),
    )
    result = extract(block, fields_schema)
    assert result.fields["author"] == "Fraccionamiento Solé — El Toro"


def test_italic_line_extracts_text_without_asterisks():
    fields_schema = {"subtitle": {"marker": "italic-line"}}
    block = _make_directive_block(
        _make_paragraph_block("*Propuesta de Reforma al Reglamento*"),
    )
    result = extract(block, fields_schema)
    assert result.fields["subtitle"] == "Propuesta de Reforma al Reglamento"


def test_bold_with_colon_not_captured_as_bold_line():
    """**Label:** value should NOT match bold-line (it has a colon)."""
    fields_schema = {"author": {"marker": "bold-line"}}
    block = _make_directive_block(
        _make_paragraph_block("**Presentado por:** Daniel Chávez"),
    )
    result = extract(block, fields_schema)
    assert "author" not in result.fields


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
    meta = result.fields["meta"]
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
    assert result.fields["title"] == "Un propietario"
    assert len(result.fields["meta"]) == 1
    assert result.fields["meta"][0]["label"] == "Otro"


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
    assert extra in result.unmatched


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
    assert result.fields["author"] == "Fraccionamiento Solé — El Toro"
    assert result.fields["subtitle"] == "Propuesta de Reforma al Reglamento"
