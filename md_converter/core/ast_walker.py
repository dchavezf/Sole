"""
AST walker utilities shared by all exporters.

markdown-it-py produces a flat token list (not a tree). These helpers
provide iteration patterns and token inspection used by html_exporter
and docx_exporter to avoid duplicating traversal logic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator
from markdown_it.token import Token

_DIRECTIVE_NAME_RE = re.compile(r"^directive\s+(\S+)")


@dataclass
class Block:
    """A paired open/close token with all inner tokens."""
    open: Token
    close: Token
    children: list["Block | Token"] = field(default_factory=list)


def iter_blocks(tokens: list[Token]) -> Iterator[Block | Token]:
    """
    Yield top-level Blocks (for paired open/close tokens) or bare Tokens
    (for self-closing tokens like hr, fence, inline).

    Blocks are nested: a block's children list contains inner Blocks or Tokens.
    """
    yield from _parse_level(tokens, 0)[0]


def _parse_level(tokens: list[Token], start: int) -> tuple[list[Block | Token], int]:
    result: list[Block | Token] = []
    i = start
    while i < len(tokens):
        tok = tokens[i]
        if tok.nesting == 1:  # open
            block = Block(open=tok, close=Token("__placeholder__", "", -1))
            inner, end = _parse_level(tokens, i + 1)
            block.children = inner
            if end < len(tokens):
                block.close = tokens[end]
            result.append(block)
            i = end + 1
        elif tok.nesting == -1:  # close — signals end of current level
            return result, i
        else:  # self-closing (nesting == 0)
            result.append(tok)
            i += 1
    return result, i


# ------------------------------------------------------------------
# Token inspection helpers
# ------------------------------------------------------------------

def token_type(tok: Token) -> str:
    return tok.type


def is_heading(tok: Token) -> bool:
    return tok.type == "heading_open"


def heading_level(tok: Token) -> int:
    """Extract 1..6 from 'h1'..'h6' tag."""
    return int(tok.tag[1]) if tok.tag and tok.tag[0] == "h" else 1


def is_callout(block: Block) -> bool:
    return block.open.type == "callout_open"


def callout_type(block: Block) -> str:
    meta = block.open.meta or {}
    return meta.get("type", "note")


def is_directive(block: Block) -> bool:
    return block.open.type.startswith("container_") or block.open.type == "container_open"


def directive_name(block: Block) -> str:
    """Extract directive name from token info or token type."""
    # mdit-py-plugins container uses 'container_name_open' as type
    if block.open.type.startswith("container_") and block.open.type.endswith("_open"):
        name = block.open.type.replace("container_", "").replace("_open", "")
        if name != "directive":
             return name

    info = block.open.info or ""
    m = _DIRECTIVE_NAME_RE.match(info.strip())
    if m:
        return m.group(1)
    # Fallback: first word of info
    return info.strip().split()[0] if info.strip() else "unknown"


def is_table(block: Block) -> bool:
    return block.open.type == "table_open"


def is_task_list(block: Block) -> bool:
    if block.open.type != "bullet_list_open":
        return False
    return any(
        isinstance(c, Block) and c.open.type == "list_item_open"
        and _has_checkbox(c)
        for c in block.children
    )


def _has_checkbox(item_block: Block) -> bool:
    for child in item_block.children:
        if isinstance(child, Token) and child.type == "inline":
            if child.content.startswith("[ ]") or child.content.startswith("[x]"):
                return True
    return False


def get_inline_text(tok: Token) -> str:
    """Return plain text from an inline token, stripping markdown syntax."""
    if tok.type != "inline":
        return ""
    return tok.content


def first_inline(block: Block) -> Token | None:
    """Return the first inline token inside a block."""
    for child in block.children:
        if isinstance(child, Token) and child.type == "inline":
            return child
        if isinstance(child, Block):
            found = first_inline(child)
            if found:
                return found
    return None


def css_dict_to_string(css: dict) -> str:
    """Convert a cssProperties dict to an inline style string."""
    parts = []
    for k, v in css.items():
        # Convert camelCase to kebab-case
        prop = re.sub(r"([A-Z])", lambda m: f"-{m.group(1).lower()}", k)
        parts.append(f"{prop}: {v}")
    return "; ".join(parts)


def merge_css_classes(*class_values) -> str:
    """Merge multiple className values (str or list[str]) into a single string."""
    classes: list[str] = []
    for cv in class_values:
        if isinstance(cv, str) and cv:
            classes.extend(cv.split())
        elif isinstance(cv, list):
            classes.extend(c for c in cv if c)
    return " ".join(dict.fromkeys(classes))  # deduplicate, preserve order
