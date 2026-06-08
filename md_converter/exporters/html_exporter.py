"""
HTML Exporter: renders a markdown-it token list to a self-contained HTML5 file.

CSS is generated entirely from the theme JSON â€” no hardcoded styles anywhere.
The Jinja2 template (base.html.jinja2) provides the outer HTML shell.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
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

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_CALLOUT_DEFAULT_ICONS = {
    "note":      "â„¹ï¸",
    "tip":       "ðŸ’¡",
    "warning":   "âš ï¸",
    "caution":   "ðŸ”´",
    "important": "â—",
    "danger":    "ðŸš¨",
}
_CALLOUT_DEFAULT_LABELS = {
    "note":      "Nota",
    "tip":       "Consejo",
    "warning":   "Advertencia",
    "caution":   "PrecauciÃ³n",
    "important": "Importante",
    "danger":    "Peligro",
}


class HtmlExporter:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self._jinja = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=False,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, tokens: list[Token], output_path: Path, title: str = "Documento") -> None:
        css = self._generate_css()
        body = self._render_tokens(tokens)
        meta = self.theme.meta
        html = self._jinja.get_template("base.html.jinja2").render(
            title=title,
            author=meta.get("author", ""),
            description=meta.get("description", ""),
            lang="es",
            css=css,
            body=body,
        )
        output_path.write_text(html, encoding="utf-8")

    def render_to_string(self, tokens: list[Token], title: str = "Documento") -> str:
        """Return full HTML string without writing to disk (used by PDF exporter)."""
        css = self._generate_css()
        body = self._render_tokens(tokens)
        meta = self.theme.meta
        return self._jinja.get_template("base.html.jinja2").render(
            title=title,
            author=meta.get("author", ""),
            description=meta.get("description", ""),
            lang="es",
            css=css,
            body=body,
        )

    # ------------------------------------------------------------------
    # CSS generation
    # ------------------------------------------------------------------

    def _generate_css(self) -> str:
        lines: list[str] = []

        variables = self.theme.get_variables()
        styles = self.theme.get_styles()

        lines.append(":root {")
        for name, val in variables.get("colors", {}).items():
            lines.append(f"  --{name}: {val};")
        for name, val in variables.get("fonts", {}).items():
            lines.append(f"  --font-{name}: {val};")
        for name, val in variables.get("spacing", {}).items():
            lines.append(f"  --space-{name}: {val};")
        for name, val in variables.get("borders", {}).items():
            lines.append(f"  --border-{name}: {val};")
        for name, val in styles.get("tokens", {}).items():
            lines.append(f"  --{name}: {val};")
        lines.append("}")

        for selector, css in styles.get("selectors", {}).items():
            if isinstance(css, dict) and css:
                lines.append(f"{selector} {{ {css_dict_to_string(css)} }}")

        # Standard elements
        for level in range(1, 7):
            cfg = self.theme.get_heading(level)
            html_cfg = cfg.get("html", {})
            css = html_cfg.get("style", {})
            if css:
                lines.append(f"h{level} {{ {css_dict_to_string(css)} }}")

        element_selectors = {
            "paragraph":      "p",
            "blockquote":     "blockquote",
            "horizontalRule": "hr",
        }
        for elem_name, selector in element_selectors.items():
            cfg = self.theme.get_element(elem_name)
            css = cfg.get("html", {}).get("style", {})
            if css:
                lines.append(f"{selector} {{ {css_dict_to_string(css)} }}")

        # Inline elements
        inline_selectors = {
            "emphasis":     "em",
            "strong":       "strong",
            "strikethrough": "s",
            "inlineCode":   "code:not(pre code)",
        }
        for elem_name, selector in inline_selectors.items():
            cfg = self.theme.get_element(elem_name)
            css = cfg.get("html", {}).get("style", {})
            if css:
                lines.append(f"{selector} {{ {css_dict_to_string(css)} }}")

        # Code blocks
        cb = self.theme.get_element("codeBlock")
        pre_css = cb.get("pre", {}).get("html", {}).get("style", {})
        code_css = cb.get("code", {}).get("html", {}).get("style", {})
        if pre_css:
            lines.append(f"pre {{ {css_dict_to_string(pre_css)} }}")
        if code_css:
            lines.append(f"pre code {{ {css_dict_to_string(code_css)} }}")

        # Tables
        table_parts = {
            "table":          ".md-table",
            "container":      ".md-table-container",
            "thead":          ".md-table thead",
            "tbody":          ".md-table tbody",
            "th":             ".md-table th",
            "td":             ".md-table td",
            "trAlternate":    ".md-table tbody tr:nth-child(even)",
        }
        for part, selector in table_parts.items():
            cfg = self.theme.get_table_part(part if part != "table" else "container")
            if part == "table":
                cfg = self.theme.get_element("table")
                css = cfg.get("html", {}).get("style", {}) if isinstance(cfg, dict) else {}
            else:
                css = cfg.get("html", {}).get("style", {}) if isinstance(cfg, dict) else {}
            if css:
                lines.append(f"{selector} {{ {css_dict_to_string(css)} }}")

        # Callouts base
        base_html = self.theme.get_element("callout").get("base", {}).get("html", {})
        base_css = base_html.get("style", {})
        if base_css:
            lines.append(f".callout {{ {css_dict_to_string(base_css)} }}")

        # Callout variants
        for ct in ("note", "tip", "warning", "caution", "important", "danger"):
            cfg = self.theme.get_callout(ct)
            html_cfg = cfg.get("html", {})
            css = html_cfg.get("style", {})
            if css:
                lines.append(f".callout-{ct} {{ {css_dict_to_string(css)} }}")

        # Callout title and body
        title_css = self.theme.get_callout_title().get("html", {}).get("style", {})
        if title_css:
            lines.append(f".callout-title {{ {css_dict_to_string(title_css)} }}")
        body_css = self.theme.get_callout_body().get("html", {}).get("style", {})
        if body_css:
            lines.append(f".callout-body {{ {css_dict_to_string(body_css)} }}")

        # Custom directives
        for name, cfg in self.theme.get_all_directives().items():
            html_cfg = cfg.get("html", {})
            css = html_cfg.get("style", {})
            if css:
                lines.append(f".directive-{name} {{ {css_dict_to_string(css)} }}")

        # Task list checkboxes
        tl = self.theme.get_element("taskList")
        cb_html = tl.get("checkbox", {}).get("html", {}) if isinstance(tl, dict) else {}
        cb_style = cb_html.get("style", {})
        if cb_style:
            lines.append(f".task-list-item input[type=checkbox] {{ {css_dict_to_string(cb_style)} }}")

        # Links
        link = self.theme.get_element("link")
        link_html = link.get("html", {}) if isinstance(link, dict) else {}
        if link_html.get("style"):
            lines.append(f"a {{ {css_dict_to_string(link_html['style'])} }}")
        if link_html.get("hoverStyle"):
            lines.append(f"a:hover {{ {css_dict_to_string(link_html['hoverStyle'])} }}")
        if link_html.get("visitedStyle"):
            lines.append(f"a:visited {{ {css_dict_to_string(link_html['visitedStyle'])} }}")

        # Images
        img = self.theme.get_element("image")
        img_css = img.get("img", {}).get("html", {}).get("style", {}) if isinstance(img, dict) else {}
        max_w = img.get("maxWidth") if isinstance(img, dict) else None
        if img_css or max_w:
            style = css_dict_to_string(img_css)
            if max_w:
                style += f"; max-width: {max_w}"
            lines.append(f"img {{ {style.strip('; ')} }}")

        extra_css = self.theme.get_extra_css()
        if extra_css:
            lines.append(extra_css)

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Token rendering
    # ------------------------------------------------------------------

    def _render_tokens(self, tokens: list[Token]) -> str:
        """Render tokens using a tree-based walker for better control."""
        output: list[str] = []
        for item in iter_blocks(tokens):
            output.append(self._render_item(item))
        return "".join(output)

    def _render_item(self, item: Block | Token) -> str:
        if isinstance(item, Token):
            return self._render_token(item)
        else:
            return self._render_block(item)

    def _render_token(self, tok: Token) -> str:
        # Standard markdown-it-py renderer for simple tokens
        md = MarkdownIt()
        # We need to render it as a list to avoid md.render(tok.content) which parses again
        return md.renderer.render([tok], md.options, {})

    def _render_block(self, block: Block) -> str:
        if is_heading(block.open):
            return self._render_heading(block)
        elif is_callout(block):
            return self._render_callout(block)
        elif is_directive(block):
            return self._render_directive(block)
        elif is_table(block):
            return self._render_table(block)
        
        # Default: render open tag, children, then close tag
        md = MarkdownIt()
        res = [md.renderer.render([block.open], md.options, {})]
        for child in block.children:
            res.append(self._render_item(child))
        res.append(md.renderer.render([block.close], md.options, {}))
        return "".join(res)

    # ------------------------------------------------------------------
    # Specialized Renderers
    # ------------------------------------------------------------------

    def _render_heading(self, block: Block) -> str:
        level = heading_level(block.open)
        cfg = self.theme.get_heading(level)
        html_cfg = cfg.get("html", {})
        tag = html_cfg.get("tag", f"h{level}")
        class_attr = ""
        classes = merge_css_classes(html_cfg.get("className", ""))
        if classes:
            class_attr = f' class="{classes}"'
        
        content = "".join(self._render_item(c) for c in block.children)
        return f'<{tag}{class_attr}>{content}</{tag}>\n'

    def _render_callout(self, block: Block) -> str:
        ct = callout_type(block)
        cfg = self.theme.get_callout(ct)
        icon_cfg = cfg.get("icon", {})
        icon_html = icon_cfg.get("html") or icon_cfg.get("unicode") or _CALLOUT_DEFAULT_ICONS.get(ct, "")
        label = cfg.get("label") or _CALLOUT_DEFAULT_LABELS.get(ct, ct.upper())

        body = "".join(self._render_item(c) for c in block.children)
        return (
            f'<div class="callout callout-{ct}">\n'
            f'  <div class="callout-title">{icon_html} {label}</div>\n'
            f'  <div class="callout-body">\n{body}</div>\n'
            f'</div>\n'
        )

    def _render_directive(self, block: Block) -> str:
        name = directive_name(block)
        
        if name == "card-propuesta":
            return self._render_card_propuesta(block)
        if name == "caso":
            return self._render_caso(block)
        if name == "cover":
            return self._render_cover(block)
        if name == "pagebreak":
            return '<div class="page-break"></div>\n'
            
        cfg = self.theme.get_directive(name)
        html_cfg = cfg.get("html", {})
        tag = html_cfg.get("tag", "div")
        base_cls = merge_css_classes(f"directive directive-{name}", html_cfg.get("className", ""))
        
        label = cfg.get("label", "")
        icon_cfg = cfg.get("icon", {})
        icon = icon_cfg.get("html") or icon_cfg.get("unicode") or ""
        header = f'  <div class="directive-header">{icon} {label}</div>\n' if (label or icon) else ""
        
        body = "".join(self._render_item(c) for c in block.children)
        return f'<{tag} class="{base_cls}">\n{header}{body}</{tag}>\n'

    def _render_table(self, block: Block) -> str:
        res = ['<div class="md-table-container">\n<table class="md-table">\n']
        for child in block.children:
            res.append(self._render_item(child))
        res.append("</table>\n</div>\n")
        return "".join(res)

    # ------------------------------------------------------------------
    # Card Components Logic
    # ------------------------------------------------------------------

    def _render_card_propuesta(self, block: Block) -> str:
        """Specialized renderer for the 'card-propuesta' component."""
        title = ""
        para_quien = ""
        sabras = ""
        body_parts = []
        
        # Extract lines
        for child in block.children:
            if isinstance(child, Block) and is_heading(child.open):
                title = "".join(self._render_item(c) for c in child.children).strip()
                continue
            
            text = ""
            if isinstance(child, Block):
                inline = first_inline(child)
                if inline: text = inline.content
            elif isinstance(child, Token) and child.type == "inline":
                text = child.content
            
            if text:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                remaining_lines = []
                for line in lines:
                    if line.startswith("**Para quiÃ©n:**"):
                        para_quien = line.replace("**Para quiÃ©n:**", "").strip()
                    elif line.startswith("**Al terminar esta parte sabrÃ¡s:**"):
                        sabras = line.replace("**Al terminar esta parte sabrÃ¡s:**", "").strip()
                    else:
                        remaining_lines.append(line)
                if remaining_lines:
                    # Re-render the non-field lines as paragraphs or just text
                    body_parts.append("<p>" + " ".join(remaining_lines) + "</p>")
            else:
                # Other tokens (not inlines/paragraphs)
                body_parts.append(self._render_item(child))

        body_html = "".join(body_parts)
        
        import re
        m = re.search(r"Parte\s+(\d+)", title, re.I)
        part_num = m.group(1) if m else "01"
        if len(part_num) == 1: part_num = "0" + part_num

        return (
            f'<article class="md-card card-propuesta">\n'
            f'  <div class="cp-inner">\n'
            f'    <div class="cp-top">\n'
            f'      <h2>{title}</h2>\n'
            f'      <span class="cp-chip">Parte {part_num}</span>\n'
            f'    </div>\n'
            f'    <div class="cp-para-quien">\n'
            f'      <span class="cp-pq-label">Para quiÃ©n</span>\n'
            f'      <span class="cp-pq-text">{para_quien}</span>\n'
            f'    </div>\n'
            f'    <div class="cp-body">{body_html}</div>\n'
            f'  </div>\n'
            f'  <footer class="cp-footer">\n'
            f'    <div class="cp-footer-icon">\n'
            f'      <svg width="13" height="13" viewBox="0 0 13 13" fill="none">\n'
            f'        <path d="M6.5 1L8.2 4.5L12 5.1L9.25 7.8L9.9 11.6L6.5 9.8L3.1 11.6L3.75 7.8L1 5.1L4.8 4.5L6.5 1Z" fill="currentColor"/>\n'
            f'      </svg>\n'
            f'    </div>\n'
            f'    <div class="cp-footer-content">\n'
            f'      <div class="cp-footer-label">Al terminar esta parte sabrÃ¡s</div>\n'
            f'      <p class="cp-footer-text">{sabras}</p>\n'
            f'    </div>\n'
            f'  </footer>\n'
            f'</article>\n'
        )

    def _render_caso(self, block: Block) -> str:
        """Specialized renderer for the 'caso' component."""
        case_title = ""
        steps = [] # list of (label, text)
        
        for child in block.children:
            text = ""
            if isinstance(child, Block):
                inline = first_inline(child)
                if inline: text = inline.content
            elif isinstance(child, Token) and child.type == "inline":
                text = child.content
            
            if text:
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                for line in lines:
                    if line.startswith("**Caso:**"):
                        case_title = line.replace("**Caso:**", "").strip()
                        continue
                    
                    found_step = False
                    for label in ["SituaciÃ³n", "AcciÃ³n", "Resultado"]:
                        marker = f"**{label} â†’**"
                        if line.startswith(marker):
                            steps.append((label, line.replace(marker, "").strip()))
                            found_step = True
                            break
                    if found_step: continue
        
        steps_html = ""
        for i, (label, text) in enumerate(steps):
            step_idx = i + 1
            dot = "â—" if label == "Resultado" else "â†’"
            connector = f'<div class="step-connector"></div>' if label != "Resultado" else ""
            steps_html += (
                f'        <div class="caso-step step-s{step_idx}">\n'
                f'          <div class="step-indicator">\n'
                f'            <div class="step-dot">{dot}</div>\n'
                f'            {connector}\n'
                f'          </div>\n'
                f'          <div class="step-content">\n'
                f'            <div class="step-label-row">\n'
                f'              <span class="step-label">{label}</span>\n'
                f'            </div>\n'
                f'            <p class="step-text">{text}</p>\n'
                f'          </div>\n'
                f'        </div>\n'
            )

        return (
            f'<article class="md-card caso">\n'
            f'  <header class="caso-header">\n'
            f'    <span class="caso-badge">Caso</span>\n'
            f'    <h3 class="caso-title">{case_title}</h3>\n'
            f'  </header>\n'
            f'  <div class="caso-body">\n'
            f'    <div class="caso-steps">\n'
            f'{steps_html}'
            f'    </div>\n'
            f'  </div>\n'
            f'</article>\n'
        )

    def _render_cover(self, block: Block) -> str:
        """Specialized renderer for the 'cover' component."""
        title = ""
        project_name = ""
        project_type = ""
        meta_items = [] # list of (label, primary, secondary)
        fundamento = None # {label, quote, source}

        # First, extract all raw lines from the children
        raw_lines = []
        for child in block.children:
            if isinstance(child, Block) and is_heading(child.open):
                title = "".join(self._render_item(c) for c in child.children).strip()
                title = title.replace("Obligatorio", "<em>Obligatorio</em>")
                continue
            
            # Extract text from paragraphs or bare inlines
            text = ""
            if isinstance(child, Block):
                inline = first_inline(child)
                if inline: text = inline.content
            elif isinstance(child, Token) and child.type == "inline":
                text = child.content
            
            if text:
                # Split by actual newlines if markdown-it merged them
                raw_lines.extend([l.strip() for l in text.split("\n") if l.strip()])

        # Process lines
        for line in raw_lines:
            # Metadata items
            found_meta = False
            for label in ["Presentado por", "Contacto", "Calidad", "Fecha"]:
                marker = f"**{label}:**"
                if line.startswith(marker):
                    val = line.replace(marker, "").strip()
                    parts = val.split("Â·") if "Â·" in val else [val]
                    primary = parts[0].strip()
                    secondary = " Â· ".join(parts[1:]).strip() if len(parts) > 1 else ""
                    # Special case for Fecha: split by comma
                    if label == "Fecha" and "," in primary:
                        f_parts = primary.split(",", 1)
                        primary = f_parts[0].strip()
                        secondary = f_parts[1].strip()
                    meta_items.append((label, primary, secondary))
                    found_meta = True
                    break
            if found_meta: continue

            # Fundamento
            if line.startswith("**Fundamento:**"):
                val = line.replace("**Fundamento:**", "").strip()
                # val looks like: "Art. 99... *(Â«quoteÂ»)*"
                import re
                m = re.search(r"^(.*?)\s*[\*]?\((.*)\)[\*]?$", val)
                if m:
                    source = m.group(1).strip().strip("*").strip()
                    quote = m.group(2).strip().strip("Â«Â»")
                    fundamento = {"label": "Fundamento", "quote": quote, "source": source}
                continue

            # Project info (if not already found)
            if line.startswith("**") and line.endswith("**") and not project_name:
                project_name = line.replace("**", "").strip()
                continue
            if line.startswith("*") and line.endswith("*") and not project_type:
                project_type = line.replace("*", "").strip()
                continue

        # Build Meta Grid HTML
        meta_html = ""
        for label, primary, secondary in meta_items:
            sec_html = f'<span class="meta-secondary">{secondary}</span>' if secondary else ""
            meta_html += (
                f'        <div class="meta-item">\n'\
                f'          <dt class="meta-label">{label}</dt>\n'\
                f'          <dd>\n'\
                f'            <span class="meta-primary">{primary}</span>\n'\
                f'            {sec_html}\n'\
                f'          </dd>\n'\
                f'        </div>\n'
            )

        # Build Citation HTML
        citation_html = ""
        if fundamento:
            citation_html = (
                f'      <div class="cover-citation">\n'\
                f'        <span class="citation-chip">{fundamento["label"]}</span>\n'\
                f'        <div class="citation-body">\n'\
                f'          <span class="citation-fundamento">Reglamento Interno â€” Base legal de convocatoria</span>\n'\
                f'          <blockquote class="citation-quote">\n'\
                f'            Â«{fundamento["quote"]}Â»\n'\
                f'            <cite class="citation-source">{fundamento["source"]}</cite>\n'\
                f'          </blockquote>\n'\
                f'        </div>\n'\
                f'      </div>\n'
            )

        # Eyebrow (derived from project info)
        eyebrow_text = f"{project_name} Â· Junio 2026"

        return (
            f'<article class="card-cover">\n'\
            f'  <div class="cover-hero">\n'\
            f'    <div class="cover-corners">\n'\
            f'      <span class="cover-corner tl"></span><span class="cover-corner tr"></span>\n'\
            f'      <span class="cover-corner bl"></span><span class="cover-corner br"></span>\n'\
            f'    </div>\n'\
            f'    <span class="cover-doctype-badge">Propuesta Â· Reglamento Interno</span>\n'\
            f'    <div class="cover-eyebrow">\n'\
            f'      <span class="cover-eyebrow-line"></span>\n'\
            f'      <span class="cover-eyebrow-text">{eyebrow_text}</span>\n'\
            f'    </div>\n'\
            f'    <h1 class="cover-title">{title}</h1>\n'\
            f'    <div class="cover-project-row">\n'\
            f'      <span class="cover-project-name">{project_name}</span>\n'\
            f'      <span class="cover-project-sep"></span>\n'\
            f'      <span class="cover-project-type">{project_type}</span>\n'\
            f'    </div>\n'\
            f'  </div>\n'\
            f'  <div class="cover-meta">\n'\
            f'    <dl class="meta-grid">\n'\
            f'{meta_html}\n'\
            f'    </dl>\n'\
            f'{citation_html}\n'\
            f'  </div>\n'\
            f'</article>\n'
        )
