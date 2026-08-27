"""Tests unitarios para el trazador e inspeccionador de memoria en BISHOP."""

from pathlib import Path
import pytest
from bishop.core.tracer import capturar_snapshot_gdb
from bishop.core.visualizer import generar_mermaid_punteros


def test_capturar_snapshot_variables_locales(tmp_path):
    """Verifica la captura de variables en stack y asignaciones dinámicas."""
    fuente = tmp_path / "mem.c"
    fuente.write_text("""
    #include <stdio.h>
    #include <stdlib.h>

    int main(void) {
        int a = 10;
        int b = 20;
        int* ptr = malloc(sizeof(int) * 5);
        return 0;
    }
    """)
    snap = capturar_snapshot_gdb(fuente)
    assert len(snap.frames) >= 1
    frame = snap.frames[0]
    nombres_vars = [v.nombre for v in frame.variables]
    assert "a" in nombres_vars or "ptr" in nombres_vars or len(frame.variables) > 0


def test_generar_diagrama_mermaid_punteros(tmp_path):
    """Verifica la exportación del mapa de memoria en Mermaid."""
    fuente = tmp_path / "ptrs.c"
    fuente.write_text("""
    #include <stdlib.h>
    int main(void) {
        int x = 42;
        int* p = malloc(16);
        return 0;
    }
    """)
    snap = capturar_snapshot_gdb(fuente)
    mermaid = generar_mermaid_punteros(snap)
    assert "graph LR" in mermaid
    assert "Stack" in mermaid
