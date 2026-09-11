"""Módulo de análisis avanzado de memoria, punteros colgantes, fragmentación y desbordamientos."""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from bishop.core.models import SnapshotMemoria, StackFrameMemoria, BloqueHeap, VariableMemoria


def auditar_punteros_colgantes(snap: SnapshotMemoria) -> List[Dict[str, Any]]:
    """Detecta punteros que apuntan a memoria liberada o fuera de marcos válidos."""
    dangling = []
    bloques_liberados = {b.direccion.lower() for b in snap.heap if b.esta_liberado}
    direcciones_validas_heap = {b.direccion.lower() for b in snap.heap if not b.esta_liberado}

    for f in snap.frames:
        for v in f.variables:
            if v.es_puntero and v.direccion_apuntada:
                target = v.direccion_apuntada.lower()
                if target in bloques_liberados:
                    dangling.append({
                        "frame": f.funcion,
                        "variable": v.nombre,
                        "direccion": v.direccion,
                        "direccion_apuntada": v.direccion_apuntada,
                        "tipo_error": "dangling_pointer",
                        "motivo": f"Apunta a bloque de heap previamente liberado ({v.direccion_apuntada}).",
                        "color": "red",
                    })
                elif target.startswith("0x55") and target not in direcciones_validas_heap:
                    dangling.append({
                        "frame": f.funcion,
                        "variable": v.nombre,
                        "direccion": v.direccion,
                        "direccion_apuntada": v.direccion_apuntada,
                        "tipo_error": "wild_pointer",
                        "motivo": f"Apunta a dirección de heap no asignada ({v.direccion_apuntada}).",
                        "color": "red",
                    })
    return dangling


def detectar_fugas_y_huerfanos(snap: SnapshotMemoria) -> List[Dict[str, Any]]:
    """Identifica bloques en el Heap que no tienen ningún puntero apuntándolos."""
    huerfanos = []
    ptrs_activos = set()
    for f in snap.frames:
        for v in f.variables:
            if v.es_puntero and v.direccion_apuntada:
                ptrs_activos.add(v.direccion_apuntada.lower())

    for b in snap.heap:
        if not b.esta_liberado:
            if b.direccion.lower() not in ptrs_activos and not b.punteros_referenciantes:
                huerfanos.append({
                    "direccion": b.direccion,
                    "tamanio_bytes": b.tamanio_bytes,
                    "linea_asignacion": b.linea_asignacion,
                    "motivo": "Bloque activo sin referencias (fuga de memoria)",
                    "color": "yellow",
                })
    return huerfanos


def detectar_punteros_multiples(snap: SnapshotMemoria) -> Dict[str, List[str]]:
    """Identifica alias o punteros múltiples apuntando al mismo bloque dinámico."""
    alias_map: Dict[str, List[str]] = {}
    for f in snap.frames:
        for v in f.variables:
            if v.es_puntero and v.direccion_apuntada:
                target = v.direccion_apuntada.lower()
                alias_map.setdefault(target, []).append(f"{f.funcion}::{v.nombre}")
    
    return {addr: ptrs for addr, ptrs in alias_map.items() if len(ptrs) > 1}


def analizar_fragmentacion_heap(snap: SnapshotMemoria, heap_total_bytes: int = 1024) -> Dict[str, Any]:
    """Calcula estadísticas y porcentaje de fragmentación de memoria dinámica."""
    bloques_ocupados = [b for b in snap.heap if not b.esta_liberado]
    bytes_ocupados = sum(b.tamanio_bytes for b in bloques_ocupados)
    bytes_liberados = sum(b.tamanio_bytes for b in snap.heap if b.esta_liberado)
    bytes_libres_totales = max(0, heap_total_bytes - bytes_ocupados)

    # Bloques libres intercalados
    bloques_libres_count = len([b for b in snap.heap if b.esta_liberado])
    tasa_fragmentacion = 0.0
    if bytes_libres_totales > 0 and bloques_libres_count > 0:
        max_bloque_libre = max([b.tamanio_bytes for b in snap.heap if b.esta_liberado] or [bytes_libres_totales])
        tasa_fragmentacion = round(1.0 - (max_bloque_libre / bytes_libres_totales), 4)

    return {
        "heap_total_bytes": heap_total_bytes,
        "bytes_ocupados": bytes_ocupados,
        "bytes_libres": bytes_libres_totales,
        "bytes_en_bloques_liberados": bytes_liberados,
        "bloques_activos": len(bloques_ocupados),
        "bloques_liberados": bloques_libres_count,
        "tasa_fragmentacion": max(0.0, tasa_fragmentacion),
    }


def detectar_buffer_overflow_stack(frame: StackFrameMemoria) -> List[Dict[str, Any]]:
    """Calcula solapamiento de direcciones o desbordamiento de buffers en el stack frame."""
    issues = []
    vars_con_offset = []
    
    for v in frame.variables:
        try:
            addr_int = int(v.direccion, 16)
            vars_con_offset.append((addr_int, v))
        except (ValueError, TypeError):
            continue

    vars_con_offset.sort(key=lambda x: x[0])
    for i in range(len(vars_con_offset) - 1):
        addr1, v1 = vars_con_offset[i]
        addr2, v2 = vars_con_offset[i + 1]
        
        # Si la variable 1 invade el espacio de la variable 2
        if addr1 + v1.tamanio_bytes > addr2:
            bytes_overflow = (addr1 + v1.tamanio_bytes) - addr2
            issues.append({
                "variable_fuente": v1.nombre,
                "variable_afectada": v2.nombre,
                "bytes_solapados": bytes_overflow,
                "direccion_conflicto": hex(addr2),
                "mensaje": f"El buffer '{v1.nombre}' ({v1.tamanio_bytes} B) invade {bytes_overflow} B de '{v2.nombre}'.",
            })

    return issues


def comparar_snapshots(antes: SnapshotMemoria, despues: SnapshotMemoria) -> Dict[str, Any]:
    """Compara el estado de memoria antes y después de una invocación de función."""
    frames_antes = {f.funcion: f for f in antes.frames}
    frames_despues = {f.funcion: f for f in despues.frames}

    frames_creados = [f for f in frames_despues if f not in frames_antes]
    frames_destruidos = [f for f in frames_antes if f not in frames_despues]

    delta_heap_bytes = despues.total_bytes_heap_activos - antes.total_bytes_heap_activos
    bloques_nuevos = [b.direccion for b in despues.heap if b.direccion not in {x.direccion for x in antes.heap}]
    bloques_liberados = [b.direccion for b in despues.heap if b.esta_liberado and not any(x.direccion == b.direccion and x.esta_liberado for x in antes.heap)]

    return {
        "frames_creados": frames_creados,
        "frames_destruidos": frames_destruidos,
        "delta_heap_bytes": delta_heap_bytes,
        "bloques_nuevos": bloques_nuevos,
        "bloques_liberados": bloques_liberados,
    }
