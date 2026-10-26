"""Diagramas de TDAs recursivos (árboles y listas) en Typst y Mermaid (QoL #58, #57, #49).

`bishop diagram --tda arbol|lista` dibuja la estructura y no la memoria: un árbol con la raíz arriba y
cada hijo en su lado (el izquierdo a la izquierda aunque falte el derecho), una lista como cadena de
nodos con sus flechas (`sig`, y `ant` si es doble; la vuelta al primero si es circular). Sirve para
consignas de exámenes y guías, donde el diagrama de pila y heap de `--formato typst` mostraba cajas
sueltas con etiquetas (①, ②) en vez de la forma del TDA.

La estructura sale de la memoria real de un programa (los bloques del heap del mismo tipo enlazados
entre sí, desde la variable `--raiz`) o de un JSON escrito a mano, para armar el examen sin programa:

- árbol: `{"dato": 8, "izq": {"dato": 3}, "der": null}`: las claves con un objeto o `null` son hijos
  (`hijos: [...]` para un árbol n-ario) y las demás, el contenido del nodo;
- lista: `[1, 2, 3]`, o `{"valores": [1, 2, 3], "doble": true, "circular": false}`.

El Typst usa sólo primitivas (`place`, `line`, `box`, `polygon`), sin paquetes, con las posiciones
calculadas acá: es vectorial y se embebe con `#include` en el examen que arma alucarD.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bishop.core.models import BloqueHeap, SnapshotMemoria

TDAS = ("arbol", "lista")
FORMATOS_TDA = ("typst", "mermaid")

_IZQUIERDA = re.compile(r"izq|left|menor", re.IGNORECASE)
_DERECHA = re.compile(r"der|right|mayor", re.IGNORECASE)
_ANTERIOR = re.compile(r"^(ant|prev|anterior|previo)", re.IGNORECASE)
_NULOS = ("NULL", "0x0", "(nil)")
_DIRECCION = re.compile(r"^0x[0-9a-fA-F]+$")


class ErrorDeTDA(ValueError):
    """La entrada no describe un TDA dibujable (no hay nodos, la raíz no existe…)."""


@dataclass
class NodoTDA:
    etiqueta: str
    # (campo, destino): destino None es un enlace a NULL (en un árbol binario, dice de qué lado falta).
    enlaces: List[Tuple[str, Optional[str]]] = field(default_factory=list)


@dataclass
class EstructuraTDA:
    nodos: Dict[str, NodoTDA]
    raiz: Optional[str]
    nombre_raiz: str = ""


# ── Desde la memoria real ─────────────────────────────────────────────────────────────────────────

def _campos(contenido: str) -> List[Tuple[str, str]]:
    """`{dato=8, izq=0x4052a0, der=NULL}` → [("dato", "8"), ("izq", "0x4052a0"), ("der", "NULL")]."""
    texto = contenido.strip()
    if not (texto.startswith("{") and texto.endswith("}")):
        return []
    partes, actual, nivel, comillas = [], "", 0, False
    for c in texto[1:-1]:
        if c == '"' and not actual.endswith("\\"):
            comillas = not comillas
        elif not comillas and c in "{[(":
            nivel += 1
        elif not comillas and c in "}])":
            nivel -= 1
        if c == "," and nivel == 0 and not comillas:
            partes.append(actual)
            actual = ""
        else:
            actual += c
    partes.append(actual)
    campos = []
    for parte in partes:
        clave, igual, valor = parte.partition("=")
        if igual:
            campos.append((clave.strip(), valor.strip()))
    return campos


def _etiqueta_de_bloque(bloque: BloqueHeap) -> str:
    """Los campos de datos del nodo (no los punteros); una cadena, sin la dirección que antepone gdb."""
    enlazados = {str(p.get("campo", "")) for p in bloque.punteros_salientes}
    valores = []
    for clave, valor in _campos(bloque.contenido):
        if clave in enlazados or valor in _NULOS or _DIRECCION.match(valor):
            continue
        valores.append(re.sub(r"^0x[0-9a-fA-F]+\s+(?=\")", "", valor))
    if not valores:
        return bloque.contenido if not bloque.contenido.startswith("{") else "·"
    return ", ".join(valores)


def estructura_desde_snapshot(snap: SnapshotMemoria, raiz: Optional[str] = None) -> EstructuraTDA:
    """Los bloques del heap del tipo del nodo, enlazados por sus punteros al mismo tipo."""
    por_direccion = {b.direccion.lower(): b for b in snap.heap if not b.esta_liberado}
    variables = [v for f in snap.frames for v in f.variables
                 if v.es_puntero and (v.direccion_apuntada or "").lower() in por_direccion]
    if raiz is not None:
        elegidas = [v for v in variables if v.nombre == raiz]
        if not elegidas:
            nombres = ", ".join(sorted({v.nombre for v in variables})) or "ninguna"
            raise ErrorDeTDA(f"no hay un puntero «{raiz}» al heap en ese punto (hay: {nombres}).")
        variables = elegidas

    def recursivo(bloque: BloqueHeap) -> bool:
        return any(getattr(por_direccion.get(str(p.get("destino", "")).lower()), "tipo", None) == bloque.tipo
                   for p in bloque.punteros_salientes)

    def nodo_inicial(bloque: BloqueHeap) -> Optional[BloqueHeap]:
        """El bloque mismo si es un nodo; si es la cabecera del TDA (`Lista` con `cabeza`), su primer nodo."""
        if recursivo(bloque):
            return bloque
        for p in bloque.punteros_salientes:
            destino = por_direccion.get(str(p.get("destino", "")).lower())
            if destino is not None and recursivo(destino):
                return destino
        return None

    candidatos = []
    for v in variables:
        bloque = por_direccion[(v.direccion_apuntada or "").lower()]
        inicio = nodo_inicial(bloque) or (bloque if raiz is not None else None)
        if inicio is not None:
            candidatos.append((v.nombre, inicio))
    if not candidatos:
        raise ErrorDeTDA("no se encontró un TDA recursivo en el heap: ¿el punto de corte (--break) es después "
                         "de armarlo? Con --raiz se elige la variable.")
    tipo = candidatos[0][1].tipo
    nodos_heap = {d: b for d, b in por_direccion.items() if b.tipo == tipo}
    entrantes = {str(p.get("destino", "")).lower() for b in nodos_heap.values() for p in b.punteros_salientes}
    # La raíz: la variable que apunta a un nodo al que no llega ningún otro (en una lista circular, todos
    # tienen uno: queda la primera variable).
    nombre, inicio = next(((n, b) for n, b in candidatos if b.direccion.lower() not in entrantes), candidatos[0])

    nodos: Dict[str, NodoTDA] = {}
    for direccion, bloque in nodos_heap.items():
        enlaces: List[Tuple[str, Optional[str]]] = []
        salientes = {str(p.get("campo", "")): str(p.get("destino", "")).lower() for p in bloque.punteros_salientes}
        for clave, valor in _campos(bloque.contenido) or [(c, d) for c, d in salientes.items()]:
            if clave in salientes and salientes[clave] in nodos_heap:
                enlaces.append((clave, salientes[clave]))
            elif valor in _NULOS:
                enlaces.append((clave, None))
        # Arreglos de hijos (`hijos[0]`, `hijos[1]`): no aparecen como campos sueltos del contenido.
        for clave, destino in salientes.items():
            if clave not in dict(enlaces) and destino in nodos_heap:
                enlaces.append((clave, destino))
        nodos[direccion] = NodoTDA(_etiqueta_de_bloque(bloque), enlaces)
    return EstructuraTDA(nodos, inicio.direccion.lower(), nombre)


def punto_final_de_main(fuente: Path) -> str:
    """La llave que cierra main: ahí el TDA ya está armado y las variables de main siguen vivas."""
    lineas = fuente.read_text(encoding="utf-8", errors="replace").splitlines()
    nivel, en_main = 0, False
    for numero, linea in enumerate(lineas, 1):
        if not en_main and re.search(r"\bmain\s*\(", linea):
            en_main = True
        if en_main:
            for c in linea:
                if c == "{":
                    nivel += 1
                elif c == "}":
                    nivel -= 1
                    if nivel == 0:
                        return f"{fuente.name}:{numero}"
    return "main"


# ── Desde un JSON escrito a mano ──────────────────────────────────────────────────────────────────

def _etiqueta_json(valores: List[Any]) -> str:
    return ", ".join(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for v in valores) or "·"


def estructura_desde_json(datos: Any, tda: str) -> EstructuraTDA:
    nombre = ""
    if isinstance(datos, dict) and ("raiz" in datos or "valores" in datos):
        nombre = str(datos.get("nombre", ""))
    nodos: Dict[str, NodoTDA] = {}

    def nuevo(etiqueta: str) -> str:
        ident = f"n{len(nodos) + 1}"
        nodos[ident] = NodoTDA(etiqueta)
        return ident

    if tda == "lista":
        if isinstance(datos, list):
            valores, doble, circular = datos, False, False
        elif isinstance(datos, dict) and isinstance(datos.get("valores"), list):
            valores, doble, circular = datos["valores"], bool(datos.get("doble")), bool(datos.get("circular"))
        else:
            raise ErrorDeTDA('una lista se escribe [1, 2, 3] o {"valores": [1, 2, 3], "doble": true}.')
        ids = [nuevo(_etiqueta_json([v])) for v in valores]
        for i, ident in enumerate(ids):
            ultimo = i == len(ids) - 1
            siguiente = ids[0] if ultimo and circular else (None if ultimo else ids[i + 1])
            nodos[ident].enlaces.append(("sig", siguiente))
            if doble:
                previo = ids[-1] if i == 0 and circular else (None if i == 0 else ids[i - 1])
                nodos[ident].enlaces.append(("ant", previo))
        return EstructuraTDA(nodos, ids[0] if ids else None, nombre)

    raiz = datos.get("raiz") if isinstance(datos, dict) and "raiz" in datos else datos

    def agregar(nodo: Any) -> str:
        if not isinstance(nodo, dict):
            return nuevo(_etiqueta_json([nodo]))  # una hoja escrita como valor suelto: 4 en vez de {"dato": 4}
        hijos: List[Tuple[str, Any]] = []
        valores = []
        for clave, valor in nodo.items():
            if clave == "hijos" and isinstance(valor, list):
                hijos += [(f"hijos[{i}]", h) for i, h in enumerate(valor)]
            elif isinstance(valor, dict) or valor is None or _lado(clave):
                hijos.append((clave, valor))  # `"izq": 2` es una hoja con el 2, no un dato del padre
            else:
                valores.append(valor)
        ident = nuevo(_etiqueta_json(valores))
        for clave, hijo in hijos:
            nodos[ident].enlaces.append((clave, agregar(hijo) if hijo is not None else None))
        return ident

    if raiz is None:
        return EstructuraTDA(nodos, None, nombre)
    return EstructuraTDA(nodos, agregar(raiz), nombre)


# ── Forma: árbol ──────────────────────────────────────────────────────────────────────────────────

def _lado(campo: str) -> Optional[str]:
    if _IZQUIERDA.search(campo):
        return "izq"
    if _DERECHA.search(campo):
        return "der"
    return None


def _es_binario(est: EstructuraTDA) -> bool:
    campos = {c for n in est.nodos.values() for c, _ in n.enlaces}
    return bool(campos) and len(campos) <= 2 and all(_lado(c) for c in campos)


def _hijos(est: EstructuraTDA, ident: str, binario: bool) -> List[Tuple[str, Optional[str]]]:
    enlaces = est.nodos[ident].enlaces
    if binario:
        por_lado = {_lado(c): d for c, d in enlaces}
        return [("izq", por_lado.get("izq")), ("der", por_lado.get("der"))]
    return [(c, d) for c, d in enlaces if d is not None]


def posiciones_arbol(est: EstructuraTDA) -> Tuple[Dict[str, Tuple[float, int]], List[Tuple[str, str]], bool]:
    """(x, nivel) de cada nodo alcanzable desde la raíz, las aristas y si es binario.

    Binario: x es el orden en un recorrido inorden, así el hijo izquierdo queda a la izquierda aunque
    no haya derecho. N-ario: las hojas en orden y cada padre centrado sobre sus hijos.
    """
    binario = _es_binario(est)
    pos: Dict[str, Tuple[float, int]] = {}
    aristas: List[Tuple[str, str]] = []
    contador = [0.0]

    def inorden(ident: str, nivel: int) -> None:
        izq, der = (d for _, d in _hijos(est, ident, True))
        pos[ident] = (0.0, nivel)  # marca de visitado (un ciclo no se recorre dos veces)
        if izq is not None and izq not in pos:
            aristas.append((ident, izq))
            inorden(izq, nivel + 1)
        pos[ident] = (contador[0], nivel)
        contador[0] += 1
        if der is not None and der not in pos:
            aristas.append((ident, der))
            inorden(der, nivel + 1)

    def por_hojas(ident: str, nivel: int) -> float:
        pos[ident] = (0.0, nivel)  # marca de visitado (un ciclo no se recorre dos veces)
        xs = []
        for _, hijo in _hijos(est, ident, False):
            if hijo is not None and hijo not in pos:
                aristas.append((ident, hijo))
                xs.append(por_hojas(hijo, nivel + 1))
        if xs:
            x = (xs[0] + xs[-1]) / 2
        else:
            x = contador[0]
            contador[0] += 1
        pos[ident] = (x, nivel)
        return x

    if est.raiz is not None:
        if binario:
            inorden(est.raiz, 0)
        else:
            por_hojas(est.raiz, 0)
    return pos, aristas, binario


# ── Forma: lista ──────────────────────────────────────────────────────────────────────────────────

def recorrido_lista(est: EstructuraTDA) -> Tuple[List[str], bool, bool, bool]:
    """(nodos en orden, es doble, es circular, termina en NULL) siguiendo el enlace que no es `ant`."""
    orden: List[str] = []
    doble = any(_ANTERIOR.match(c) for n in est.nodos.values() for c, _ in n.enlaces)
    actual, circular, nulo = est.raiz, False, False
    while actual is not None:
        orden.append(actual)
        siguientes = [d for c, d in est.nodos[actual].enlaces if not _ANTERIOR.match(c)]
        if not siguientes or siguientes[0] is None:
            nulo = bool(siguientes)
            break
        if siguientes[0] in orden:
            circular = siguientes[0] == orden[0]
            break
        actual = siguientes[0]
    return orden, doble, circular, nulo


# ── Typst ─────────────────────────────────────────────────────────────────────────────────────────

def _escapar(texto: str) -> str:
    from bishop.core.typst import _escapar as escapar
    return escapar(texto)


def _ancho(etiqueta: str) -> float:
    return max(22.0, 6.2 * len(etiqueta) + 12)


def _n(valor: float) -> str:
    return f"{valor:.1f}pt"


def _linea(x1: float, y1: float, x2: float, y2: float) -> str:
    return f"  #place(line(start: ({_n(x1)}, {_n(y1)}), end: ({_n(x2)}, {_n(y2)}), stroke: 0.6pt))"


def _punta(x: float, y: float, dx: float, dy: float) -> str:
    """Punta de flecha que termina en (x, y) apuntando en la dirección (dx, dy)."""
    largo = (dx * dx + dy * dy) ** 0.5 or 1.0
    ux, uy = dx / largo, dy / largo
    bx, by = x - 5 * ux, y - 5 * uy
    a = (bx - 2.5 * uy, by + 2.5 * ux)
    b = (bx + 2.5 * uy, by - 2.5 * ux)
    return (f"  #place(polygon(fill: black, ({_n(x)}, {_n(y)}), ({_n(a[0])}, {_n(a[1])}), "
            f"({_n(b[0])}, {_n(b[1])})))")


def _flecha(x1: float, y1: float, x2: float, y2: float) -> List[str]:
    return [_linea(x1, y1, x2, y2), _punta(x2, y2, x2 - x1, y2 - y1)]


def _texto(x: float, y: float, texto: str, ancho: float = 60.0) -> str:
    return (f"  #place(dx: {_n(x - ancho / 2)}, dy: {_n(y - 6)}, box(width: {_n(ancho)}, "
            f"align(center, text(size: 8pt, raw({json.dumps(texto, ensure_ascii=False)})))))")


def _typst_arbol(est: EstructuraTDA) -> str:
    pos, aristas, _ = posiciones_arbol(est)
    alto_nodo, sep_y = 22.0, 44.0
    ancho_max = max((_ancho(est.nodos[i].etiqueta) for i in pos), default=22.0)
    sep_x = ancho_max / 2 + 14
    margen_sup = 26.0 if est.nombre_raiz else 4.0

    def centro(ident: str) -> Tuple[float, float]:
        x, nivel = pos[ident]
        return 4 + ancho_max / 2 + x * sep_x, margen_sup + alto_nodo / 2 + nivel * sep_y

    ancho = 8 + ancho_max + max((x for x, _ in pos.values()), default=0) * sep_x
    alto = margen_sup + alto_nodo + max((n for _, n in pos.values()), default=0) * sep_y + 4
    partes = [f"#box(width: {_n(ancho)}, height: {_n(alto)})["]
    for origen, destino in aristas:
        partes.append(_linea(*centro(origen), *centro(destino)))
    if est.nombre_raiz and est.raiz in pos:
        x, y = centro(est.raiz)
        partes.append(_texto(x, 6, est.nombre_raiz))
        partes += _flecha(x, 13, x, y - alto_nodo / 2)
    for ident in pos:
        x, y = centro(ident)
        etiqueta = est.nodos[ident].etiqueta
        w = _ancho(etiqueta)
        partes.append(f"  #place(dx: {_n(x - w / 2)}, dy: {_n(y - alto_nodo / 2)}, box(width: {_n(w)}, "
                      f"height: {_n(alto_nodo)}, radius: {_n(alto_nodo / 2)}, stroke: 0.6pt, fill: white, "
                      f"align(center + horizon)[{_escapar(etiqueta)}]))")
    partes.append("]")
    return "\n".join(partes)


def _typst_lista(est: EstructuraTDA) -> str:
    orden, doble, circular, nulo = recorrido_lista(est)
    alto, celda, sep = 22.0, 12.0, 26.0
    anchos = [_ancho(est.nodos[i].etiqueta) + celda * (2 if doble else 1) for i in orden]
    margen_sup = 26.0 if est.nombre_raiz else 4.0
    xs, x = [], 4.0
    for w in anchos:
        xs.append(x)
        x += w + sep
    ancho_total = x + (34 if nulo else 0)
    alto_total = margen_sup + alto + (22 if circular else 4)
    y0 = margen_sup
    partes = [f"#box(width: {_n(ancho_total)}, height: {_n(alto_total)})["]
    for i, ident in enumerate(orden):
        x, w = xs[i], anchos[i]
        etiqueta = est.nodos[ident].etiqueta
        partes.append(f"  #place(dx: {_n(x)}, dy: {_n(y0)}, rect(width: {_n(w)}, height: {_n(alto)}, "
                      f"stroke: 0.6pt, inset: 0pt))")
        izq = x + (celda if doble else 0)
        der = x + w - celda
        partes.append(_linea(der, y0, der, y0 + alto))
        if doble:
            partes.append(_linea(izq, y0, izq, y0 + alto))
        partes.append(f"  #place(dx: {_n(izq)}, dy: {_n(y0)}, box(width: {_n(der - izq)}, height: {_n(alto)}, "
                      f"align(center + horizon)[{_escapar(etiqueta)}]))")
        if i + 1 < len(orden):
            ys = y0 + alto * (0.35 if doble else 0.5)
            partes += _flecha(der + celda / 2, ys, xs[i + 1], ys)
            if doble:
                yi = y0 + alto * 0.65
                partes += _flecha(xs[i + 1] + celda / 2, yi, x + w, yi)
    if orden:
        ultimo = len(orden) - 1
        der = xs[ultimo] + anchos[ultimo] - celda / 2
        if nulo:
            partes += _flecha(der, y0 + alto / 2, der + 22, y0 + alto / 2)
            partes.append(_texto(der + 40, y0 + alto / 2, "NULL", 30))
        elif circular:
            abajo = y0 + alto + 14
            primero = xs[0] + anchos[0] / 2
            partes += [_linea(der, y0 + alto / 2, der, abajo), _linea(der, abajo, primero, abajo)]
            partes += _flecha(primero, abajo, primero, y0 + alto)
        if est.nombre_raiz:
            x = xs[0] + anchos[0] / 2
            partes.append(_texto(x, 6, est.nombre_raiz))
            partes += _flecha(x, 13, x, y0)
    partes.append("]")
    return "\n".join(partes)


# ── Mermaid ───────────────────────────────────────────────────────────────────────────────────────

def _m(texto: str) -> str:
    return texto.replace('"', "#quot;")


def _mermaid_arbol(est: EstructuraTDA) -> str:
    pos, _, binario = posiciones_arbol(est)
    ids = {ident: f"n{k}" for k, ident in enumerate(pos, 1)}
    lineas = ["graph TD"]
    if est.nombre_raiz and est.raiz in ids:
        lineas.append(f'    raiz_var(["{_m(est.nombre_raiz)}"]) --> {ids[est.raiz]}')
    for ident in sorted(pos, key=lambda i: (pos[i][1], pos[i][0])):
        lineas.append(f'    {ids[ident]}(("{_m(est.nodos[ident].etiqueta)}"))')
    nulos = 0
    for ident in sorted(pos, key=lambda i: (pos[i][1], pos[i][0])):
        hijos = _hijos(est, ident, binario)
        if binario and all(d is None for _, d in hijos):
            continue
        for _, hijo in hijos:
            if hijo is None:
                # Con un solo hijo, el lado vacío se dibuja como NULL: si no, Mermaid lo centra y no se
                # ve si es el izquierdo o el derecho.
                nulos += 1
                lineas.append(f"    {ids[ident]} -.-> nulo{nulos}[NULL]:::nulo")
            elif hijo in ids:
                lineas.append(f"    {ids[ident]} --> {ids[hijo]}")
    if nulos:
        lineas.append("    classDef nulo stroke-dasharray: 3 3,color:#888")
    return "\n".join(lineas)


def _mermaid_lista(est: EstructuraTDA) -> str:
    orden, doble, circular, nulo = recorrido_lista(est)
    ids = {ident: f"n{k}" for k, ident in enumerate(orden, 1)}
    lineas = ["graph LR"]
    if est.nombre_raiz and orden:
        lineas.append(f'    raiz_var(["{_m(est.nombre_raiz)}"]) --> {ids[orden[0]]}')
    for ident in orden:
        lineas.append(f'    {ids[ident]}["{_m(est.nodos[ident].etiqueta)}"]')
    flecha = "<-->" if doble else "-->"
    for a, b in zip(orden, orden[1:], strict=False):
        lineas.append(f"    {ids[a]} {flecha} {ids[b]}")
    if orden and circular:
        lineas.append(f"    {ids[orden[-1]]} {flecha} {ids[orden[0]]}")
    elif orden and nulo:
        lineas.append(f"    {ids[orden[-1]]} --> nulo[NULL]:::nulo")
        lineas.append("    classDef nulo stroke-dasharray: 3 3,color:#888")
    return "\n".join(lineas)


def generar_diagrama_tda(est: EstructuraTDA, tda: str, formato: str) -> str:
    if tda not in TDAS:
        raise ErrorDeTDA(f"TDA «{tda}» desconocido: usá {' o '.join(TDAS)}.")
    if formato not in FORMATOS_TDA:
        raise ErrorDeTDA(f"con --tda el formato es {' o '.join(FORMATOS_TDA)} (no «{formato}»).")
    if est.raiz is None:
        raise ErrorDeTDA("el TDA está vacío: no hay nodos para dibujar.")
    if formato == "mermaid":
        return _mermaid_arbol(est) if tda == "arbol" else _mermaid_lista(est)
    cuerpo = _typst_arbol(est) if tda == "arbol" else _typst_lista(est)
    return f"// {'Árbol' if tda == 'arbol' else 'Lista'} generado por bishop diagram --tda {tda}\n{cuerpo}\n"
