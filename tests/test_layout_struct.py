"""Ola 18 (QoL #58): `bishop layout` dibuja el layout de un struct con el relleno resaltado; los offsets
los calcula brett."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core.layout_struct import StructNoEncontrado, ascii, layout_de, mermaid, typst

runner = CliRunner()

ALUMNO = """typedef struct
{
    char inicial;
    double promedio;
    int aprobadas;
    char activo;
    long legajo;
} alumno_t;
typedef struct { long double d; } otro_t;
"""


@pytest.fixture
def archivo(tmp_path: Path) -> Path:
    ruta = tmp_path / "alumno.h"
    ruta.write_text(ALUMNO, encoding="utf-8")
    return ruta


def test_offsets_y_relleno_de_brett(archivo):
    layout = layout_de(archivo, "alumno_t")
    assert (layout.tamanio_total, layout.datos_utiles, layout.relleno) == (32, 22, 10)
    assert [(t.nombre, t.offset, t.tamanio, t.es_relleno) for t in layout.tramos] == [
        ("inicial", 0, 1, False), ("relleno", 1, 7, True), ("promedio", 8, 8, False), ("aprobadas", 16, 4, False),
        ("activo", 20, 1, False), ("relleno", 21, 3, True), ("legajo", 24, 8, False)]


def test_un_campo_que_cruza_la_fila_sigue_en_la_siguiente(archivo):
    tramos = layout_de(archivo, "otro_t").tramos
    assert [(t.offset, t.tamanio, t.continua) for t in tramos] == [(0, 8, False), (8, 8, True)]


def test_varios_structs_sin_nombre_pide_elegir(archivo):
    with pytest.raises(StructNoEncontrado, match="alumno_t, otro_t"):
        layout_de(archivo)
    res = runner.invoke(app, ["layout", str(archivo), "--struct", "nada_t"])
    assert res.exit_code == 1 and "no hay un struct 'nada_t'" in res.output


def test_mermaid_resalta_el_relleno(archivo):
    texto = mermaid(layout_de(archivo, "alumno_t"))
    assert texto.startswith("flowchart TB\n")
    assert 't1["+1 · 7 B<br/>relleno"]' in texto and "class t1,t5 relleno" in texto
    assert "classDef relleno fill:#e5e7eb" in texto


def test_typst_con_celdas_proporcionales(archivo):
    texto = typst(layout_de(archivo, "alumno_t"))
    assert "#grid(columns: (1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr, 1fr)" in texto
    assert texto.count("fill: luma(225)") == 2
    assert "grid.cell(colspan: 7," in texto and "22 B de datos y 10 B de relleno" in texto


def test_ascii_y_cli(archivo):
    assert ascii(layout_de(archivo, "alumno_t")).splitlines()[1] == "+  0 |#|.......|  inicial, relleno"
    res = runner.invoke(app, ["layout", str(archivo), "-s", "alumno_t", "-f", "typst"])
    assert res.exit_code == 0 and "luma(225)" in res.stdout
    assert runner.invoke(app, ["layout", str(archivo), "-f", "svg"]).exit_code == 2
