#!/usr/bin/env python3
"""
md_converter — Markdown Multi-Format Renderer
============================================

Usage:
    python md_converter.py --input <file.md|folder/|index.md> \
                           --theme theme-config.json \
                           --output [all|html|pdf|docx] \
                           [--output-dir ruta/destino] \
                           [--title "Título del documento"]

Output destination priority:
    1. --output-dir CLI argument
    2. meta.outputDir in theme JSON
    3. Same directory as the first input file
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

# Allow running as `python md_converter.py` from inside the md_converter/ dir
# or as `python -m md_converter.md_converter` from the parent dir.
_pkg_dir = Path(__file__).parent          # .../md_converter/
_root_dir = _pkg_dir.parent               # .../Sole/
if str(_pkg_dir) not in sys.path:
    sys.path.insert(0, str(_pkg_dir))
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))

from core.resolver import resolve_input, resolve_output_dir, output_stem
from core.parser import parse
from core.theme import load_theme, ThemeError
from exporters.html_exporter import HtmlExporter
from exporters.pdf_exporter import PdfExporter
from exporters.docx_exporter import DocxExporter


def main() -> int:
    args = _parse_args()

    # ------------------------------------------------------------------ #
    # 1. Load theme
    # ------------------------------------------------------------------ #
    try:
        theme = load_theme(args.theme)
    except ThemeError as exc:
        _err(f"Theme error: {exc}")
        return 1

    # ------------------------------------------------------------------ #
    # 2. Resolve input sources
    # ------------------------------------------------------------------ #
    try:
        sources = resolve_input(args.input)
    except Exception as exc:
        _err(f"Input error: {exc}")
        return 1

    _info(f"Processing {len(sources)} source file(s)...")

    # ------------------------------------------------------------------ #
    # 3. Parse
    # ------------------------------------------------------------------ #
    try:
        directives = list(theme.get_all_directives().keys())
        tokens = parse(sources, directives=directives)
    except Exception as exc:
        _err(f"Parse error: {exc}")
        if args.verbose:
            traceback.print_exc()
        return 1

    # ------------------------------------------------------------------ #
    # 4. Resolve output directory and base filename
    # ------------------------------------------------------------------ #
    theme_out_dir = theme.meta.get("outputDir")
    out_dir = resolve_output_dir(args.input, args.output_dir, theme_out_dir)
    stem = output_stem(sources, Path(args.input))
    title = args.title or theme.meta.get("name") or stem

    _info(f"Output directory: {out_dir}")

    # ------------------------------------------------------------------ #
    # 5. Export
    # ------------------------------------------------------------------ #
    formats = _resolve_formats(args.output)
    html_string: str | None = None
    docx_out_path: Path | None = None

    if "html" in formats or "pdf" in formats:
        html_exp = HtmlExporter(theme)
        html_string = html_exp.render_to_string(tokens, title=title)

        if "html" in formats:
            out_path = out_dir / f"{stem}.html"
            html_exp.export(tokens, out_path, title=title)
            _ok(f"HTML  -> {out_path}")

    if "docx" in formats or "pdf" in formats:
        first_source_path = sources[0][0] if sources else Path(args.input)
        docx_exp = DocxExporter(theme, base_dir=first_source_path.parent)
        docx_out_path = out_dir / f"{stem}.docx"
        docx_exp.export(tokens, docx_out_path, title=title)
        if "docx" in formats:
            _ok(f"DOCX  -> {docx_out_path}")

    if "pdf" in formats:
        if html_string is None:
            _err("HTML string not available for PDF export.")
            return 1
        pdf_exp = PdfExporter(theme)
        out_path = out_dir / f"{stem}.pdf"
        pdf_exp.export(html_string, out_path, title=title, docx_path=docx_out_path)
        if out_path.exists():
            _ok(f"PDF   -> {out_path}")
        else:
            _err("PDF skipped — install GTK3 64-bit or run: pip install docx2pdf")

    return 0


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Markdown to HTML, PDF and/or DOCX using a theme JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to a .md file, a folder of .md files, or an index .md with !include directives.",
    )
    parser.add_argument(
        "--theme", "-t", required=True,
        help="Path to a theme-config.json validated against the schema.",
    )
    parser.add_argument(
        "--output", "-o", default="all",
        choices=["all", "html", "pdf", "docx"],
        help="Output format(s). 'all' generates HTML + PDF + DOCX. Default: all.",
    )
    parser.add_argument(
        "--output-dir", "-d", default=None,
        help="Destination directory for output files. Overrides theme and auto-detection.",
    )
    parser.add_argument(
        "--title", default=None,
        help="Document title used in HTML <title>, PDF header, and DOCX properties.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print full tracebacks on errors.",
    )
    return parser.parse_args()


def _resolve_formats(output_arg: str) -> list[str]:
    if output_arg == "all":
        return ["html", "pdf", "docx"]
    return [output_arg]


def _info(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
