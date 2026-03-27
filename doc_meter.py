#!/usr/bin/env python3
"""
doc-meter: Mide el crecimiento de documentación en un repositorio Git.

Itera sobre los commits del repositorio, filtra archivos de documentación
por extensión, acumula líneas netas y genera una gráfica de crecimiento.
"""

import argparse
import bisect
import csv
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from tqdm import tqdm

import matplotlib.pyplot as plt
import matplotlib.dates as mdates


DOC_EXTENSIONS = {
    # Markdown y variantes
    ".md", ".mdx", ".markdown",
    # reStructuredText
    ".rst",
    # AsciiDoc
    ".adoc", ".asciidoc", ".asc",
    # Texto plano
    ".txt",
    # LaTeX
    ".tex",
    # Wiki
    ".wiki",
    # PlantUML / diagramas como código
    ".puml", ".plantuml",
    # Org-mode (Emacs)
    ".org",
    # Jupyter Notebooks
    ".ipynb",
    # Quarto
    ".qmd",
}

# Patrones de comentarios por extensión de código fuente.
# El patrón se aplica al contenido de la línea (sin el prefijo +/- del diff).
SOURCE_COMMENT_PATTERNS: dict[str, str] = {
    # Python, Ruby, Shell, R, PowerShell
    ".py":   r"^\s*#",
    ".rb":   r"^\s*#",
    ".sh":   r"^\s*#",
    ".bash": r"^\s*#",
    ".zsh":  r"^\s*#",
    ".ps1":  r"^\s*#",
    # C-style (soporta // y bloques /* */)
    ".js":    r"^\s*(//|/\*|\*)",
    ".ts":    r"^\s*(//|/\*|\*)",
    ".jsx":   r"^\s*(//|/\*|\*)",
    ".tsx":   r"^\s*(//|/\*|\*)",
    ".cs":    r"^\s*(//|/\*|\*)",
    ".java":  r"^\s*(//|/\*|\*)",
    ".cpp":   r"^\s*(//|/\*|\*)",
    ".c":     r"^\s*(//|/\*|\*)",
    ".h":     r"^\s*(//|/\*|\*)",
    ".hpp":   r"^\s*(//|/\*|\*)",
    ".go":    r"^\s*(//|/\*|\*)",
    ".swift": r"^\s*(//|/\*|\*)",
    ".kt":    r"^\s*(//|/\*|\*)",
    ".rs":    r"^\s*(//|/\*|\*)",
    ".scala": r"^\s*(//|/\*|\*)",
    ".dart":  r"^\s*(//|/\*|\*)",
    # CSS / SCSS / LESS
    ".css":  r"^\s*(/\*|\*)",
    ".scss": r"^\s*(//|/\*|\*)",
    ".less": r"^\s*(//|/\*|\*)",
    # SQL, Lua
    ".sql": r"^\s*(--|/\*|\*)",
    ".lua": r"^\s*--",
    # HTML / XML / Vue
    ".html": r"^\s*<!--",
    ".xml":  r"^\s*<!--",
    ".vue":  r"^\s*(//|/\*|\*|<!--)",
}


def run_git(args: list[str], repo_path: str) -> str:
    """Ejecuta un comando git y retorna stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=repo_path,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        print(f"Error ejecutando git {' '.join(args)}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def parse_commits(
    repo_path: str,
    extensions: set[str],
    branch: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """
    Obtiene todos los commits con --numstat y filtra por extensiones de documentación.

    Retorna una lista ordenada cronológicamente de:
      {"date": datetime, "added": int, "removed": int, "files": set}
    """
    git_args = [
        "log",
        "--numstat",
        "--pretty=format:###%H|%aI",  # separador con hash y fecha ISO
        "--no-merges",
    ]
    if date_from:
        git_args.append(f"--after={date_from.strftime('%Y-%m-%d')}")
    if date_to:
        git_args.append(f"--before={date_to.strftime('%Y-%m-%d')}")
    if branch:
        git_args.append(branch)

    process = subprocess.Popen(
        ["git"] + git_args,
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )

    commits: list[dict] = []
    current: dict | None = None

    with tqdm(process.stdout, desc="  Commits (docs)", unit=" líneas", ncols=80, miniters=500) as pbar:
        for raw_line in pbar:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("###"):
                # Guardar commit anterior si tiene datos de docs
                if current and current["added"] + current["removed"] > 0:
                    commits.append(current)
                # Actualizar descripción con el conteo actual
                pbar.set_postfix({"commits": len(commits)}, refresh=False)

                parts = line[3:].split("|", 1)
                commit_hash = parts[0]
                date_str = parts[1] if len(parts) > 1 else ""
                try:
                    dt = datetime.fromisoformat(date_str)
                except ValueError:
                    continue

                current = {
                    "hash": commit_hash,
                    "date": dt,
                    "added": 0,
                    "removed": 0,
                    "files": set(),
                    "by_ext": defaultdict(lambda: {"added": 0, "removed": 0}),
                }
            elif current is not None:
                # Línea numstat: "added\tremoved\tfilepath"
                parts = line.split("\t")
                if len(parts) != 3:
                    continue

                added_str, removed_str, filepath = parts

                # Archivos binarios aparecen como "-"
                if added_str == "-" or removed_str == "-":
                    continue

                ext = Path(filepath).suffix.lower()
                if ext not in extensions:
                    continue

                current["added"] += int(added_str)
                current["removed"] += int(removed_str)
                current["files"].add(filepath)
                current["by_ext"][ext]["added"] += int(added_str)
                current["by_ext"][ext]["removed"] += int(removed_str)

    process.wait()
    if process.returncode != 0:
        err = process.stderr.read()
        print(f"Error ejecutando git log --numstat:\n{err}", file=sys.stderr)
        sys.exit(1)

    # Último commit
    if current and current["added"] + current["removed"] > 0:
        commits.append(current)

    # Ordenar cronológicamente (más antiguo primero)
    commits.sort(key=lambda c: c["date"])
    return commits


def parse_source_comments(
    repo_path: str,
    comment_patterns: dict[str, str],
    branch: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> list[dict]:
    """
    Recorre git log -p filtrando archivos de código fuente y cuenta
    las líneas añadidas/eliminadas que son comentarios.
    """
    if not comment_patterns:
        return []

    pathspecs = [f"*{ext}" for ext in comment_patterns]
    git_args = ["log", "-p", "--pretty=format:###%H|%aI", "--no-merges"]
    if date_from:
        git_args.append(f"--after={date_from.strftime('%Y-%m-%d')}")
    if date_to:
        git_args.append(f"--before={date_to.strftime('%Y-%m-%d')}")
    if branch:
        git_args.append(branch)
    git_args += ["--"] + pathspecs

    process = subprocess.Popen(
        ["git"] + git_args,
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )

    commits: list[dict] = []
    current: dict | None = None
    current_pattern: str | None = None

    with tqdm(process.stdout, desc="  Diffs (src)", unit=" líneas", ncols=80, miniters=1000) as pbar:
        for raw_line in pbar:
            line = raw_line.rstrip("\n")

            if line.startswith("###"):
                if current and (current["added"] + current["removed"]) > 0:
                    commits.append(current)
                parts = line[3:].split("|", 1)
                date_str = parts[1] if len(parts) > 1 else ""
                try:
                    dt = datetime.fromisoformat(date_str)
                except ValueError:
                    continue
                current = {"hash": parts[0], "date": dt, "added": 0, "removed": 0}
                current_pattern = None

            elif current is None:
                continue

            elif line.startswith("+++ b/"):
                ext = Path(line[6:].strip()).suffix.lower()
                current_pattern = comment_patterns.get(ext)

            elif current_pattern and line.startswith("+") and not line.startswith("++"):
                if re.match(current_pattern, line[1:]):
                    current["added"] += 1

            elif current_pattern and line.startswith("-") and not line.startswith("--"):
                if re.match(current_pattern, line[1:]):
                    current["removed"] += 1

    process.wait()
    if process.returncode != 0:
        err = process.stderr.read()
        print(f"Error ejecutando git log -p:\n{err}", file=sys.stderr)
        sys.exit(1)

    if current and (current["added"] + current["removed"]) > 0:
        commits.append(current)

    commits.sort(key=lambda c: c["date"])
    return commits


def aggregate_comments_by_interval(commits: list[dict], interval: str) -> tuple[list, list]:
    """
    Agrega commits de comentarios por intervalo.
    Retorna (dates, cumulative_series).
    """
    if not commits:
        return [], []

    def make_key(dt: datetime) -> str:
        if interval == "day":   return dt.strftime("%Y-%m-%d")
        if interval == "week":  return dt.strftime("%Y-W%W")
        if interval == "month": return dt.strftime("%Y-%m")
        return dt.strftime("%Y-%m-%d")

    buckets: dict[str, dict] = defaultdict(lambda: {"added": 0, "removed": 0, "date": None})
    for commit in commits:
        key = make_key(commit["date"])
        buckets[key]["added"] += commit["added"]
        buckets[key]["removed"] += commit["removed"]
        if buckets[key]["date"] is None or commit["date"] > buckets[key]["date"]:
            buckets[key]["date"] = commit["date"]

    sorted_buckets = sorted(buckets.values(), key=lambda b: b["date"])
    dates, cumulative_series = [], []
    cumulative = 0
    for bucket in sorted_buckets:
        cumulative += bucket["added"] - bucket["removed"]
        dates.append(bucket["date"])
        cumulative_series.append(cumulative)

    return dates, cumulative_series


def aggregate_by_interval(commits: list[dict], interval: str) -> dict:
    """
    Agrupa commits por intervalo de tiempo y calcula líneas netas acumuladas.

    Retorna un dict con:
      - dates:  lista de datetimes ordenados
      - total:  lista de acumulado total por fecha
      - net:    lista de cambio neto por período
      - by_ext: dict[ext -> lista de acumulado por fecha]
    """
    def make_key(dt: datetime) -> str:
        if interval == "day":
            return dt.strftime("%Y-%m-%d")
        elif interval == "week":
            return dt.strftime("%Y-W%W")
        elif interval == "month":
            return dt.strftime("%Y-%m")
        return dt.strftime("%Y-%m-%d")

    # Recopilar buckets por clave y por extensión
    bucket_dates: dict[str, datetime] = {}
    bucket_by_ext: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {"added": 0, "removed": 0}))

    for commit in commits:
        dt = commit["date"]
        key = make_key(dt)
        if key not in bucket_dates or dt > bucket_dates[key]:
            bucket_dates[key] = dt
        for ext, stats in commit["by_ext"].items():
            bucket_by_ext[key][ext]["added"] += stats["added"]
            bucket_by_ext[key][ext]["removed"] += stats["removed"]

    sorted_keys = sorted(bucket_dates.keys())
    dates = [bucket_dates[k] for k in sorted_keys]
    all_exts = sorted({ext for key in sorted_keys for ext in bucket_by_ext[key]})

    # Calcular series acumuladas por extensión
    ext_cum = {ext: 0 for ext in all_exts}
    by_ext_series: dict[str, list[int]] = {ext: [] for ext in all_exts}
    total_series: list[int] = []
    net_series: list[int] = []
    total_cum = 0

    for key in sorted_keys:
        period_net = 0
        for ext in all_exts:
            net = bucket_by_ext[key][ext]["added"] - bucket_by_ext[key][ext]["removed"]
            ext_cum[ext] += net
            by_ext_series[ext].append(ext_cum[ext])
            period_net += net
        total_cum += period_net
        total_series.append(total_cum)
        net_series.append(period_net)

    # Filtrar extensiones con cero líneas a lo largo de todo el historial
    by_ext_series = {ext: vals for ext, vals in by_ext_series.items() if max(vals, default=0) > 0}

    return {
        "dates": dates,
        "total": total_series,
        "net": net_series,
        "by_ext": by_ext_series,
    }


def print_summary(data: dict, commits: list[dict]):
    """Imprime un resumen en consola."""
    if not data["dates"]:
        print("No se encontraron cambios en archivos de documentación.")
        return

    total_added = sum(c["added"] for c in commits)
    total_removed = sum(c["removed"] for c in commits)
    total_net = total_added - total_removed

    print(f"\n{'='*60}")
    print(f"  doc-meter — Resumen de documentación")
    print(f"{'='*60}")
    print(f"  Commits con cambios en docs : {len(commits)}")
    print(f"  Período                     : {data['dates'][0].strftime('%Y-%m-%d')} → {data['dates'][-1].strftime('%Y-%m-%d')}")
    print(f"  Líneas añadidas (total)     : +{total_added}")
    print(f"  Líneas eliminadas (total)   : -{total_removed}")
    print(f"  Líneas netas (total)        : {'+' if total_net >= 0 else ''}{total_net}")
    print(f"  Documentación actual (est.) : {data['total'][-1]} líneas")
    print(f"{'='*60}\n")


def export_csv(
    path: str,
    data: dict,
    comment_dates: list | None,
    comment_series: list | None,
):
    """
    Exporta los datos de la gráfica a un archivo CSV.

    Columnas: date, total_docs, net_docs, <ext1>, <ext2>, ..., comments_src

    Para comments_src se aplica un join "as-of": cada fila recibe el último
    valor acumulado de comentarios cuya fecha sea ≤ a la fecha de esa fila.
    """
    by_ext = data["by_ext"]
    exts = sorted(by_ext.keys())

    # Construir serie de comentarios ordenada para búsqueda as-of
    c_dates_sorted: list[datetime] = []
    c_vals_sorted: list[int] = []
    if comment_dates and comment_series:
        pairs = sorted(zip(comment_dates, comment_series), key=lambda x: x[0])
        c_dates_sorted = [p[0] for p in pairs]
        c_vals_sorted  = [p[1] for p in pairs]

    fieldnames = ["date", "total_docs", "net_docs"] + exts
    if c_dates_sorted:
        fieldnames.append("comments_src")

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, dt in enumerate(data["dates"]):
            row: dict = {
                "date": dt.strftime("%Y-%m-%d"),
                "total_docs": data["total"][i],
                "net_docs": data["net"][i],
            }
            for ext in exts:
                row[ext] = by_ext[ext][i]
            if c_dates_sorted:
                # bisect_right devuelve el primer índice cuya fecha > dt;
                # el anterior es el último valor acumulado ≤ dt.
                idx = bisect.bisect_right(c_dates_sorted, dt) - 1
                row["comments_src"] = c_vals_sorted[idx] if idx >= 0 else ""
            writer.writerow(row)

    print(f"CSV guardado en: {path}")


def plot_growth(
    data: dict,
    output_path: str | None,
    interval: str,
    repo_name: str,
    comment_dates: list | None = None,
    comment_series: list | None = None,
):
    """Genera la gráfica de crecimiento de documentación."""
    dates = data["dates"]
    total = data["total"]
    net_per_period = data["net"]
    by_ext = data["by_ext"]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 9), sharex=True)
    fig.suptitle(f"doc-meter — {repo_name}", fontsize=14, fontweight="bold")

    # Paleta de colores para las extensiones de documentación
    cmap = plt.colormaps["tab20"]
    ext_colors = {ext: cmap(i / max(len(by_ext), 1)) for i, ext in enumerate(sorted(by_ext))}

    # Gráfica superior: una línea por extensión + línea total
    for ext, series in sorted(by_ext.items()):
        ax1.plot(dates, series, color=ext_colors[ext], linewidth=1.2,
                 marker="o", markersize=2.5, alpha=0.85, label=ext)

    ax1.plot(dates, total, color="#1a1a2e", linewidth=3,
             marker="o", markersize=4, label="total docs", zorder=5)

    # Línea de comentarios en código fuente
    if comment_dates and comment_series:
        ax1.plot(comment_dates, comment_series, color="#e67e22", linewidth=2.2,
                 marker="s", markersize=3.5, linestyle="--", alpha=0.9,
                 label="comentarios (src)", zorder=4)

    ax1.set_ylabel("Líneas acumuladas")
    ax1.set_title("Crecimiento acumulado de documentación")
    ax1.legend(loc="upper left", fontsize=8, framealpha=0.8)
    ax1.grid(True, alpha=0.3)

    # Gráfica inferior: cambio neto total por período
    bar_colors = ["#2ecc71" if v >= 0 else "#e74c3c" for v in net_per_period]
    ax2.bar(dates, net_per_period, color=bar_colors, alpha=0.8, width=2)
    ax2.set_ylabel(f"Líneas netas por {interval}")
    ax2.set_title(f"Cambio neto total por {interval}")
    ax2.set_xlabel("Fecha")
    ax2.axhline(y=0, color="black", linewidth=0.5)
    ax2.grid(True, alpha=0.3)

    # Formato de fechas
    for ax in (ax1, ax2):
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())

    fig.autofmt_xdate()
    plt.tight_layout()

    if output_path:
        plt.savefig(output_path, dpi=150, bbox_inches="tight")
        print(f"Gráfica guardada en: {output_path}")
    else:
        plt.show()


def main():
    parser = argparse.ArgumentParser(
        description="doc-meter: Mide el crecimiento de documentación en un repositorio Git.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python doc_meter.py /ruta/al/repo
  python doc_meter.py /ruta/al/repo --interval week --output grafica.png
  python doc_meter.py /ruta/al/repo --extensions .md .rst --branch main
        """,
    )
    parser.add_argument(
        "repo",
        help="Ruta al repositorio Git",
    )
    parser.add_argument(
        "--extensions",
        nargs="+",
        default=None,
        help=f"Extensiones de archivos de documentación (default: {' '.join(sorted(DOC_EXTENSIONS))})",
    )
    parser.add_argument(
        "--interval",
        choices=["day", "week", "month"],
        default="week",
        help="Intervalo de agrupación temporal (default: week)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Branch a analizar (default: branch actual)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Ruta para guardar la gráfica como imagen. Si se omite, no se genera gráfica.",
    )
    parser.add_argument(
        "--no-comments",
        action="store_true",
        help="No analizar comentarios en código fuente",
    )
    parser.add_argument(
        "--output-csv",
        default=None,
        metavar="PATH",
        help="Ruta para exportar los datos de la gráfica como archivo CSV",
    )
    parser.add_argument(
        "--begin",
        default=None,
        metavar="YYYY-MM-DD",
        help="Fecha de inicio del análisis (default: hace un año)",
    )
    parser.add_argument(
        "--end",
        default=None,
        metavar="YYYY-MM-DD",
        help="Fecha de fin del análisis (default: hoy)",
    )

    args = parser.parse_args()

    repo_path = str(Path(args.repo).resolve())
    extensions = set(args.extensions) if args.extensions else DOC_EXTENSIONS

    # Rango de fechas
    today = datetime.now()
    try:
        date_from = datetime.strptime(args.begin, "%Y-%m-%d") if args.begin else today - timedelta(days=365)
        date_to   = datetime.strptime(args.end,   "%Y-%m-%d") if args.end   else today
    except ValueError as e:
        print(f"Error en formato de fecha (usar YYYY-MM-DD): {e}", file=sys.stderr)
        sys.exit(1)

    # Validar que es un repo git
    run_git(["rev-parse", "--git-dir"], repo_path)

    repo_name = Path(repo_path).name

    print(f"Analizando repositorio: {repo_path}")
    print(f"Período             : {date_from.strftime('%Y-%m-%d')} → {date_to.strftime('%Y-%m-%d')}")
    print(f"Extensiones docs    : {', '.join(sorted(extensions))}")
    print(f"Intervalo           : {args.interval}")

    commits = parse_commits(repo_path, extensions, args.branch, date_from, date_to)

    if not commits:
        print("\nNo se encontraron commits con cambios en archivos de documentación.")
        sys.exit(0)

    data = aggregate_by_interval(commits, args.interval)
    print_summary(data, commits)

    # Analizar comentarios en código fuente
    comment_dates, comment_series = None, None
    if not args.no_comments:
        print("Analizando comentarios en código fuente...")
        comment_commits = parse_source_comments(repo_path, SOURCE_COMMENT_PATTERNS, args.branch, date_from, date_to)
        if comment_commits:
            comment_dates, comment_series = aggregate_comments_by_interval(comment_commits, args.interval)
            total_comments = comment_series[-1] if comment_series else 0
            print(f"  Commits con cambios en comentarios : {len(comment_commits)}")
            print(f"  Comentarios acumulados (est.)      : {total_comments} líneas\n")
        else:
            print("  No se encontraron comentarios en código fuente.\n")

    if args.output_csv:
        export_csv(args.output_csv, data, comment_dates, comment_series)

    if args.output:
        plot_growth(data, args.output, args.interval, repo_name, comment_dates, comment_series)


if __name__ == "__main__":
    main()
