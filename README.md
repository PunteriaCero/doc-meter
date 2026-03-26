# doc-meter

Mide el crecimiento de documentación en un repositorio Git a lo largo del tiempo.

Itera sobre los commits, filtra archivos de documentación por extensión, acumula líneas netas y genera una gráfica de crecimiento.

## Instalación

```bash
pip install -r requirements.txt
```

Requisitos: Python 3.10+ y Git instalado en el PATH.

## Uso

```bash
# Análisis básico (agrupa por semana, gráfica interactiva)
python doc_meter.py /ruta/al/repo

# Guardar gráfica como imagen
python doc_meter.py /ruta/al/repo --output docs_growth.png

# Agrupar por mes
python doc_meter.py /ruta/al/repo --interval month

# Filtrar solo .md y .rst
python doc_meter.py /ruta/al/repo --extensions .md .rst

# Analizar un branch específico
python doc_meter.py /ruta/al/repo --branch main

# Solo resumen en consola, sin gráfica
python doc_meter.py /ruta/al/repo --no-plot
```

## Opciones

| Argumento | Descripción | Default |
|---|---|---|
| `repo` | Ruta al repositorio Git | (requerido) |
| `--extensions` | Extensiones a considerar como documentación | `.adoc .asciidoc .md .rst .tex .txt .wiki` |
| `--interval` | Agrupación temporal: `day`, `week`, `month` | `week` |
| `--branch` | Branch a analizar | branch actual |
| `--output`, `-o` | Ruta para guardar la gráfica como imagen | (interactiva) |
| `--no-plot` | Solo mostrar resumen en consola | `false` |

## Salida

El script genera:

- **Resumen en consola** con total de commits, líneas añadidas/eliminadas y líneas netas.
- **Gráfica de dos paneles**:
  - Superior: crecimiento acumulado de líneas de documentación.
  - Inferior: cambio neto por período (verde = crecimiento, rojo = reducción).
