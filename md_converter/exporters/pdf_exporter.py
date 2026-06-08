"""
PDF Exporter: two backends in priority order:
  1. WeasyPrint  — renders HTML→PDF directly (needs GTK3 64-bit on Windows)
  2. docx2pdf    — converts the DOCX output to PDF via Microsoft Word COM (Windows only)

The active backend is chosen at runtime; if neither is available, export is skipped.
"""

from __future__ import annotations

import warnings
from pathlib import Path

from core.theme import Theme
from core.ast_walker import css_dict_to_string

try:
    from weasyprint import HTML as WeasyHTML, CSS as WeasyCSS
    _HAS_WEASYPRINT = True
except (ImportError, OSError):
    _HAS_WEASYPRINT = False

try:
    import docx2pdf as _docx2pdf
    _HAS_DOCX2PDF = True
except ImportError:
    _HAS_DOCX2PDF = False


class PdfExporter:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(
        self,
        html_string: str,
        output_path: Path,
        title: str = "Documento",
        docx_path: Path | None = None,
    ) -> None:
        # --- Backend 1: WeasyPrint (HTML → PDF) ---
        if _HAS_WEASYPRINT:
            extra_css = self._build_print_css(title)
            full_html = self._inject_print_css(html_string, extra_css)
            WeasyHTML(string=full_html).write_pdf(str(output_path), stylesheets=[])
            return

        # --- Backend 2: docx2pdf (DOCX → PDF via Word COM) ---
        if _HAS_DOCX2PDF and docx_path and docx_path.exists():
            try:
                _docx2pdf.convert(str(docx_path), str(output_path))
                return
            except Exception as exc:
                warnings.warn(f"docx2pdf failed ({exc}) — Word may not be installed.", stacklevel=2)

        warnings.warn(
            "PDF export skipped: no backend available.\n"
            "Option A: install GTK3 64-bit from https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer\n"
            "Option B: pip install docx2pdf  (uses Microsoft Word on Windows)",
            stacklevel=2,
        )

    # ------------------------------------------------------------------
    # Print CSS generation
    # ------------------------------------------------------------------

    def _build_print_css(self, title: str) -> str:
        meta   = self.theme.meta
        layout = self.theme.get_layout()
        pdf_styles = self.theme.get_styles().get("pdf", {})
        author = meta.get("author", "")
        lines: list[str] = []

        # Margins from layout config
        pm = layout.get("margins", {}).get("pdf", {})
        margins = [pm.get("top"), pm.get("right"), pm.get("bottom"), pm.get("left")]
        margin_rule = f"  margin: {' '.join(margins)};" if all(margins) else ""

        # Header slots from layout config
        h_cfg = layout.get("header", {})
        f_cfg = layout.get("footer", {})
        header_style = css_dict_to_string(pdf_styles.get("headerStyle", {}))
        header_right_style = css_dict_to_string(pdf_styles.get("headerRightStyle", {}))
        footer_style = css_dict_to_string(pdf_styles.get("footerStyle", {}))

        def _slot(cfg: dict, pos: str, default: str = "") -> str:
            val = cfg.get(pos, default).replace("{{meta.author}}", author).replace("{{title}}", title)
            if val == "pageNumber":
                return "counter(page) ' / ' counter(pages)"
            return f'"{val}"' if val else '""'

        page_rule = [
            "@page {",
        ]
        page_size = pdf_styles.get("page", {}).get("size")
        if page_size:
            page_rule.append(f"  size: {page_size};")
        if margin_rule:
            page_rule.append(margin_rule)

        if h_cfg.get("enabled", True):
            page_rule += [
                "  @top-left   { content: " + _slot(h_cfg, "left")   + _style_suffix(header_style) + " }",
                "  @top-center { content: " + _slot(h_cfg, "center") + _style_suffix(header_style) + " }",
                "  @top-right  { content: " + _slot(h_cfg, "right",  title) + _style_suffix(header_style, header_right_style) + " }",
            ]

        if f_cfg.get("enabled", True):
            page_rule += [
                "  @bottom-left   { content: " + _slot(f_cfg, "left")              + _style_suffix(footer_style) + " }",
                "  @bottom-center { content: " + _slot(f_cfg, "center", "pageNumber") + _style_suffix(footer_style) + " }",
                "  @bottom-right  { content: " + _slot(f_cfg, "right")             + _style_suffix(footer_style) + " }",
            ]

        page_rule.append("}")
        lines += page_rule

        # Page break rules from theme element config
        lines += self._page_break_rules()

        # H1 auto page break (driven by layout.autoPageBreakOnH1)
        if layout.get("autoPageBreakOnH1", False):
            lines += ["h1 { page-break-before: always; break-before: page; }"]

        # Manual :::pagebreak directive
        manual_style = pdf_styles.get("manualPageBreakStyle", {})
        if manual_style:
            lines.append(f".page-break {{ {css_dict_to_string(manual_style)} }}")

        for selector, css in pdf_styles.get("screenOverrides", {}).items():
            if isinstance(css, dict) and css:
                lines.append(f"{selector} {{ {css_dict_to_string(css)} }}")

        return "\n".join(lines)

    def _page_break_rules(self) -> list[str]:
        rules: list[str] = []

        selectors_to_avoid_break = self.theme.get_styles().get("pdf", {}).get("avoidBreakInside", [])
        for sel in selectors_to_avoid_break:
            rules.append(f"{sel} {{ break-inside: avoid; page-break-inside: avoid; }}")

        # Per-element overrides from theme
        element_selector_map = {
            "codeBlock":      "pre",
            "blockquote":     "blockquote",
            "horizontalRule": "hr",
        }
        for elem_name, selector in element_selector_map.items():
            cfg = self.theme.get_element(elem_name)
            pdf_cfg = cfg.get("pdf", {}) if isinstance(cfg, dict) else {}
            pb = pdf_cfg.get("pageBreak", {})
            if pb.get("inside"):
                rules.append(f"{selector} {{ break-inside: {pb['inside']}; }}")
            if pb.get("before"):
                rules.append(f"{selector} {{ break-before: {pb['before']}; }}")
            if pb.get("after"):
                rules.append(f"{selector} {{ break-after: {pb['after']}; }}")
            orphans = pdf_cfg.get("orphans")
            widows = pdf_cfg.get("widows")
            if orphans or widows:
                props = []
                if orphans:
                    props.append(f"orphans: {orphans}")
                if widows:
                    props.append(f"widows: {widows}")
                rules.append(f"{selector} {{ {'; '.join(props)}; }}")

        return rules

    @staticmethod
    def _inject_print_css(html: str, extra_css: str) -> str:
        """Insert extra CSS just before </head>."""
        inject = f"\n<style>\n{extra_css}\n</style>\n"
        if "</head>" in html:
            return html.replace("</head>", inject + "</head>", 1)
        return inject + html


def _style_suffix(*styles: str) -> str:
    props = "; ".join(style.strip().rstrip(";") for style in styles if style and style.strip())
    return f"; {props};" if props else ";"
