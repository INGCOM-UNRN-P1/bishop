"""CLI de BISHOP — Visualizador pedagógico de memoria C (Stack, Heap y punteros)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bishop import __version__
from bishop.core.models import SnapshotMemoria
from bishop.core.tracer import capturar_snapshot_gdb
from bishop.core.visualizer import generar_mermaid_punteros, renderizar_memoria_rich

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="bishop",
    help="🧠 BISHOP — Visualizador pedagógico de memoria C (Stack, Heap y punteros) en terminal y diagramas.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]BISHOP[/bold cyan] versión [bold]{__version__}[/bold]")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Muestra la versión de BISHOP.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


def generar_seccion_markdown(snap: SnapshotMemoria) -> str:
    """Genera sección de auditoría e inspección de memoria para Dredd."""
    lines = ["## Inspección de Memoria y Punteros (Bishop)\n"]
    lines.append(f"- **Archivo analizado:** `{snap.archivo.name}` (línea {snap.linea})")
    lines.append(f"- **Frames en Stack:** {len(snap.frames)}")
    lines.append(f"- **Bloques activos en Heap:** {len(snap.heap)} ({snap.total_bytes_heap_activos} bytes)")
    if snap.fugas_detectadas > 0:
        lines.append(f"- **Fugas detectadas:** {snap.fugas_detectadas}\n")
        lines.append("> [!WARNING]\n> **Fugas de Memoria:** Se detectaron punteros huérfanos o memoria dinámica sin liberar.\n")
    else:
        lines.append("\n> [!TIP]\n> **Memoria Estable:** No se detectaron punteros colgados ni anomalías en el snapshot de memoria.\n")

    if snap.frames:
        lines.append("### Frames de Pila (Stack)")
        lines.append("| Función | Línea | Variables Locales |")
        lines.append("| :--- | :---: | :--- |")
        for f in snap.frames:
            vars_str = ", ".join(f"`{v.nombre}={v.valor}`" for v in f.variables) if f.variables else "*Sin variables*"
            lines.append(f"| `{f.funcion}` | {f.linea_actual or '-'} | {vars_str} |")
        lines.append("")

    if snap.heap:
        lines.append("### Bloques Dinámicos (Heap)")
        lines.append("| Dirección | Tamaño | Estado | Punteros Asociados |")
        lines.append("| :--- | :---: | :---: | :--- |")
        for b in snap.heap:
            ptrs = ", ".join(f"`{p}`" for p in b.punteros_referenciantes) if b.punteros_referenciantes else "**⚠️ Huérfano**"
            estado = "Liberado" if b.esta_liberado else "Activo"
            lines.append(f"| `{b.direccion}` | {b.tamanio_bytes} B | {estado} | {ptrs} |")
        lines.append("")

    diagrama = generar_mermaid_punteros(snap)
    if diagrama:
        lines.append("### Diagrama de Relaciones de Punteros")
        lines.append("```mermaid")
        lines.append(diagrama)
        lines.append("```\n")

    return "\n".join(lines)


@app.command("trace")
def trace_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a trazar e inspeccionar."),
    punto_corte: Optional[str] = typer.Option(None, "--break", "-b", help="Función o línea donde pausar la ejecución (ej: 'invertir_vector', 'main:15')."),
    mermaid_view: bool = typer.Option(False, "--mermaid", "-m", help="Emitir diagrama de punteros en formato Mermaid."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en formato JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
) -> None:
    """Ejecuta el programa, pausa en el punto indicado e inspecciona el estado vivo del Stack y Heap."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    snap = capturar_snapshot_gdb(fuente, punto_corte=punto_corte)

    if output_md:
        md_text = generar_seccion_markdown(snap)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[green]✓ Sección Markdown generada en:[/green] [cyan]{output_md}[/cyan]")
        raise typer.Exit(code=0)

    if json_output:
        print(json.dumps(snap.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    if mermaid_view:
        console.print(generar_mermaid_punteros(snap))
        raise typer.Exit(code=0)

    renderizar_memoria_rich(snap, console)


@app.command("snapshot")
def snapshot_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a inspeccionar."),
    linea: int = typer.Option(1, "--line", "-l", help="Número de línea donde tomar la foto de memoria."),
    json_output: bool = typer.Option(False, "--json", help="Emitir salida en JSON."),
) -> None:
    """Toma una foto exacta del estado del Stack y Heap en una línea específica de código."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    snap = capturar_snapshot_gdb(fuente, linea_corte=linea)

    if json_output:
        print(json.dumps(snap.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    renderizar_memoria_rich(snap, console)


@app.command("heap")
def heap_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a auditar."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en JSON."),
) -> None:
    """Audita exclusivamente el estado del Heap, bloques activos y detección de punteros huérfanos."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    snap = capturar_snapshot_gdb(fuente)

    if json_output:
        print(json.dumps([b.to_dict() for b in snap.heap], indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    if not snap.heap:
        console.print(f"[green]✓ No se detectaron asignaciones dinámicas activas en {fuente.name}.[/green]")
        raise typer.Exit(code=0)

    tabla = Table(title=f"Auditoría de Bloques en Heap ({len(snap.heap)} bloques)")
    tabla.add_column("Dirección", style="bold yellow")
    tabla.add_column("Tamaño", justify="right")
    tabla.add_column("Estado", justify="center")
    tabla.add_column("Punteros Asociados", style="magenta")

    for b in snap.heap:
        ptrs = ", ".join(b.punteros_referenciantes) if b.punteros_referenciantes else "[red]⚠️ Huérfano (Leak)[/red]"
        tabla.add_row(b.direccion, f"{b.tamanio_bytes} B", "Activo", ptrs)

    console.print(tabla)


@app.command("report")
def report_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a inspeccionar."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
    punto_corte: Optional[str] = typer.Option(None, "--break", "-b", help="Punto de corte para el snapshot."),
) -> None:
    """Genera directamente la sección de reporte Markdown de BISHOP para Dredd."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    snap = capturar_snapshot_gdb(fuente, punto_corte=punto_corte)
    md_content = generar_seccion_markdown(snap)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[green]✓ Reporte Markdown generado en:[/green] [cyan]{output}[/cyan]")
    else:
        print(md_content)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
