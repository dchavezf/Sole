"""
HTML Exporter: renders a markdown-it token list to a self-contained HTML5 file.

CSS is generated entirely from the theme JSON â€” no hardcoded styles anywhere.
The Jinja2 template (base.html.jinja2) provides the outer HTML shell.
"""

from __future__ import annotations

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


class HtmlExporter:
    def __init__(self, theme: Theme) -> None:
        self.theme = theme
        self._jinja = Environment(
            loader=ChoiceLoader([
                FileSystemLoader(str(theme.base_dir)),
                FileSystemLoader(str(_TEMPLATES_DIR)),
            ]),
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

        # Pre-render unmatched blocks for _body/remainder fields
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

    def _render_table(self, block: Block) -> str:
        res = ['<div class="md-table-container">\n<table class="md-table">\n']
        for child in block.children:
            res.append(self._render_item(child))
        res.append("</table>\n</div>\n")
        return "".join(res)
