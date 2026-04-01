# doc-meter

[![doc-meter](https://github.com/PunteriaCero/doc-meter/actions/workflows/doc-meter.yml/badge.svg)](https://github.com/PunteriaCero/doc-meter/actions/workflows/doc-meter.yml)

Mide el crecimiento de documentación en un repositorio Git a lo largo del tiempo. Itera sobre los commits, filtra archivos de documentación por extensión, acumula líneas netas y genera una gráfica de crecimiento — incluyendo comentarios en código fuente como indicador de documentación técnica.

## Instalación

```bash
pip install -r requirements.txt
```

Requisitos: Python 3.10+ y Git en el PATH.

## Uso

```bash
# Análisis básico — solo resumen en consola
python doc_meter.py /ruta/al/repo

# Guardar gráfica como imagen
python doc_meter.py /ruta/al/repo --output salida.png

# Agrupar por mes, solo branch main
python doc_meter.py /ruta/al/repo --interval month --branch main --output salida.png

# Solo resumen en consola (sin análisis de comentarios)
python doc_meter.py /ruta/al/repo --no-comments

# Exportar datos a CSV
python doc_meter.py /ruta/al/repo --output-csv datos.csv

# Gráfica y CSV al mismo tiempo
python doc_meter.py /ruta/al/repo --output salida.png --output-csv datos.csv

# Limitar a un rango de fechas
python doc_meter.py /ruta/al/repo --begin 2024-01-01 --end 2024-12-31 --output salida.png

# Solo desde una fecha (hasta hoy)
python doc_meter.py /ruta/al/repo --begin 2023-06-01 --output-csv datos.csv
```

## Opciones

| Argumento | Descripción | Default |
|---|---|---|
| `repo` | Ruta al repositorio Git | (requerido) |
| `--interval` | Agrupación temporal: `day`, `week`, `month` | `week` |
| `--branch` | Branch a analizar | branch actual |
| `--output`, `-o` | Ruta para guardar la gráfica. Si se omite, no se genera gráfica. | — |
| `--output-csv` | Ruta para exportar los datos como CSV | — |
| `--begin` | Fecha de inicio del análisis (`YYYY-MM-DD`) | hace un año |
| `--end` | Fecha de fin del análisis (`YYYY-MM-DD`) | hoy |
| `--extensions` | Extensiones de documentación | ver lista abajo |
| `--no-comments` | Omitir análisis de comentarios en código fuente | — |

**Extensiones de documentación detectadas por defecto:**
`.adoc` `.asc` `.asciidoc` `.ipynb` `.markdown` `.md` `.mdx` `.org` `.plantuml` `.puml` `.qmd` `.rst` `.tex` `.txt` `.wiki`

**Lenguajes analizados para comentarios:**
Python, JavaScript/TypeScript, C#, Java, C/C++, Go, Rust, Kotlin, Swift, Scala, Dart, Ruby, Shell, SQL, Lua, HTML, CSS/SCSS y más.

## Salida

Consola: commits procesados, período, líneas añadidas/eliminadas/netas y total acumulado de comentarios en código.

Gráfica de dos paneles:

- **Superior:** crecimiento acumulado, una línea por extensión de documentación + línea total (negra gruesa) + línea de comentarios en código fuente (naranja punteada).
- **Inferior:** cambio neto por período (verde = crecimiento, rojo = reducción).

CSV (con `--output-csv`): una fila por período con las columnas `date`, `total_docs`, `net_docs`, una columna por cada extensión detectada y `comments_src` si se analizaron comentarios.

## Ejemplo

![Ejemplo de gráfica de crecimiento de documentación](reclamos_backend_docs.png)

## Uso como GitHub Action

Publica el repositorio en GitHub y referencia la acción en cualquier workflow:

```yaml
steps:
  - name: Checkout (full history)
    uses: actions/checkout@v4
    with:
      fetch-depth: 0

  - name: Medir crecimiento de documentación
    uses: {owner}/doc-meter@v1
    with:
      repo: .                     # directorio del repo (default: .)
      interval: month             # day | week | month
      output: docs_growth.png     # si se omite, no se genera gráfica
      output-csv: docs_growth.csv
      begin: '2024-01-01'         # opcional
      # end: '2024-12-31'         # opcional, default: hoy
      # branch: main              # opcional
      # no-comments: 'true'       # opcional
```

> `fetch-depth: 0` es obligatorio: sin él `git log` solo ve el commit más reciente.

### Inputs

| Input | Descripción | Default |
|---|---|---|
| `repo` | Ruta al repositorio a analizar | `.` |
| `interval` | Agrupación temporal: `day`, `week`, `month` | `week` |
| `branch` | Branch a analizar | branch actual |
| `output` | Ruta de la gráfica PNG | — (sin gráfica) |
| `output-csv` | Ruta del CSV de datos | — |
| `begin` | Fecha de inicio (`YYYY-MM-DD`) | hace un año |
| `end` | Fecha de fin (`YYYY-MM-DD`) | hoy |
| `no-comments` | `'true'` para omitir análisis de comentarios | `'false'` |
| `python-version` | Versión de Python a usar | `3.12` |

---

## CI / GitHub Pages

El repositorio incluye un workflow de GitHub Actions (`.github/workflows/doc-meter.yml`) que se ejecuta automáticamente en cada push a `main`:

1. Clona el repositorio con historial completo (`fetch-depth: 0`).
2. Instala las dependencias.
3. Ejecuta `doc_meter.py` sobre el propio repo con agrupación mensual y genera `docs_growth.png` + `docs_growth.csv`.
4. Construye una página `index.html` que embebe la gráfica y muestra los datos en tabla.
5. Publica todo en **GitHub Pages** usando el entorno oficial `github-pages`.

El resultado queda disponible en:

```
https://<owner>.github.io/doc-meter/
```

Para activarlo, habilita GitHub Pages en la configuración del repositorio eligiendo la fuente **GitHub Actions** (`Settings → Pages → Source → GitHub Actions`).

> Ajusta `--begin YYYY-MM-DD` en el paso `Run doc-meter` del workflow si quieres restringir el período analizado.

