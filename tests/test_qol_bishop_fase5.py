import pytest
from pathlib import Path
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core.models import SnapshotMemoria, StackFrameMemoria, BloqueHeap, VariableMemoria
from bishop.core.memory_analyzer import (
    auditar_punteros_colgantes,
    detectar_fugas_y_huerfanos,
    detectar_punteros_multiples,
    analizar_fragmentacion_heap,
    detectar_buffer_overflow_stack,
    comparar_snapshots,
)
from bishop.core.ascii_visualizer import (
    render_ascii_punteros,
    render_ascii_lista_enlazada,
    render_ascii_arbol_binario,
    render_heap_fragmentation_map,
    render_modo_principiante,
)

runner = CliRunner()


def test_auditar_punteros_colgantes():
    bloque_liberado = BloqueHeap(
        direccion="0x5555555592a0",
        tamanio_bytes=32,
        esta_liberado=True,
    )
    var_dangling = VariableMemoria(
        nombre="ptr_invalido",
        tipo="int*",
        direccion="0x7fffffffe010",
        valor="0x5555555592a0",
        es_puntero=True,
        direccion_apuntada="0x5555555592a0",
    )
    frame = StackFrameMemoria(
        funcion="main",
        direccion_base="0x7fffffffe000",
        direccion_tope="0x7fffffffdff0",
        variables=[var_dangling],
    )
    snap = SnapshotMemoria(
        archivo=Path("test.c"),
        linea=15,
        frames=[frame],
        heap=[bloque_liberado],
    )

    dangling = auditar_punteros_colgantes(snap)
    assert len(dangling) == 1
    assert dangling[0]["variable"] == "ptr_invalido"
    assert dangling[0]["color"] == "red"


def test_detectar_fugas_y_huerfanos():
    bloque_huerfano = BloqueHeap(
        direccion="0x555555559999",
        tamanio_bytes=64,
        esta_liberado=False,
        punteros_referenciantes=[],
    )
    frame = StackFrameMemoria(
        funcion="main",
        direccion_base="0x7fffffffe000",
        direccion_tope="0x7fffffffdff0",
        variables=[],
    )
    snap = SnapshotMemoria(
        archivo=Path("test.c"),
        linea=20,
        frames=[frame],
        heap=[bloque_huerfano],
    )

    huerfanos = detectar_fugas_y_huerfanos(snap)
    assert len(huerfanos) == 1
    assert huerfanos[0]["direccion"] == "0x555555559999"
    assert huerfanos[0]["color"] == "yellow"


def test_detectar_punteros_multiples():
    v1 = VariableMemoria(
        nombre="p1", tipo="int*", direccion="0x7fff1", valor="0x5500", es_puntero=True, direccion_apuntada="0x5500"
    )
    v2 = VariableMemoria(
        nombre="p2", tipo="int*", direccion="0x7fff2", valor="0x5500", es_puntero=True, direccion_apuntada="0x5500"
    )
    frame = StackFrameMemoria(
        funcion="main", direccion_base="0x7fff0", direccion_tope="0x7ffe0", variables=[v1, v2]
    )
    snap = SnapshotMemoria(archivo=Path("test.c"), linea=5, frames=[frame])

    multiples = detectar_punteros_multiples(snap)
    assert "0x5500" in multiples
    assert len(multiples["0x5500"]) == 2


def test_analizar_fragmentacion_heap():
    b1 = BloqueHeap(direccion="0x10", tamanio_bytes=100, esta_liberado=False)
    b2 = BloqueHeap(direccion="0x20", tamanio_bytes=50, esta_liberado=True)
    snap = SnapshotMemoria(archivo=Path("test.c"), linea=1, heap=[b1, b2])

    frag = analizar_fragmentacion_heap(snap, heap_total_bytes=1000)
    assert frag["bytes_ocupados"] == 100
    assert frag["bloques_activos"] == 1
    assert frag["bloques_liberados"] == 1
    assert "tasa_fragmentacion" in frag


def test_detectar_buffer_overflow_stack():
    # v1 ocupa 16 bytes pero la distancia a v2 es de 8 bytes
    v1 = VariableMemoria(
        nombre="buffer", tipo="char[16]", direccion="0x1000", valor="...", tamanio_bytes=16
    )
    v2 = VariableMemoria(
        nombre="canary", tipo="int", direccion="0x1008", valor="0", tamanio_bytes=4
    )
    frame = StackFrameMemoria(
        funcion="vulnerable", direccion_base="0x1000", direccion_tope="0x1020", variables=[v1, v2]
    )
    issues = detectar_buffer_overflow_stack(frame)
    assert len(issues) == 1
    assert issues[0]["variable_fuente"] == "buffer"
    assert issues[0]["bytes_solapados"] == 8


def test_comparar_snapshots():
    snap1 = SnapshotMemoria(archivo=Path("t.c"), linea=1, total_bytes_heap_activos=32)
    snap2 = SnapshotMemoria(archivo=Path("t.c"), linea=5, total_bytes_heap_activos=64)
    res = comparar_snapshots(snap1, snap2)
    assert res["delta_heap_bytes"] == 32


def test_ascii_visualizers():
    v1 = VariableMemoria(
        nombre="p", tipo="int*", direccion="0x7000", valor="0x5000", es_puntero=True, direccion_apuntada="0x5000"
    )
    f = StackFrameMemoria(funcion="foo", direccion_base="0x7000", direccion_tope="0x6ff0", variables=[v1])
    b = BloqueHeap(direccion="0x5000", tamanio_bytes=16, esta_liberado=False, contenido="123")
    snap = SnapshotMemoria(archivo=Path("test.c"), linea=10, frames=[f], heap=[b])

    out_ptrs = render_ascii_punteros(snap)
    assert "--->" in out_ptrs
    assert "foo()" in out_ptrs

    out_heap = render_heap_fragmentation_map(snap)
    assert "Mapa de Fragmentación" in out_heap

    out_beg = render_modo_principiante(snap)
    assert "PRINCIPIANTES" in out_beg
    assert "STACK" in out_beg

    lista_ascii = render_ascii_lista_enlazada([{"direccion": "0x1", "valor": 10}, {"direccion": "0x2", "valor": 20}])
    assert "0x1" in lista_ascii and "0x2" in lista_ascii and "NULL" in lista_ascii

    arbol_ascii = render_ascii_arbol_binario({"valor": "raiz", "izq": {"valor": "izq"}, "der": None})
    assert "raiz" in arbol_ascii


def test_cli_bishop_new_commands(tmp_path):
    c_code = """#include <stdio.h>
#include <stdlib.h>
int main(void) {
    int *ptr = malloc(32);
    int x = 42;
    return 0;
}
"""
    c_file = tmp_path / "main.c"
    c_file.write_text(c_code, encoding="utf-8")

    res_beg = runner.invoke(app, ["beginner", str(c_file)])
    assert res_beg.exit_code == 0
    assert "PRINCIPIANTES" in res_beg.output

    res_map = runner.invoke(app, ["heap-map", str(c_file)])
    assert res_map.exit_code == 0
    assert "Mapa de Fragmentación" in res_map.output

    res_asc = runner.invoke(app, ["ascii", str(c_file)])
    assert res_asc.exit_code == 0
    assert "Visualización de Punteros" in res_asc.output

    res_aud = runner.invoke(app, ["audit", str(c_file)])
    assert res_aud.exit_code in (0, 1)

    res_diff = runner.invoke(app, ["diff", str(c_file), "--antes", "3", "--despues", "5"])
    assert res_diff.exit_code == 0
