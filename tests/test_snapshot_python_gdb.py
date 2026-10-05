"""Snapshot con la API Python de gdb: listas dobles y circulares, matrices `int **` y tamaños
reales (QoL #58, #49; revisión 07: `heap` y `ascii` sin parsear texto)."""

import shutil
import subprocess
from pathlib import Path

import pytest

from bishop.core.diagrama import generar_diagrama, snapshot_desde_dict
from bishop.core.snapshot_gdb import capturar_con_python_gdb

FUENTE = Path(__file__).parent / "datos" / "lista_y_matriz.c"


def _gdb_con_python() -> bool:
    gdb = shutil.which("gdb")
    if not gdb or not shutil.which("gcc"):
        return False
    res = subprocess.run([gdb, "-nx", "-batch", "-ex", "python print(1)"], capture_output=True, text=True)
    return res.stdout.strip() == "1"


pytestmark = pytest.mark.skipif(not _gdb_con_python(), reason="requiere gcc y gdb con Python")


@pytest.fixture(scope="module")
def datos():
    return capturar_con_python_gdb(FUENTE, f"{FUENTE.name}:25")


def test_variables_con_direcciones_y_tipos_reales(datos):
    (marco,) = datos["frames"]
    variables = {v["nombre"]: v for v in marco["variables"]}
    assert variables["m"]["tipo"] == "int **" and variables["a"]["tipo"] == "Nodo *"
    assert variables["lista"]["direccion_apuntada"] == variables["a"]["direccion_apuntada"]
    assert len({v["direccion"] for v in variables.values()}) == len(variables)


def test_lista_doble_y_circular(datos):
    heap = {b["direccion"]: b for b in datos["heap"]}
    variables = {v["nombre"]: v for v in datos["frames"][0]["variables"]}
    a, b, c = (variables[n]["direccion_apuntada"] for n in "abc")
    assert {p["campo"]: p["destino"] for p in heap[a]["punteros_salientes"]} == {"ant": c, "sig": b}
    assert {p["campo"]: p["destino"] for p in heap[c]["punteros_salientes"]} == {"ant": b, "sig": a}
    assert heap[a]["tamanio_bytes"] == 24


def test_matriz_de_punteros_con_tamanios_pedidos(datos):
    heap = {b["direccion"]: b for b in datos["heap"]}
    m = next(v for v in datos["frames"][0]["variables"] if v["nombre"] == "m")["direccion_apuntada"]
    filas = [p["destino"] for p in heap[m]["punteros_salientes"]]
    assert heap[m]["tamanio_bytes"] == 16 and len(filas) == 2
    assert heap[filas[1]]["contenido"] == "[ 0, 0, 7 ]" and heap[filas[1]]["tamanio_bytes"] == 12


def test_bloque_liberado(datos):
    suelto = next(v for v in datos["frames"][0]["variables"] if v["nombre"] == "suelto")["direccion_apuntada"]
    bloque = next(b for b in datos["heap"] if b["direccion"] == suelto)
    assert bloque["esta_liberado"] and bloque["contenido"] == "‹liberado›"


def test_diagramas_con_flechas_entre_bloques(datos):
    snap = snapshot_desde_dict(datos, FUENTE.name)
    mermaid = generar_diagrama(snap, "mermaid")
    assert mermaid.count(" -- sig --> ") == 3 and mermaid.count(" -- ant --> ") == 3
    assert " -- [1] --> " in mermaid
    assert "--sig-->" in generar_diagrama(snap, "ascii")
    assert snap.fugas_detectadas == 0


def test_diagrama_typst(datos, tmp_path):
    texto = generar_diagrama(snapshot_desde_dict(datos, FUENTE.name), "typst")
    assert texto.startswith("// Diagrama de memoria") and 'raw("Nodo * a")' in texto and "sig → " in texto
    typst = shutil.which("typst")
    if typst:
        destino = tmp_path / "mem.typ"
        destino.write_text(texto, encoding="utf-8")
        assert subprocess.run([typst, "compile", str(destino), str(tmp_path / "mem.pdf")], capture_output=True).returncode == 0
