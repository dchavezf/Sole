# Configuracion del micrositio de Propuesta Sole

Este archivo documenta como se genero el micrositio estatico de la propuesta, para poder regenerarlo de forma consistente cuando cambien los documentos fuente.

## Objetivo

Crear un micrositio estatico, navegable desde celular, que permita leer la propuesta de forma progresiva:

- Portada/resumen en `index.html`.
- Articulos y documentos completos convertidos de Markdown a HTML.
- Seccion de descargas con documentos finales.
- URL local para comentarios que redirige a Google Forms.

## Rutas

### Fuente editable

Los documentos fuente viven en:

```text
Propuesta/
```

Cada archivo Markdown de `Propuesta/*.md` debe convertirse a una pagina HTML individual.

### Salida generada

El micrositio generado temporalmente vive en:

```text
output/Propuesta/
```

El archivo principal es:

```text
output/Propuesta/index.html
```

Las descargas viven dentro del micrositio en:

```text
output/Propuesta/downloads/
```

No usar `output/descargas` para este micrositio.

### Carpeta para GitHub Pages

Para publicar con GitHub Pages, copiar el contenido de `output/Propuesta/` a:

```text
docs/
```

La carpeta `docs/` debe contener directamente:

```text
docs/index.html
docs/formulario.html
docs/downloads/
docs/Sole_*.html
docs/.nojekyll
```

En GitHub configurar:

```text
Settings -> Pages -> Build and deployment -> Deploy from a branch -> master -> /docs
```

## Archivos especiales

### `output/Propuesta/index.html`

Portada principal del micrositio.

Debe incluir:

- Encabezado con mensaje principal.
- Boton local `Enviar comentario` apuntando a `formulario.html`.
- Lectura rapida.
- Seccion `Explora por concepto`, independiente de la biblioteca completa.
- Comparativo "Antes / despues" en tarjetas, no en tabla, para mejor lectura en celular.
- Tipos de obra.
- Footer en las tarjetas principales con liga directa al desarrollo del concepto.
- Ruta de implementacion.
- Articulos A-E bajo demanda.
- FAQ con busqueda.
- Seccion `Descargas`.
- Biblioteca completa agrupada por capitulos.

### `output/Propuesta/formulario.html`

Pagina local de redireccion al formulario de Google.

Destino actual:

```text
https://docs.google.com/forms/d/e/1FAIpQLSfh-qkBy-GXCR_RMD9pmJK5uN6CjYX_X4naCAeZpRHkRVQgpg/viewform
```

Debe tener:

- `meta refresh`.
- `window.location.replace(...)`.
- Boton manual por si la redireccion falla.

### `output/Propuesta/downloads/`

Carpeta para archivos descargables.

Archivos enlazados actualmente desde `index.html`:

```text
downloads/folleto_bolsillo_2_paginas.pdf
downloads/Propuesta.pdf
downloads/PLANO%20MONTSE%202R%20AUTORIZADO%20SOLE.pdf
downloads/PLANO%20MONTSE%203.0%20AUTORIZADO%20SOLE.pdf
```

Si cambian los nombres de archivo, actualizar la seccion `Descargas` en `index.html`.

## Biblioteca completa

La biblioteca del indice debe agruparse por prefijo numerico del documento:

```text
01 - Presentacion
02 - Propuesta explicada
03 - Texto normativo y formatos
04 - Referencia
05 - Participacion
```

Los enlaces de la biblioteca deben apuntar a paginas `.html`, no a `.md`.

Ejemplo:

```html
<a href="Sole_03_01_Articulos_Normativos.html">Articulos normativos A-E</a>
```

## Mapa conceptual del indice

La portada debe incluir una seccion llamada `Explora por concepto` antes del comparativo.

Esta seccion no sustituye la biblioteca completa. Su funcion es ayudar a leer la propuesta por temas mayores, agrupando documentos relacionados aunque provengan de capitulos distintos.
Esta organizacion queda como la estructura vigente del micrositio.

Conceptos actuales:

```text
Valor patrimonial y punto de partida
Consejo, Manual y clasificacion de obras
Tramites, formatos y operacion
Regularizacion, historial y compraventas
HABI, proyecto original y soporte tecnico
Dudas, terminos y firma para Asamblea
```

Reglas:

- Un concepto puede enlazar a mas de un HTML.
- Un documento puede aparecer en el concepto donde ayude a explicar mejor el tema.
- No todos los documentos tienen que convertirse en concepto principal.
- Los formatos, catalogos y anexos pueden aparecer como soporte de un concepto mayor.
- La biblioteca completa se conserva al final como indice documental exhaustivo.
- Al agregar nuevos documentos, primero decidir si pertenecen a un concepto existente, si justifican crear un concepto nuevo, o si deben quedarse solo en biblioteca/descargas.

## Conversion de Markdown a HTML

Cada archivo:

```text
Propuesta/*.md
```

debe generar:

```text
output/Propuesta/<mismo-nombre>.html
```

Ejemplo:

```text
Propuesta/Sole_04_01_FAQ.md
output/Propuesta/Sole_04_01_FAQ.html
```

Reglas de conversion usadas:

- Leer Markdown como UTF-8.
- Usar el primer encabezado `#` como titulo de la pagina.
- Convertir encabezados, parrafos, listas, blockquotes, tablas simples y enlaces.
- Ignorar marcas internas como `:::`, `:::pagebreak`, `:::card-propuesta`.
- Cada pagina generada debe tener un enlace superior de regreso a `index.html`.
- El estilo de paginas internas debe ser simple, legible y consistente con la portada.

## Reglas visuales importantes

- El sitio debe funcionar bien en celular.
- Evitar tablas anchas en secciones principales de `index.html`.
- Usar tarjetas para comparativos y resuenes.
- Las tarjetas principales deben cerrar con un footer breve del tipo: "Si quieres conocer mas de este concepto, consulta..." y enlazar a la pagina HTML donde se desarrolla el tema.
- Mantener tarjetas con radio maximo de `8px`.
- No depender de internet para estilos, fuentes o scripts.
- No usar frameworks externos.
- Todo debe funcionar como HTML estatico.

## Publicacion recomendada

Opciones recomendadas:

1. Cloudflare Pages
2. Netlify
3. GitHub Pages

Carpeta a publicar en GitHub Pages:

```text
docs/
```

Al publicar, la portada debe quedar en la raiz del sitio:

```text
https://dominio.example/
```

El formulario local quedaria en:

```text
https://dominio.example/formulario.html
```

## Checklist de regeneracion

1. Actualizar los archivos Markdown en `Propuesta/`.
2. Regenerar todos los HTML internos en `output/Propuesta/`.
3. Confirmar que `output/Propuesta/index.html` sigue apuntando a `.html`, no a `.md`.
4. Confirmar que `formulario.html` existe y redirige al Google Form correcto.
5. Confirmar que las descargas estan en `output/Propuesta/downloads/`.
6. Actualizar la seccion `Descargas` si cambiaron nombres o archivos.
7. Confirmar que `Explora por concepto` relaciona los documentos relevantes con conceptos mayores.
8. Revisar la portada en celular o con ventana estrecha.
9. Copiar el contenido de `output/Propuesta/` a `docs/`.
10. Confirmar que `docs/index.html`, `docs/formulario.html`, `docs/downloads/` y `docs/.nojekyll` existen.
11. Publicar con GitHub Pages desde `master` y carpeta `/docs`.

## Nota de git

Actualmente `output/` esta ignorado por `.gitignore`.

Eso significa que el micrositio generado no aparece en commits por defecto. Este archivo de configuracion queda en `Propuesta/MICROSITIO.md` para conservar la receta de generacion aunque la salida se regenere o se borre.
