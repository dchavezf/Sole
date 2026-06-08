# md_converter — Motor de Renderizado Markdown Multi-Formato

Convierte archivos Markdown (GFM + directivas personalizadas) a **HTML**, **PDF** y **DOCX** usando un archivo JSON de tema como única fuente de estilos.

## Instalación

```bash
cd md_converter
pip install -r requirements.txt
```

### WeasyPrint en Windows

WeasyPrint requiere GTK3. Instala el runtime desde:
https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer

Descarga e instala `gtk3-runtime-*-x64.exe`, luego reinicia la terminal.

## Uso

```bash
# Archivo único → HTML + PDF + DOCX
python md_converter.py --input doc.md --theme themes/sole.theme.json --output all

# Solo HTML
python md_converter.py --input doc.md --theme themes/sole.theme.json --output html

# Carpeta completa → un documento combinado
python md_converter.py --input ../  --theme themes/sole.theme.json --output all

# Archivo índice con orden explícito
python md_converter.py --input indice.md --theme themes/sole.theme.json --output all

# Directorio de salida personalizado
python md_converter.py --input doc.md --theme themes/sole.theme.json \
                       --output all --output-dir ./dist --title "Mi Documento"
```

### Archivo índice (`!include`)

Crea un `.md` con directivas `!include` para controlar el orden:

```markdown
!include Sole_01_Presentacion.md
!include Sole_02_01_El_punto_de_partida.md
!include Sole_02_02_Base_Legal.md
!include Sole_03_00_Texto normativo para votación.md
```

## Sintaxis Markdown soportada

| Elemento | Sintaxis |
|---|---|
| Encabezados | `# H1` … `###### H6` |
| Negritas / cursivas | `**bold**` / `*italic*` |
| Tachado | `~~texto~~` |
| Código inline | `` `código` `` |
| Bloques de código | ` ```lang ``` ` |
| Tablas GFM | `\| col \|` con `:---` / `:---:` |
| Listas de tareas | `- [ ]` / `- [x]` |
| Callouts GFM | `> [!NOTE]`, `[!TIP]`, `[!WARNING]`, `[!CAUTION]`, `[!IMPORTANT]`, `[!DANGER]` |
| Directivas personalizadas | `:::card-propuesta`, `:::caso`, `:::example`, `:::details` |
| Links e imágenes | `[texto](url)` / `![alt](src)` |

## Estructura del tema JSON

El archivo de tema (`themes/sole.theme.json`) sigue el schema en `templates/md-conversion-template.schema.json`.

```jsonc
{
  "version": "1.0.0",
  "variables": {
    "colors": { "primary": "#1B3A6B" },
    "fonts":  { "body": "Georgia, serif" }
  },
  "elements": {
    "heading": { "h1": { "html": { "style": {...} }, "docx": {...}, "pdf": {...} } },
    "callout":  { "note": { "icon": {...}, "label": "Nota", "html": {...} } }
  },
  "customDirectives": {
    "card-propuesta": { "html": {...}, "docx": {...} }
  }
}
```

Variables se referencian con `{{colors.primary}}` en cualquier valor string.

## Estructura del proyecto

```
md_converter/
├── md_converter.py          ← CLI entry point
├── requirements.txt
├── core/
│   ├── resolver.py          ← Detecta modo de entrada (archivo/carpeta/índice)
│   ├── parser.py            ← markdown-it-py + plugins GFM
│   ├── theme.py             ← Carga, valida y resuelve variables del JSON
│   └── ast_walker.py        ← Utilidades de travesía del token stream
├── exporters/
│   ├── html_exporter.py     ← HTML5 + CSS dinámico desde el tema
│   ├── pdf_exporter.py      ← WeasyPrint + @page con header/footer
│   └── docx_exporter.py     ← python-docx con bordes y shading desde el tema
├── templates/
│   ├── base.html.jinja2     ← Shell HTML
│   └── md-conversion-template.schema.json
└── themes/
    └── sole.theme.json      ← Tema del Fraccionamiento Solé
```
