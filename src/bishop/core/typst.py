"""Diagrama de memoria en Typst (QoL #57), para los exámenes que arma alucarD en Typst.

Solo primitivas de Typst (sin paquetes): dos columnas, la pila y el heap, con una caja por
variable y por bloque. Los punteros se marcan con una etiqueta (①, ②…) en el origen y en el
destino, que en papel se leen mejor que flechas cruzadas.
"""

from __future__ import annotations

import json
from typing import Dict

from bishop.core.models import SnapshotMemoria

_ETIQUETAS = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _escapar(texto: str) -> str:
    for c in ("\\", "#", "$", "*", "_", "<", ">", "@", "`", "[", "]"):
        texto = texto.replace(c, "\\" + c)
    return texto


def generar_typst(snap: SnapshotMemoria) -> str:
    etiquetas: Dict[str, str] = {}

    def etiqueta(direccion: str) -> str:
        clave = direccion.lower()
        if clave not in etiquetas:
            etiquetas[clave] = _ETIQUETAS[len(etiquetas) % len(_ETIQUETAS)]
        return etiquetas[clave]

    en_heap = {b.direccion.lower() for b in snap.heap}
    pila = []
    for f in snap.frames:
        filas = []
        for v in f.variables:
            valor = _escapar(v.valor)
            if v.es_puntero and v.direccion_apuntada and v.direccion_apuntada.lower() in en_heap:
                valor = f"→ {etiqueta(v.direccion_apuntada)}"
            filas.append(f"[#raw({json.dumps(f'{v.tipo} {v.nombre}')})], [{valor}]")
        cuerpo = ", ".join(filas) if filas else "[—], []"
        pila.append(f"block(stroke: 0.6pt, inset: 4pt, width: 100%)[*{_escapar(f.funcion)}()* \\\n"
                    f"  #table(columns: 2, stroke: 0.4pt, {cuerpo})]")
    heap = []
    for b in snap.heap:
        marca = etiqueta(b.direccion)
        contenido = _escapar(b.contenido)
        for p in b.punteros_salientes:
            destino = str(p.get("destino", ""))
            if destino.lower() in en_heap:
                contenido += f" \\ {_escapar(str(p.get('campo', '')))} → {etiqueta(destino)}"
        estado = " (liberado)" if b.esta_liberado else ""
        heap.append(f"block(stroke: 0.6pt, inset: 4pt, width: 100%, fill: luma(245))[{marca} "
                    f"*{b.tamanio_bytes} bytes*{estado} \\ {contenido}]")
    columna_pila = ", ".join(pila) or "[]"
    columna_heap = ", ".join(heap) or "[_(vacío)_]"
    return ("// Diagrama de memoria generado por bishop\n"
            "#grid(columns: (1fr, 1fr), gutter: 12pt,\n"
            f"  [*Pila* #stack(spacing: 6pt, {columna_pila})],\n"
            f"  [*Heap* #stack(spacing: 6pt, {columna_heap})],\n"
            ")\n")
