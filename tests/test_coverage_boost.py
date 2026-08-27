"""Tests adicionales para maximizar la cobertura en BISHOP."""

import json
from pathlib import Path
from typer.testing import CliRunner
from rich.console import Console
import bishop.cli
from bishop.cli import app
from bishop.core.models import SnapshotMemoria, StackFrameMemoria, VariableMemoria, BloqueHeap
from bishop.core.visualizer import renderizar_memoria_rich, generar_mermaid_punteros

runner = CliRunner()


def test_visualizer_rich_y_mermaid_completo():
    v1 = VariableMemoria(nombre="x", tipo="int", direccion="0x7fff01", valor="42")
    v2 = VariableMemoria(nombre="ptr", tipo="int*", direccion="0x7fff08", valor="0x555010", es_puntero=True, direccion_apuntada="0x555010")
    f1 = StackFrameMemoria(funcion="main", direccion_base="0x7fff00", direccion_tope="0x7ffef0", variables=[v1, v2])
    f2 = StackFrameMemoria(funcion="vacia", direccion_base="0x7fff20", direccion_tope="0x7fff10", variables=[])

    b1 = BloqueHeap(direccion="0x555010", tamanio_bytes=64, punteros_referenciantes=["ptr"])
    b2 = BloqueHeap(direccion="0x555080", tamanio_bytes=128, punteros_referenciantes=[], esta_liberado=True)

    snap = SnapshotMemoria(
        archivo=Path("test.c"),
        linea=15,
        frames=[f1, f2],
        heap=[b1, b2],
    )

    console = Console(record=True)
    renderizar_memoria_rich(snap, console)
    out = console.export_text()
    assert "Memoria Stack" in out
    assert "Memoria Heap" in out

    mermaid = generar_mermaid_punteros(snap)
    assert "graph LR" in mermaid
    assert "subgraph Stack" in mermaid


def test_cli_trace_rich_and_mermaid(tmp_path):
    fuente = tmp_path / "mem.c"
    fuente.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *p = malloc(sizeof(int) * 10);
        *p = 100;
        free(p);
        return 0;
    }
    """)

    # Trace rich
    res1 = runner.invoke(app, ["trace", str(fuente)])
    assert res1.exit_code == 0

    # Trace mermaid
    res2 = runner.invoke(app, ["trace", str(fuente), "--mermaid"])
    assert res2.exit_code == 0
    assert "graph LR" in res2.stdout


def test_cli_snapshot_and_heap_commands(tmp_path):
    fuente = tmp_path / "heap_test.c"
    fuente.write_text("""
    #include <stdlib.h>
    int main(void) {
        int *buf = malloc(32);
        return 0;
    }
    """)

    # Snapshot
    res_snap = runner.invoke(app, ["snapshot", str(fuente), "--line", "4"])
    assert res_snap.exit_code == 0

    # Snapshot json
    res_snap_j = runner.invoke(app, ["snapshot", str(fuente), "--json"])
    assert res_snap_j.exit_code == 0

    # Heap
    res_heap = runner.invoke(app, ["heap", str(fuente)])
    assert res_heap.exit_code == 0

    # Heap json
    res_heap_j = runner.invoke(app, ["heap", str(fuente), "--json"])
    assert res_heap_j.exit_code == 0


def test_cli_file_not_found():
    res1 = runner.invoke(app, ["trace", "/no/existe.c"])
    assert res1.exit_code == 2

    res2 = runner.invoke(app, ["snapshot", "/no/existe.c"])
    assert res2.exit_code == 2

    res3 = runner.invoke(app, ["heap", "/no/existe.c"])
    assert res3.exit_code == 2


def test_generar_snapshot_estatico(tmp_path):
    from bishop.core.tracer import _generar_snapshot_estatico
    fuente = tmp_path / "static_vars.c"
    fuente.write_text("int a = 10;\nint *p = malloc(10);\n")
    snap = _generar_snapshot_estatico(fuente, 2)
    assert len(snap.frames[0].variables) == 2
    assert len(snap.heap) == 1
    assert snap.heap[0].punteros_referenciantes == ["p"]


def test_cli_main_block(monkeypatch):
    monkeypatch.setattr("sys.argv", ["bishop", "--version"])
    try:
        bishop.cli.main()
    except SystemExit as e:
        assert e.code == 0
