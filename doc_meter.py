#!/usr/bin/env python3
"""
doc-meter: Mide el crecimiento de documentación en un repositorio Git.

Itera sobre los commits del repositorio, filtra archivos de documentación
por extensión, acumula líneas netas y genera una gráfica de crecimiento.
"""

import argparse
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

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


def run_git(args: list[str], repo_path: str) -> str:
    """Ejecuta un comando git y retorna stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"Error ejecutando git {' '.join(args)}:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def parse_commits(repo_path: str, extensions: set[str], branch: str | None = None) -> list[dict]:
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
    if branch:
        git_args.append(branch)

    raw = run_git(git_args, repo_path)

    commits: list[dict] = []
    current: dict | None = None

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("###"):
            # Guardar commit anterior si tiene datos de docs
            if current and current["added"] + current["removed"] > 0:
                commits.append(current)

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

    # Último commit
    if current and current["added"] + current["removed"] > 0:
        commits.append(current)

    # Ordenar cronológicamente (más antiguo primero)
    commits.sort(key=lambda c: c["date"])
    return commits


def aggregate_by_interval(commits: list[dict], interval: str) -> list[dict]:
    """
    Agrupa commits por intervalo de tiempo y calcula líneas netas acumuladas.

    interval: "day", "week", "month"

    Retorna lista de {"date": datetime, "net_lines": int, "cumulative": int}
    """
    buckets: dict[str, dict] = defaultdict(lambda: {"added": 0, "removed": 0, "date": None})

    for commit in commits:
        dt = commit["date"]
        if interval == "day":
            key = dt.strftime("%Y-%m-%d")
        elif interval == "week":
            key = dt.strftime("%Y-W%W")
        elif interval == "month":
            key = dt.strftime("%Y-%m")
        else:
            key = dt.strftime("%Y-%m-%d")

        buckets[key]["added"] += commit["added"]
        buckets[key]["removed"] += commit["removed"]
        if buckets[key]["date"] is None or dt > buckets[key]["date"]:
            buckets[key]["date"] = dt

    # Ordenar por fecha
    sorted_buckets = sorted(buckets.values(), key=lambda b: b["date"])

    # Calcular acumulado
    results = []
    cumulative = 0
    for bucket in sorted_buckets:
        net = bucket["added"] - bucket["removed"]
        cumulative += net
        results.append({
            "date": bucket["date"],
            "net_lines": net,
            "cumulative": cumulative,
            "added": bucket["added"],
            "removed": bucket["removed"],
        })

    return results


def print_summary(data: list[dict], commits: list[dict]):
    """Imprime un resumen en consola."""
    if not data:
        print("No se encontraron cambios en archivos de documentación.")
        return

    total_added = sum(c["added"] for c in commits)
    total_removed = sum(c["removed"] for c in commits)
    total_net = total_added - total_removed

    print(f"\n{'='*60}")
    print(f"  doc-meter — Resumen de documentación")
    print(f"{'='*60}")
    print(f"  Commits con cambios en docs : {len(commits)}")
    print(f"  Período                     : {data[0]['date'].strftime('%Y-%m-%d')} → {data[-1]['date'].strftime('%Y-%m-%d')}")
    print(f"  Líneas añadidas (total)     : +{total_added}")
    print(f"  Líneas eliminadas (total)   : -{total_removed}")
    print(f"  Líneas netas (total)        : {'+' if total_net >= 0 else ''}{total_net}")
    print(f"  Documentación actual (est.) : {data[-1]['cumulative']} líneas")
    print(f"{'='*60}\n")


def plot_growth(data: list[dict], output_path: str | None, interval: str, repo_name: str):
    """Genera la gráfica de crecimiento de documentación."""
    dates = [d["date"] for d in data]
    cumulative = [d["cumulative"] for d in data]
    net_per_period = [d["net_lines"] for d in data]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    fig.suptitle(f"doc-meter — {repo_name}", fontsize=14, fontweight="bold")

    # Gráfica superior: líneas acumuladas
    ax1.fill_between(dates, cumulative, alpha=0.3, color="steelblue")
    ax1.plot(dates, cumulative, color="steelblue", linewidth=2, marker="o", markersize=3)
    ax1.set_ylabel("Líneas acumuladas")
    ax1.set_title("Crecimiento acumulado de documentación")
    ax1.grid(True, alpha=0.3)

    # Gráfica inferior: líneas netas por período
    colors = ["green" if v >= 0 else "red" for v in net_per_period]
    ax2.bar(dates, net_per_period, color=colors, alpha=0.7, width=2)
    ax2.set_ylabel(f"Líneas netas por {interval}")
    ax2.set_title(f"Cambio neto por {interval}")
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
        help="Ruta para guardar la gráfica como imagen (si no se indica, se muestra interactiva)",
    )
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="Solo mostrar resumen en consola, sin gráfica",
    )

    args = parser.parse_args()

    repo_path = str(Path(args.repo).resolve())
    extensions = set(args.extensions) if args.extensions else DOC_EXTENSIONS

    # Validar que es un repo git
    run_git(["rev-parse", "--git-dir"], repo_path)

    repo_name = Path(repo_path).name

    print(f"Analizando repositorio: {repo_path}")
    print(f"Extensiones: {', '.join(sorted(extensions))}")
    print(f"Intervalo: {args.interval}")

    commits = parse_commits(repo_path, extensions, args.branch)

    if not commits:
        print("\nNo se encontraron commits con cambios en archivos de documentación.")
        sys.exit(0)

    data = aggregate_by_interval(commits, args.interval)
    print_summary(data, commits)

    if not args.no_plot:
        plot_growth(data, args.output, args.interval, repo_name)


if __name__ == "__main__":
    main()
