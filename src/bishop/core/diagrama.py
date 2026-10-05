"""Diagramas de memoria a partir de un fuente C (memoria real) o de una traza JSON.

bishop es el dueño de los diagramas de memoria (revisión 04 §5): `deckard diagram-memory` y
`scorm-tools diagram-memory` hacían los suyos (el de deckard, con valores inventados según el tema
del enunciado) y ahora delegan acá.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from bishop.core.ascii_visualizer import render_ascii_punteros
from bishop.core.models import BloqueHeap, SnapshotMemoria, StackFrameMemoria, VariableMemoria
from bishop.core.visualizer import generar_mermaid_punteros

FORMATOS = ("mermaid", "ascii", "typst")


def _campo(d: Dict[str, Any], *claves: str, defecto: Any = None) -> Any:
    for clave in claves:
        if clave in d and d[clave] is not None:
            return d[clave]
    return defecto


def snapshot_desde_dict(datos: Dict[str, Any], archivo: str = "traza.json") -> SnapshotMemoria:
    """Arma un snapshot desde el JSON de `bishop trace --json` o desde una traza con `stack`/`frames`
    y `heap` en español o inglés (el formato que recibía `scorm-tools diagram-memory`)."""
    frames: List[StackFrameMemoria] = []
    for f in _campo(datos, "frames", "stack", defecto=[]):
        variables = []
        for v in _campo(f, "variables", "locals", defecto=[]):
            apuntada = _campo(v, "direccion_apuntada", "target_address", "points_to")
            variables.append(VariableMemoria(
                nombre=str(_campo(v, "nombre", "name", defecto="?")),
                tipo=str(_campo(v, "tipo", "type", defecto="")),
                direccion=str(_campo(v, "direccion", "address", defecto="")),
                valor=str(_campo(v, "valor", "value", defecto="")),
                es_puntero=bool(_campo(v, "es_puntero", "is_pointer", defecto=apuntada is not None)),
                direccion_apuntada=apuntada,
            ))
        frames.append(StackFrameMemoria(
            funcion=str(_campo(f, "funcion", "function", "name", defecto="?")),
            direccion_base=str(_campo(f, "direccion_base", "base_address", defecto="")),
            direccion_tope=str(_campo(f, "direccion_tope", "top_address", defecto="")),
            linea_actual=_campo(f, "linea_actual", "line"),
            variables=variables,
        ))
    heap = [
        BloqueHeap(
            direccion=str(_campo(b, "direccion", "address", defecto="")),
            tamanio_bytes=int(_campo(b, "tamanio_bytes", "size", defecto=0)),
            esta_liberado=bool(_campo(b, "esta_liberado", "is_freed", defecto=False)),
            contenido=str(_campo(b, "contenido", "preview", "content", defecto="...")),
            punteros_salientes=list(_campo(b, "punteros_salientes", defecto=[])),
            tipo=str(_campo(b, "tipo", defecto="")),
        )
        for b in _campo(datos, "heap", defecto=[])
    ]
    snap = SnapshotMemoria(archivo=Path(archivo), linea=int(_campo(datos, "linea", "line", defecto=0) or 0),
                           frames=frames, heap=heap)
    completar_referencias(snap)
    return snap


def completar_referencias(snap: SnapshotMemoria) -> None:
    """Quién apunta a cada bloque (variables y otros bloques), los bytes activos y las fugas: un
    bloque al que no llega ningún puntero ya no se puede liberar."""
    por_direccion = {b.direccion.lower(): b for b in snap.heap}
    for f in snap.frames:
        for v in f.variables:
            b = por_direccion.get((v.direccion_apuntada or "").lower())
            if b is not None and v.nombre not in b.punteros_referenciantes:
                b.punteros_referenciantes.append(v.nombre)
    for origen in snap.heap:
        for p in origen.punteros_salientes:
            b = por_direccion.get(str(p.get("destino", "")).lower())
            etiqueta = f"{origen.direccion}.{p.get('campo', '')}"
            if b is not None and etiqueta not in b.punteros_referenciantes:
                b.punteros_referenciantes.append(etiqueta)
    activos = [b for b in snap.heap if not b.esta_liberado]
    snap.total_bytes_heap_activos = sum(b.tamanio_bytes for b in activos)
    snap.fugas_detectadas = sum(1 for b in activos if not b.punteros_referenciantes)


def generar_diagrama(snap: SnapshotMemoria, formato: str = "mermaid") -> str:
    if formato not in FORMATOS:
        raise ValueError(f"formato «{formato}» desconocido: usá {' o '.join(FORMATOS)}")
    if formato == "typst":
        from bishop.core.typst import generar_typst
        return generar_typst(snap)
    return generar_mermaid_punteros(snap) if formato == "mermaid" else render_ascii_punteros(snap)


def diagrama_de_fuente(fuente: Path, formato: str = "mermaid", punto_corte: Optional[str] = None) -> str:
    """Compila y ejecuta el fuente bajo gdb y dibuja la memoria real en el punto de corte."""
    from bishop.core.tracer import capturar_snapshot_gdb
    return generar_diagrama(capturar_snapshot_gdb(fuente, punto_corte=punto_corte), formato)
