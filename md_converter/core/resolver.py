"""
Input resolver: detects which of the three input modes is being used and
returns an ordered list of (Path, str) tuples — (source_file, markdown_text).

Modes:
  1. Index file  — a .md whose first non-blank lines contain !include directives
  2. Single file — any other .md file
  3. Folder      — a directory; all .md files sorted alphabetically
"""

from __future__ import annotations

import re
from pathlib import Path

_INCLUDE_RE = re.compile(r"^!include\s+(.+)$", re.MULTILINE)
_INCLUDE_MARKER = "!include"


class ResolverError(Exception):
    pass


def resolve_input(input_path: str | Path) -> list[tuple[Path, str]]:
    """
    Returns a list of (Path, markdown_text) in the order they should be processed.
    All paths are absolute.
    """
    p = Path(input_path).resolve()

    if not p.exists():
        raise ResolverError(f"Input path does not exist: {p}")

    if p.is_dir():
        return _resolve_folder(p)

    if p.is_file() and p.suffix.lower() == ".md":
        text = p.read_text(encoding="utf-8")
        if _is_index_file(text):
            return _resolve_index(p, text)
        return [(p, text)]

    raise ResolverError(f"Input must be a .md file or a directory, got: {p}")


# ------------------------------------------------------------------
# Mode 1 — Index file
# ------------------------------------------------------------------

def _is_index_file(text: str) -> bool:
    """An index file has at least one !include directive."""
    return bool(_INCLUDE_RE.search(text))


def _resolve_index(index_path: Path, text: str) -> list[tuple[Path, str]]:
    """
    Parse all !include <relative_path> directives in order.
    Non-include lines before the first directive are treated as a preamble
    and prepended to the first included file's content.

    Syntax:
        !include path/to/file.md
        !include ../other/doc.md
    """
    base_dir = index_path.parent
    results: list[tuple[Path, str]] = []
    preamble_lines: list[str] = []
    found_first_include = False

    for line in text.splitlines(keepends=True):
        m = _INCLUDE_RE.match(line.rstrip())
        if m:
            found_first_include = True
            rel = m.group(1).strip()
            target = (base_dir / rel).resolve()
            if not target.exists():
                raise ResolverError(f"!include target not found: {target} (referenced from {index_path})")
            if not target.suffix.lower() == ".md":
                raise ResolverError(f"!include target must be a .md file: {target}")
            content = target.read_text(encoding="utf-8")
            if preamble_lines:
                content = "".join(preamble_lines) + "\n\n" + content
                preamble_lines = []
            results.append((target, content))
        elif not found_first_include:
            preamble_lines.append(line)

    if not results:
        raise ResolverError(f"Index file contains no valid !include directives: {index_path}")

    return results


# ------------------------------------------------------------------
# Mode 3 — Folder
# ------------------------------------------------------------------

def _resolve_folder(folder: Path) -> list[tuple[Path, str]]:
    """
    Collect all .md files in the folder (non-recursive) sorted alphabetically.
    Alphabetical sort works well with numeric prefixes like Sole_02_01_*.md.
    """
    files = sorted(folder.glob("*.md"), key=lambda f: f.name.lower())
    if not files:
        raise ResolverError(f"No .md files found in folder: {folder}")
    return [(f, f.read_text(encoding="utf-8")) for f in files]


# ------------------------------------------------------------------
# Output path resolution
# ------------------------------------------------------------------

def resolve_output_dir(
    input_path: str | Path,
    cli_output_dir: str | Path | None,
    theme_output_dir: str | None,
) -> Path:
    """
    Priority: --output-dir CLI arg > theme meta.outputDir > same dir as first input file.
    """
    if cli_output_dir:
        p = Path(cli_output_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    if theme_output_dir:
        p = Path(theme_output_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    p = Path(input_path).resolve()
    return p if p.is_dir() else p.parent


def output_stem(sources: list[tuple[Path, str]], input_path: Path) -> str:
    """
    Derive the base filename (without extension) for the output files.
    - Folder or index mode → use the folder/index file name
    - Single file → use the file stem
    """
    if len(sources) == 1:
        return sources[0][0].stem
    p = Path(input_path).resolve()
    return p.stem if p.is_file() else p.name
