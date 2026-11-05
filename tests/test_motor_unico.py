"""Un único motor de memoria: la API Python de gdb (ola R3). Sin él, un dibujo que dice que lo es."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core import snapshot_gdb
from bishop.core.tracer import _generar_snapshot_estatico, capturar_snapshot_gdb

con_gdb = pytest.mark.skipif(not (shutil.which("gcc") and shutil.which("gdb")), reason="hace falta gcc y gdb")

LISTA = """#include <stdlib.h>
typedef struct nodo { int valor; struct nodo *sig; } Nodo;
int main(void) {
    char nombre[16] = "ana";
    Nodo *n = malloc(sizeof(Nodo));
    n->valor = 3;
    n->sig = NULL;
    free(n);
    return nombre[0] == 0;
}
"""


def _fuente(tmp_path, codigo, nombre="prog.c"):
    archivo = tmp_path / nombre
    archivo.write_text(codigo, encoding="utf-8")
    return archivo


@con_gdb
def test_la_memoria_real_trae_direcciones_y_tipos_reales(tmp_path):
    snap = capturar_snapshot_gdb(_fuente(tmp_path, LISTA), linea_corte=7)

    assert (snap.origen, snap.motivo) == ("gdb", "")
    variables = {v.nombre: v for v in snap.frames[0].variables}
    assert variables["n"].tipo == "Nodo *" and variables["n"].es_puntero
    assert variables["nombre"].tipo == "char [16]"
    assert snap.heap and snap.heap[0].punteros_referenciantes == ["n"]
    assert snap.to_dict()["origen"] == "gdb"


@con_gdb
def test_no_quedan_archivos_junto_al_fuente(tmp_path):
    capturar_snapshot_gdb(_fuente(tmp_path, LISTA), linea_corte=7)

    assert [p.name for p in tmp_path.iterdir()] == ["prog.c"]


@pytest.mark.skipif(shutil.which("gcc") is None, reason="hace falta gcc")
def test_si_no_compila_lo_dice_sin_mostrar_a_gcc(tmp_path):
    snap = capturar_snapshot_gdb(_fuente(tmp_path, "int main(void) { int a = 1 return a; }\n"))

    assert snap.origen == "estatico"
    assert "no compila" in snap.motivo
    assert "expected" not in snap.motivo and "\n" not in snap.motivo


def test_sin_gdb(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_gdb.shutil, "which", lambda _: None)

    snap = capturar_snapshot_gdb(_fuente(tmp_path, LISTA))

    assert snap.origen == "estatico" and "gdb" in snap.motivo


@con_gdb
def test_si_el_programa_termina_antes_del_punto_de_corte(tmp_path):
    snap = capturar_snapshot_gdb(_fuente(tmp_path, "int nunca(void) { return 1; }\nint main(void) { return 0; }\n"),
                                 punto_corte="nunca")

    assert snap.origen == "estatico" and "terminó antes" in snap.motivo


def test_gdb_sin_python_se_informa(tmp_path, monkeypatch):
    def sin_python(*args, **kwargs):
        raise snapshot_gdb.ErrorDeSnapshot("gdb no pudo leer la memoria: puede que no tenga soporte de Python.\ndetalle crudo")

    monkeypatch.setattr(snapshot_gdb, "capturar_con_python_gdb", sin_python)

    snap = capturar_snapshot_gdb(_fuente(tmp_path, LISTA))

    assert snap.motivo == "gdb no pudo leer la memoria: puede que no tenga soporte de Python."


def test_el_dibujo_del_fuente_no_inventa_contenido(tmp_path):
    snap = _generar_snapshot_estatico(_fuente(tmp_path, "int *p = malloc(10);\n"), 1, "motivo")

    assert snap.heap[0].contenido == "‹sin ejecutar›"
    assert (snap.origen, snap.motivo) == ("estatico", "motivo")


@pytest.mark.skipif(shutil.which("gcc") is None, reason="hace falta gcc")
@pytest.mark.parametrize("comando", ["snapshot", "heap", "ascii"])
def test_cada_comando_avisa_si_no_es_la_memoria_real(tmp_path, comando):
    res = CliRunner().invoke(app, [comando, str(_fuente(tmp_path, "int main(void) { int a = 1 return a; }\n"))])

    assert "no es la memoria real" in res.output


@pytest.mark.skipif(shutil.which("gcc") is None, reason="hace falta gcc")
def test_el_json_dice_el_origen(tmp_path):
    res = CliRunner().invoke(app, ["trace", str(_fuente(tmp_path, "int main(void) { int a = 1 return a; }\n")), "--json"])

    datos = json.loads(res.stdout)
    assert datos["origen"] == "estatico" and "no compila" in datos["motivo"]


@con_gdb
def test_doctor_comprueba_que_gdb_tenga_python():
    res = CliRunner().invoke(app, ["doctor", "--json"])

    assert json.loads(res.stdout)["ok"] is True
