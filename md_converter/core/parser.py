"""
Parser: configures markdown-it-py with all required GFM plugins and returns
a parsed token stream from one or more markdown source strings.

Supported syntax:
  - CommonMark baseline
  - GFM tables (with alignment)
  - GFM task lists  (- [ ] / - [x])
  - GFM strikethrough  (~~text~~)
  - GFM alerts  (> [!NOTE], [!TIP], [!WARNING], [!CAUTION], [!IMPORTANT], [!DANGER])
  - Custom fenced divs  (::: name ... :::)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

try:
    from mdit_py_plugins.tasklists import tasklists_plugin
    _HAS_TASKLISTS = True
except ImportError:
    _HAS_TASKLISTS = False

try:
    from mdit_py_plugins.container import container_plugin
    _HAS_CONTAINER = True
except ImportError:
    _HAS_CONTAINER = False

# GitHub-style alerts are parsed manually since mdit_py_plugins.alerts
# may not cover all six types. We post-process blockquote tokens instead.
_ALERT_RE = re.compile(r"^\[!(NOTE|TIP|WARNING|CAUTION|IMPORTANT|DANGER)\]", re.IGNORECASE)
_PAGEBREAK_RE = re.compile(r"<!--\s*(pagebreak|breakpage)\s*-->", re.IGNORECASE)

# Directive names we've registered — populated dynamically
_REGISTERED_DIRECTIVES: set[str] = set()


def build_parser(directives: list[str] | None = None) -> MarkdownIt:
    """Build and return a fully configured MarkdownIt instance."""
    md = (
        MarkdownIt("commonmark", {"typographer": False, "html": True})
        .enable("table")
        .enable("strikethrough")
    )

    if _HAS_TASKLISTS:
        md.use(tasklists_plugin)
    else:
        import warnings
        warnings.warn("mdit_py_plugins.tasklists not available — task lists will render as plain lists.")

    if _HAS_CONTAINER:
        # Register standard directives from theme
        if directives:
            for name in directives:
                md.use(container_plugin, name=name)
        
        # Also register a wildcard-style container that accepts any name with 'directive' prefix.
        def _any_name(info: str, *args) -> bool:
            name = info.strip().split()[0] if info.strip() else ""
            return bool(re.match(r"^[a-z][a-z0-9\-_]*$", name))

        md.use(container_plugin, name="directive", validate=_any_name)
    else:
        import warnings
        warnings.warn("mdit_py_plugins.container not available — ::: directives will not be processed.")

    return md


def parse(sources: list[tuple[Path, str]], directives: list[str] | None = None) -> list[Token]:
    """
    Parse one or more (path, text) pairs into a flat token list.
    Sources are concatenated with a horizontal rule separator so that
    section boundaries are visible in the output.
    """
    md = build_parser(directives)
    combined_tokens: list[Token] = []

    for i, (path, text) in enumerate(sources):
        tokens = md.parse(text)
        tokens = _post_process_alerts(tokens)
        tokens = _post_process_pagebreaks(tokens)
        tokens = _annotate_source(tokens, path)
        if i > 0:
            # Insert an hr token between documents
            hr = Token("hr", "hr", 0)
            hr.attrSet("class", "document-separator")
            combined_tokens.append(hr)
        combined_tokens.extend(tokens)

    combined_tokens = _tag_no_page_break_on_headings(combined_tokens)
    return combined_tokens


def parse_inline(text: str) -> list[Token]:
    """Parse a single markdown string (no source annotation)."""
    md = build_parser()
    tokens = md.parse(text)
    return _post_process_alerts(tokens)


# ------------------------------------------------------------------
# Alert post-processing
# ------------------------------------------------------------------

def _post_process_alerts(tokens: list[Token]) -> list[Token]:
    """
    Convert blockquote tokens that start with [!TYPE] into callout tokens.

    Before:
        blockquote_open
          inline  → "[!WARNING]\nsome text"
        blockquote_close

    After:
        callout_open   (meta: {"type": "warning"})
          inline  → "some text"
        callout_close
    """
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "blockquote_open":
            # Peek at first inline inside to detect alert marker
            alert_type, end_idx = _detect_alert(tokens, i)
            if alert_type:
                open_tok = Token("callout_open", "div", 1)
                open_tok.attrSet("class", f"callout callout-{alert_type}")
                open_tok.meta = {"type": alert_type}
                open_tok.map = tok.map
                result.append(open_tok)

                # Collect inner tokens, stripping the [!TYPE] marker line
                inner = _strip_alert_marker(tokens[i + 1 : end_idx])
                result.extend(inner)

                close_tok = Token("callout_close", "div", -1)
                result.append(close_tok)
                i = end_idx + 1
                continue
        result.append(tok)
        i += 1
    return result


def _detect_alert(tokens: list[Token], bq_open_idx: int) -> tuple[str | None, int]:
    """
    Look for [!TYPE] in the first inline token inside a blockquote.
    Returns (alert_type_lower, blockquote_close_idx) or (None, -1).
    """
    depth = 0
    for j in range(bq_open_idx, len(tokens)):
        t = tokens[j]
        if t.type == "blockquote_open":
            depth += 1
        elif t.type == "blockquote_close":
            depth -= 1
            if depth == 0:
                # Scan backwards to find the first inline
                for k in range(bq_open_idx + 1, j):
                    if tokens[k].type == "inline" and tokens[k].content:
                        m = _ALERT_RE.match(tokens[k].content.strip())
                        if m:
                            return m.group(1).lower(), j
                return None, -1
    return None, -1


def _strip_alert_marker(tokens: list[Token]) -> list[Token]:
    """Remove the [!TYPE] prefix from the first inline token (content + children)."""
    result = list(tokens)
    for tok in result:
        if tok.type == "inline" and tok.content:
            if not _ALERT_RE.match(tok.content.strip()):
                continue
            tok.content = _ALERT_RE.sub("", tok.content.strip()).strip()
            # Also update children — the renderer uses tok.children, not tok.content
            if tok.children:
                new_children = []
                skip_next_softbreak = False
                for child in tok.children:
                    if skip_next_softbreak and child.type == "softbreak":
                        skip_next_softbreak = False
                        continue
                    if child.type == "text" and _ALERT_RE.match(child.content.strip()):
                        child_stripped = _ALERT_RE.sub("", child.content.strip()).strip()
                        skip_next_softbreak = True
                        if child_stripped:
                            child.content = child_stripped
                            new_children.append(child)
                        # else: drop the now-empty text node
                    else:
                        new_children.append(child)
                tok.children = new_children
            break
    return result


def _post_process_pagebreaks(tokens: list[Token]) -> list[Token]:
    """
    Convert :::pagebreak and :::breakpage directives (and <!-- pagebreak --> or <!-- breakpage --> comments) to
    a single self‑closing pagebreak token, removing the paired open/close.
    Preserve any inner tokens and handle orphan containers gracefully.
    """
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        # Skip closing token of a pagebreak container if we encounter it directly
        if tok.type.startswith("container_") and tok.type.endswith("_close"):
            name = tok.type.replace("container_", "").replace("_close", "")
            if name in ("pagebreak", "breakpage"):
                i += 1
                continue
        # Check if it's a pagebreak or breakpage container opening
        is_pb_container = False
        name = None
        if tok.type.startswith("container_") and tok.type.endswith("_open"):
            name = tok.type.replace("container_", "").replace("_open", "")
            if name in ("pagebreak", "breakpage"):
                is_pb_container = True
            elif name == "directive" and _is_pagebreak_info(tok.info):
                is_pb_container = True
        if is_pb_container:
            # Look ahead to see if an H1 follows directly (skip intermediate containers)
            next_idx = i + 1
            while next_idx < len(tokens) and tokens[next_idx].type.startswith("container_"):
                next_idx += 1
            next_tok = tokens[next_idx] if next_idx < len(tokens) else None
            is_h1_heading = next_tok is not None and next_tok.type == "heading_open" and next_tok.tag == "h1"
            if not is_h1_heading:
                result.append(Token("pagebreak", "", 0))
            # Skip the opening token only
            i += 1
            continue
        # Backwards‑compatible HTML comment pagebreaks
        if tok.type in ("html_block", "html_inline") and _PAGEBREAK_RE.search(tok.content):
            next_idx = i + 1
            next_tok = tokens[next_idx] if next_idx < len(tokens) else None
            is_h1_heading = next_tok is not None and next_tok.type == "heading_open" and next_tok.tag == "h1"
            if not is_h1_heading:
                result.append(Token("pagebreak", "", 0))
            i += 1
            continue
        # Default: keep token as‑is
        result.append(tok)
        i += 1
    return result
    """
    Convert :::pagebreak and :::breakpage directives (and <!-- pagebreak --> or <!-- breakpage --> comments) to
    a single self-closing pagebreak token, removing the paired open/close.
    """
    result: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        
        # Check if it's a pagebreak or breakpage container
        is_pb_container = False
        name = None
        if tok.type.startswith("container_") and tok.type.endswith("_open"):
            name = tok.type.replace("container_", "").replace("_open", "")
            if name in ("pagebreak", "breakpage"):
                is_pb_container = True
            elif name == "directive" and _is_pagebreak_info(tok.info):
                is_pb_container = True
        
        if is_pb_container:
            # Look ahead to see if an H1 follows directly (skip intermediate containers)
            next_idx = i + 1
            while next_idx < len(tokens) and tokens[next_idx].type.startswith("container_"):
                next_idx += 1
            next_tok = tokens[next_idx] if next_idx < len(tokens) else None
            is_h1_heading = next_tok is not None and next_tok.type == "heading_open" and next_tok.tag == "h1"
            if not is_h1_heading:
                result.append(Token("pagebreak", "", 0))
            # Advance i past the opening token
            i += 1
            if i < len(tokens) and tokens[i].type == f"container_{name}_close":
                # Skip the close token
                i += 1
        
        # Backwards‑compatible HTML comment pagebreaks
        if tok.type in ("html_block", "html_inline") and _PAGEBREAK_RE.search(tok.content):
            next_idx = i + 1
            next_tok = tokens[next_idx] if next_idx < len(tokens) else None
            is_h1_heading = next_tok is not None and next_tok.type == "heading_open" and next_tok.tag == "h1"
            if not is_h1_heading:
                result.append(Token("pagebreak", "", 0))
            i += 1
            continue
        
        # Default: keep token as‑is
        result.append(tok)
        i += 1
    return result


def _is_pagebreak_info(info: str | None) -> bool:
    return bool(info and info.strip().split()[0].lower() in ("pagebreak", "breakpage"))


# ------------------------------------------------------------------
# Source annotation
# ------------------------------------------------------------------

def _annotate_source(tokens: list[Token], path: Path) -> list[Token]:
    """Tag every token with its source file path for error reporting."""
    for tok in tokens:
        if not hasattr(tok, "meta") or tok.meta is None:
            tok.meta = {}
        if isinstance(tok.meta, dict):
            tok.meta["_source"] = str(path)
    return tokens


def _tag_no_page_break_on_headings(tokens: list[Token]) -> list[Token]:
    """
    If a heading_open (tag h1) immediately follows a pagebreak token
    (with only comments, whitespace, or document-separator hr in between),
    tag it with meta['noPageBreak'] = True to prevent double page breaks.
    """
    for i, tok in enumerate(tokens):
        if tok.type == "pagebreak":
            for j in range(i + 1, len(tokens)):
                t = tokens[j]
                # Skip comments
                if t.type in ("html_block", "html_inline") and t.content.strip().startswith("<!--") and t.content.strip().endswith("-->"):
                    continue
                # Skip empty inline
                if t.type == "inline" and not t.content.strip():
                    continue
                # Skip document separator hr
                if t.type == "hr" and t.attrGet("class") == "document-separator":
                    continue
                # If H1 heading_open, tag it
                if t.type == "heading_open" and t.tag == "h1":
                    if not hasattr(t, "meta") or t.meta is None:
                        t.meta = {}
                    t.meta["noPageBreak"] = True
                    break
                # Any other token stops the scan
                break
    return tokens
