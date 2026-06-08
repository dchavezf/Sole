"""
Theme loader: reads theme-config.json, validates it against the schema,
and resolves all {{variable}} references before handing styles to exporters.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Any

try:
    import jsonschema
    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

_SCHEMA_PATH = Path(__file__).parent.parent.parent / "templates" / "md-conversion-template.schema.json"
_VAR_RE = re.compile(r"\{\{([^}]+)\}\}")

# All GFM callout types recognised by this engine
KNOWN_CALLOUT_TYPES = {"note", "tip", "warning", "caution", "important", "danger"}


class ThemeError(Exception):
    pass


class Theme:
    def __init__(self, data: dict, base_dir: Path | None = None) -> None:
        self._raw = data
        self._base_dir = base_dir or Path.cwd()
        self._variables = data.get("variables", {})
        self._elements = data.get("elements", {})
        self._directives = data.get("customDirectives", {})
        self._styles = data.get("styles", {})
        self._meta = data.get("meta", {})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def meta(self) -> dict:
        return self._meta

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def get_variables(self) -> dict:
        """Return all resolved design variables."""
        return self._resolve(self._variables)

    def get_styles(self) -> dict:
        """Return resolved global style configuration."""
        return self._resolve(self._styles)

    def get_extra_css(self) -> str:
        """Return CSS loaded from configured files plus inline CSS strings."""
        styles = self.get_styles()
        chunks: list[str] = []

        for rel_path in styles.get("cssFiles", []) or []:
            css_path = (self.base_dir / rel_path).resolve()
            if not css_path.exists():
                raise ThemeError(f"Configured CSS file not found: {css_path}")
            chunks.append(css_path.read_text(encoding="utf-8"))

        css = styles.get("css", "")
        if isinstance(css, list):
            chunks.extend(str(part) for part in css if str(part).strip())
        elif css:
            chunks.append(str(css))

        return "\n".join(chunks)

    def get_element(self, name: str) -> dict:
        """Return resolved style block for a standard element, or {} if missing."""
        raw = self._elements.get(name, {})
        return self._resolve(raw)

    def get_heading(self, level: int) -> dict:
        """Return resolved style for h1..h6."""
        raw = self._elements.get("heading", {}).get(f"h{level}", {})
        return self._resolve(raw)

    def get_callout(self, callout_type: str) -> dict:
        """Return resolved style for a callout variant, falling back to base."""
        ct = callout_type.lower()
        callout_cfg = self._elements.get("callout", {})
        base = self._resolve(callout_cfg.get("base", {}))

        if ct not in KNOWN_CALLOUT_TYPES:
            warnings.warn(
                f"Callout type '[!{callout_type.upper()}]' is not defined in the theme. "
                f"Falling back to callout.base styles.",
                stacklevel=3,
            )
            return base

        variant = self._resolve(callout_cfg.get(ct, {}))
        return _deep_merge(base, variant)

    def get_callout_title(self) -> dict:
        return self._resolve(self._elements.get("callout", {}).get("title", {}))

    def get_callout_body(self) -> dict:
        return self._resolve(self._elements.get("callout", {}).get("body", {}))

    def get_layout(self) -> dict:
        """Return resolved layout configuration."""
        raw = self._raw.get("layout", {})
        return self._resolve(raw)

    def get_all_directives(self) -> dict[str, dict]:
        """Return all resolved custom directive definitions keyed by name."""
        return {name: self._resolve(cfg) for name, cfg in self._directives.items()}

    def get_directive(self, name: str) -> dict:
        """Return resolved style for a custom ::: directive, or {} with warning."""
        raw = self._directives.get(name)
        if raw is None:
            warnings.warn(
                f"Custom directive ':::{name}' has no definition in the theme. "
                f"Output will have no custom styling for this block.",
                stacklevel=3,
            )
            return {}
        return self._resolve(raw)

    def get_table_part(self, part: str) -> dict:
        """part: container | thead | tbody | tr | trAlternate | th | td | caption"""
        raw = self._elements.get("table", {}).get(part, {})
        return self._resolve(raw)

    def get_table_columns(self) -> dict:
        raw = self._elements.get("table", {}).get("columns", {})
        return self._resolve(raw)

    def get_variable(self, path: str) -> str | None:
        """Resolve a dotted variable path like 'colors.primary'."""
        parts = path.split(".")
        node = self._variables
        for p in parts:
            if not isinstance(node, dict):
                return None
            node = node.get(p)
        return node if isinstance(node, (str, int, float)) else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, obj: Any) -> Any:
        """Recursively resolve all {{variable}} references in obj, including nested ones."""
        if isinstance(obj, str):
            res = _VAR_RE.sub(lambda m: str(self.get_variable(m.group(1)) or m.group(0)), obj)
            if "{{" in res and res != obj:
                return self._resolve(res)
            return res
        if isinstance(obj, dict):
            return {k: self._resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve(i) for i in obj]
        return obj


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def load_theme(path: str | Path) -> Theme:
    """Load and validate a theme JSON file. Returns a ready-to-use Theme."""
    path = Path(path)
    if not path.exists():
        raise ThemeError(f"Theme file not found: {path}")

    with path.open(encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ThemeError(f"Invalid JSON in theme file: {exc}") from exc

    if _HAS_JSONSCHEMA:
        _validate(data)
    else:
        warnings.warn(
            "jsonschema is not installed — theme validation skipped. "
            "Run: pip install jsonschema",
            stacklevel=2,
        )

    return Theme(data, base_dir=path.parent)


def _validate(data: dict) -> None:
    if not _SCHEMA_PATH.exists():
        warnings.warn(f"Schema file not found at {_SCHEMA_PATH}, skipping validation.", stacklevel=3)
        return
    with _SCHEMA_PATH.open(encoding="utf-8") as fh:
        schema = json.load(fh)
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as exc:
        raise ThemeError(f"Theme validation failed: {exc.message}\nPath: {list(exc.absolute_path)}") from exc


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base recursively; override wins on conflicts."""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
