"""Diagrama del layout de un struct, byte por byte, con el relleno resaltado (Ola 18, QoL #58).

Los offsets y el relleno los calcula brett (el motor de layout del ecosistema): bishop sólo dibuja.
Cada fila tiene `por_fila` bytes (8 por omisión, la alineación de un `double` o un puntero); un campo
que cruza el final de una fila sigue en la siguiente. El relleno va en gris y punteado, para que se
vea dónde el compilador agrega bytes entre campos (y al final) y cuánto ocupa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

FORMATOS_LAYOUT = ("mermaid", "typst", "ascii")


class StructNoEncontrado(ValueError):
    pass


@dataclass
class Tramo:
    """Un pedazo de un campo o relleno dentro de una fila."""
    nombre: str
    tipo: str
    offset: int  # del tramo
    tamanio: int  # del tramo
    es_relleno: bool
    continua: bool  # el campo empezó en una fila anterior


@dataclass
class Layout:
    nombre: str
    tamanio_total: int
    datos_utiles: int
    relleno: int
    tramos: List[Tramo]
    por_fila: int


def layout_de(archivo: Path, nombre: Optional[str] = None, por_fila: int = 8) -> Layout:
    """El layout del struct `nombre` del archivo (o del único que defina), partido en filas."""
    from brett.core.layout import disponer
    from brett.core.padding import analizar_archivo_c

    structs = analizar_archivo_c(Path(archivo))
    if nombre:
        elegidos = [s for s in structs if s.nombre == nombre]
    else:
        elegidos = structs[:1] if len(structs) == 1 else []
    if not elegidos:
        disponibles = ", ".join(s.nombre for s in structs) or "ninguno"
        raise StructNoEncontrado(
            f"{'no hay un struct ' + repr(nombre) if nombre else 'elegí un struct con --struct'} en "
            f"{Path(archivo).name} (structs: {disponibles}).")
    info = elegidos[0]
    tipos = {c.nombre: f"{c.tipo}{c.sufijo_array}" for c in info.campos}
    elementos, total = disponer([(c.nombre, c.tamanio, c.alineacion) for c in info.campos])
    tramos: List[Tramo] = []
    for e in elementos:
        offset, restante, continua = e.offset, e.tamanio, False
        while restante > 0:
            en_fila = min(restante, por_fila - offset % por_fila)
            tramos.append(Tramo("relleno" if e.es_relleno else e.nombre, "" if e.es_relleno else tipos.get(e.nombre, ""),
                                offset, en_fila, e.es_relleno, continua))
            offset, restante, continua = offset + en_fila, restante - en_fila, True
    relleno = sum(e.tamanio for e in elementos if e.es_relleno)
    return Layout(info.nombre, total, total - relleno, relleno, tramos, por_fila)


def _mermaid_texto(texto: str) -> str:
    return texto.replace('"', "'").replace("[", "(").replace("]", ")")


def mermaid(layout: Layout) -> str:
    """Un flowchart: una fila por cada `por_fila` bytes, un nodo por campo (con su offset y tamaño) y el
    relleno en gris punteado. (block-beta da anchos proporcionales, pero achica las columnas hasta que
    la etiqueta de un campo de un byte no se lee; la proporción la da el diagrama Typst.)"""
    lineas = ["flowchart TB"]
    rellenos = []
    filas: List[List[str]] = []
    for i, t in enumerate(layout.tramos):
        if t.offset % layout.por_fila == 0 or not filas:
            filas.append([])
        if t.es_relleno:
            partes = [f"+{t.offset} · {t.tamanio} B", "relleno"]
            rellenos.append(f"t{i}")
        elif t.continua:
            partes = [f"+{t.offset} · {t.tamanio} B", f"{t.nombre} (sigue)"]
        else:
            partes = [f"+{t.offset} · {t.tamanio} B", t.nombre, t.tipo]
        filas[-1].append(f't{i}["{"<br/>".join(_mermaid_texto(p) for p in partes)}"]')
    for n, nodos in enumerate(filas):
        inicio = n * layout.por_fila
        lineas.append(f'  subgraph f{n} ["bytes {inicio}–{inicio + layout.por_fila - 1}"]')
        lineas.append("    direction LR")
        lineas.append("    " + " ~~~ ".join(nodos))
        lineas.append("  end")
    if len(filas) > 1:
        lineas.append("  " + " ~~~ ".join(f"f{n}" for n in range(len(filas))))
    lineas.append("  classDef relleno fill:#e5e7eb,stroke:#9ca3af,stroke-dasharray: 4 4,color:#6b7280")
    if rellenos:
        lineas.append(f"  class {','.join(rellenos)} relleno")
    return "\n".join(lineas) + "\n"


def _typst_texto(texto: str) -> str:
    return "".join("\\" + c if c in '\\#$*_`<>@[]~/="' else c for c in texto)


def typst(layout: Layout) -> str:
    celdas = []
    for t in layout.tramos:
        if t.es_relleno:
            contenido = f"relleno \\ {t.tamanio} B"
            relleno = 'fill: luma(225), stroke: (paint: luma(150), dash: "dashed", thickness: 0.6pt)'
        else:
            nombre = f"{t.nombre} (sigue)" if t.continua else t.nombre
            contenido = f"*{_typst_texto(nombre)}*" + ("" if t.continua else f" \\ #text(size: 7pt)[{_typst_texto(t.tipo)}]")
            relleno = "fill: white"
        celdas.append(f"  grid.cell(colspan: {t.tamanio}, {relleno})[#text(size: 6pt, fill: luma(110))[+{t.offset}] "
                      f"\\ #text(size: 8pt)[{contenido}]],")
    return "\n".join([
        f"// Layout de {layout.nombre}: {layout.tamanio_total} B ({layout.relleno} B de relleno, en gris)",
        "#block(breakable: false)[",
        f"  #text(weight: \"bold\")[{_typst_texto(layout.nombre)}] — {layout.tamanio_total} B: "
        f"{layout.datos_utiles} B de datos y {layout.relleno} B de relleno",
        "  #v(4pt)",
        f"  #grid(columns: ({', '.join(['1fr'] * layout.por_fila)}), stroke: 0.6pt, inset: 4pt, align: center,",
        *celdas,
        "  )",
        "]",
    ]) + "\n"


def ascii(layout: Layout) -> str:
    """Una fila de texto por fila de bytes: `#` es un byte de dato, `.` uno de relleno."""
    lineas = [f"{layout.nombre}: {layout.tamanio_total} B ({layout.datos_utiles} de datos, {layout.relleno} de relleno '.')"]
    fila: List[Tuple[str, str]] = []
    for t in layout.tramos:
        marca = "." if t.es_relleno else "#"
        fila.append((marca * t.tamanio, "relleno" if t.es_relleno else (f"{t.nombre}…" if t.continua else t.nombre)))
        if (t.offset + t.tamanio) % layout.por_fila == 0 or t is layout.tramos[-1]:
            inicio = t.offset + t.tamanio - sum(len(b) for b, _ in fila)
            lineas.append(f"+{inicio:>3} |{'|'.join(b for b, _ in fila)}|  {', '.join(n for _, n in fila)}")
            fila = []
    return "\n".join(lineas) + "\n"


def generar_layout(layout: Layout, formato: str) -> str:
    return {"mermaid": mermaid, "typst": typst, "ascii": ascii}[formato](layout)
