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


@app.command("trace")
def trace_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a trazar e inspeccionar."),
    punto_corte: Optional[str] = typer.Option(None, "--break", "-b", help="Función o línea donde pausar la ejecución (ej: 'invertir_vector', 'main:15')."),
    mermaid_view: bool = typer.Option(False, "--mermaid", "-m", help="Emitir diagrama de punteros en formato Mermaid."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en formato JSON."),
) -> None:
    """Ejecuta el programa, pausa en el punto indicado e inspecciona el estado vivo del Stack y Heap."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    snap = capturar_snapshot_gdb(fuente, punto_corte=punto_corte)

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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
