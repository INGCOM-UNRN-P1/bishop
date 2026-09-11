"""Visualizador ASCII enriquecido y modo principiante para BISHOP."""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from bishop.core.models import SnapshotMemoria, StackFrameMemoria, BloqueHeap


def render_ascii_punteros(snap: SnapshotMemoria) -> str:
    """Genera una representación de punteros con flechas direccionales ASCII en terminal."""
    lineas = ["=== Visualización de Punteros en Terminal (ASCII) ==="]
    
    for f in snap.frames:
        lineas.append(f"\n[Marco de función: {f.funcion}()]")
        for v in f.variables:
            if v.es_puntero:
                dest = v.direccion_apuntada or "NULL"
                target_desc = "NULL"
                if dest != "NULL":
                    # Buscar coincidencia en heap
                    heap_match = next((b for b in snap.heap if b.direccion.lower() == dest.lower()), None)
                    if heap_match:
                        estado = "[LIBERADO!]" if heap_match.esta_liberado else f"[Heap {heap_match.tamanio_bytes}B]"
                        target_desc = f"{dest} {estado} -> {heap_match.contenido}"
                    else:
                        target_desc = f"{dest} [Stack/Otro]"

                lineas.append(f"  [{v.tipo} {v.nombre} @ {v.direccion}] ---> {target_desc}")
            else:
                lineas.append(f"  ({v.tipo} {v.nombre} @ {v.direccion}) = {v.valor}")

    return "\n".join(lineas)


def render_ascii_lista_enlazada(nodos: List[Dict[str, Any]]) -> str:
    """Representación gráfica de listas enlazadas en ASCII."""
    if not nodos:
        return "[Lista Vacía: NULL]"

    partes = []
    for n in nodos:
        val = n.get("valor", "?")
        addr = n.get("direccion", "0x0")
        partes.append(f"[ {addr} | Dato: {val} | *next ]")

    return " ---> ".join(partes) + " ---> NULL"


def render_ascii_arbol_binario(nodo: Optional[Dict[str, Any]], prefijo: str = "", es_izq: bool = True) -> str:
    """Representación gráfica de árbol binario en ASCII."""
    if not nodo:
        return f"{prefijo}{'└── ' if es_izq else '┌── '}[NULL]\n"

    res = ""
    if nodo.get("der"):
        res += render_ascii_arbol_binario(nodo["der"], prefijo + ("│   " if es_izq else "    "), False)

    res += f"{prefijo}{'└── ' if es_izq else '┌── '}[ {nodo.get('valor', '?')} ]\n"

    if nodo.get("izq"):
        res += render_ascii_arbol_binario(nodo["izq"], prefijo + ("    " if es_izq else "│   "), True)

    return res


def render_heap_fragmentation_map(snap: SnapshotMemoria, ancho_total: int = 50) -> str:
    """Genera un mapa visual de fragmentación del Heap con bloques libres y ocupados."""
    lineas = ["=== Mapa de Fragmentación del Heap ==="]
    if not snap.heap:
        lineas.append("[ El Heap está completamente libre o no contiene asignaciones ]")
        return "\n".join(lineas)

    total_bytes = sum(b.tamanio_bytes for b in snap.heap)
    if total_bytes == 0:
        total_bytes = 1

    mapa_chars = []
    for b in snap.heap:
        ancho_bloque = max(2, int((b.tamanio_bytes / total_bytes) * ancho_total))
        simbolo = "." if b.esta_liberado else "#"
        mapa_chars.append(f"[{simbolo * ancho_bloque} {b.tamanio_bytes}B]")

    lineas.append("".join(mapa_chars))
    lineas.append("Referencias: [#]=Bloque ocupado con datos activos, [.]=Bloque liberado con free()")
    return "\n".join(lineas)


def render_modo_principiante(snap: SnapshotMemoria) -> str:
    """Modo de visualización pedagógica simplificada para principiantes en español rioplatense."""
    lineas = [
        "============================================================",
        "  BISHOP: GUÍA SIMPLIFICADA DE MEMORIA PARA PRINCIPIANTES   ",
        "============================================================",
        "",
        "1. LA PILA DE LLAMADAS (STACK):",
        "   Es la memoria rápida y automática donde viven tus variables locales.",
    ]

    for f in snap.frames:
        lineas.append(f"\n   * Estás adentro de la función '{f.funcion}()':")
        for v in f.variables:
            if v.es_puntero:
                lineas.append(f"     - '{v.nombre}' es una FLECHA (puntero) que guarda la dirección {v.direccion_apuntada or 'NULL'}.")
            else:
                lineas.append(f"     - '{v.nombre}' es una CAJITA de tipo '{v.tipo}' que guarda el valor '{v.valor}'.")

    lineas.append("\n2. LA MEMORIA DINÁMICA (HEAP):")
    lineas.append("   Es el espacio que pedís a mano con malloc() y tenés que devolver con free().")

    if not snap.heap:
        lineas.append("   * En este momento no pediste memoria con malloc() o ya liberaste todo.")
    else:
        for idx, b in enumerate(snap.heap, 1):
            if b.esta_liberado:
                lineas.append(f"   * Bloque {idx} ({b.direccion}): Ya lo liberaste con free(). No lo toques más.")
            else:
                duenos = ", ".join(b.punteros_referenciantes) if b.punteros_referenciantes else "¡Nadie! Está huérfano (fuga de memoria)"
                lineas.append(f"   * Bloque {idx} ({b.direccion}): Ocupa {b.tamanio_bytes} bytes. Quien lo mira: {duenos}.")

    lineas.append("\n============================================================")
    return "\n".join(lineas)
