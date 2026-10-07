"""Visualizador de memoria en terminal (ASCII / Rich) y diagramas Mermaid en BISHOP."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from bishop.core.models import SnapshotMemoria


def renderizar_memoria_rich(snap: SnapshotMemoria, console: Console) -> None:
    """Renderiza el snapshot de memoria en terminal con paneles y tablas enriquecidas."""
    # 1. Panel de Encabezado
    console.print(Panel(
        f"📍 [bold]Ubicación:[/bold] [yellow]{snap.archivo.name}:{snap.linea}[/yellow] · "
        f"🥞 Frames en Stack: [cyan]{len(snap.frames)}[/cyan] · "
        f"📦 Bloques en Heap: [green]{len(snap.heap)}[/green] ({snap.total_bytes_heap_activos} bytes)",
        title="🧠 BISHOP — Estado de Memoria del Proceso",
        border_style="blue",
    ))

    # 2. Tabla del Stack
    tabla_stack = Table(title="🥞 Memoria Stack (Pila de Ejecución)")
    tabla_stack.add_column("Frame / Función", style="bold cyan")
    tabla_stack.add_column("Variable", style="bold")
    tabla_stack.add_column("Tipo", style="dim")
    tabla_stack.add_column("Dirección (&var)", style="yellow")
    tabla_stack.add_column("Valor Actual", style="green")
    tabla_stack.add_column("Apunta a (Puntero)", style="magenta")

    for f in snap.frames:
        if not f.variables:
            tabla_stack.add_row(f"{f.funcion}()", "[dim]—[/dim]", "—", f.direccion_base, "—", "—")
        for v in f.variables:
            apunta_str = f"➜ {v.direccion_apuntada}" if v.es_puntero and v.direccion_apuntada else "—"
            tabla_stack.add_row(
                f"{f.funcion}()",
                v.nombre,
                v.tipo,
                v.direccion,
                v.valor,
                apunta_str,
            )

    console.print(tabla_stack)

    # 3. Tabla del Heap si hay asignaciones
    if snap.heap:
        tabla_heap = Table(title="📦 Memoria Heap (Memoria Dinámica malloc/calloc)")
        tabla_heap.add_column("Dirección Bloque", style="bold yellow")
        tabla_heap.add_column("Tamaño", justify="right")
        tabla_heap.add_column("Estado", justify="center")
        tabla_heap.add_column("Contenido / Preview", style="dim")
        tabla_heap.add_column("Punteros Dueños", style="magenta")
        tabla_heap.add_column("Apunta a", style="cyan")

        for b in snap.heap:
            estado_str = "[red]Liberado (free)[/red]" if b.esta_liberado else "[green]Activo (reservado)[/green]"
            ptrs_str = ", ".join(b.punteros_referenciantes) if b.punteros_referenciantes else "[red]⚠️ Fuga (huérfano)[/red]"
            tabla_heap.add_row(
                b.direccion,
                f"{b.tamanio_bytes} B",
                estado_str,
                b.contenido,
                ptrs_str,
                ", ".join(f"{p.get('campo')} ➜ {p.get('destino')}" for p in b.punteros_salientes) or "—",
            )

        console.print(tabla_heap)


def generar_mermaid_punteros(snap: SnapshotMemoria) -> str:
    """Genera un diagrama Mermaid con las relaciones entre punteros y datos."""
    lineas = ["graph LR", "    subgraph Stack[Pila / Variables Locales]"]

    # Agregar variables de stack
    for _idx, f in enumerate(snap.frames):
        for v in f.variables:
            v_id = f"var_{f.funcion}_{v.nombre}"
            lineas.append(f'        {v_id}["{v.tipo} {v.nombre}<br/>dir: {v.direccion}<br/>val: {v.valor}"]')
    lineas.append("    end")

    # Agregar bloques de heap
    if snap.heap:
        lineas.append("    subgraph Heap[Memoria Dinámica / Heap]")
        for b in snap.heap:
            b_id = f"heap_{b.direccion.replace('0x', '')}"
            estado = " LIBERADO" if b.esta_liberado else ""
            tipo = f"{b.tipo} · " if b.tipo else ""
            contenido = b.contenido.replace('"', "'")
            lineas.append(f'        {b_id}["{tipo}{b.tamanio_bytes} bytes{estado}<br/>dir: {b.direccion}<br/>{contenido}"]')
        lineas.append("    end")

    # Flechas de punteros
    for f in snap.frames:
        for v in f.variables:
            if v.es_puntero and v.direccion_apuntada:
                v_id = f"var_{f.funcion}_{v.nombre}"
                # Buscar si apunta a heap o a otra variable de stack
                target_id = None
                for b in snap.heap:
                    if b.direccion.lower() == v.direccion_apuntada.lower():
                        target_id = f"heap_{b.direccion.replace('0x', '')}"
                        break
                if not target_id:
                    for f2 in snap.frames:
                        for v2 in f2.variables:
                            if v2.direccion.lower() == v.direccion_apuntada.lower():
                                target_id = f"var_{f2.funcion}_{v2.nombre}"
                                break

                if target_id:
                    lineas.append(f"    {v_id} == desreferencia ==> {target_id}")

    # Punteros guardados en el heap: `sig`/`ant` de una lista (doble o circular), las filas de una
    # matriz `int **` (QoL #58, #49). Un par sig/ant entre dos nodos queda como dos flechas opuestas.
    en_heap = {b.direccion.lower() for b in snap.heap}
    for b in snap.heap:
        origen = f"heap_{b.direccion.replace('0x', '')}"
        for p in b.punteros_salientes:
            destino = str(p.get("destino", ""))
            if destino.lower() in en_heap:
                lineas.append(f"    {origen} -- {p.get('campo', '')} --> heap_{destino.replace('0x', '')}")

    return "\n".join(lineas)
