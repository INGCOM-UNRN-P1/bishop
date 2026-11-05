"""Un único motor de memoria: la API Python de gdb (ola R3). Sin él, un dibujo que dice que lo es."""

import json
import os
import shutil

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core import snapshot_gdb
from bishop.core.diagrama import MemoriaNoReal, diagrama_de_fuente
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


NO_COMPILA = "int main(void) { int a = 1 return a; }\n"
con_gcc = pytest.mark.skipif(shutil.which("gcc") is None, reason="hace falta gcc")


@con_gcc
def test_un_diagrama_no_sale_de_un_dibujo_del_fuente(tmp_path):
    with pytest.raises(MemoriaNoReal, match="no compila"):
        diagrama_de_fuente(_fuente(tmp_path, NO_COMPILA))


@con_gcc
@pytest.mark.parametrize("opciones", [[], ["--tda", "lista"]])
def test_el_comando_diagrama_falla_sin_escribir_nada(tmp_path, opciones):
    salida = tmp_path / "diagrama.mmd"

    res = CliRunner().invoke(app, ["diagram", str(_fuente(tmp_path, NO_COMPILA)), "-o", str(salida), *opciones])

    assert res.exit_code == 2 and "no compila" in res.output and not salida.exists()


@con_gcc
def test_ripley_no_audita_un_dibujo_del_fuente(tmp_path):
    from bishop.ripley_plugin import BishopPlugin

    _fuente(tmp_path, NO_COMPILA)

    resultado = BishopPlugin().execute(tmp_path, {})

    assert resultado["observaciones"] == []
    assert "no compila" in resultado["sin_ejecutar"][0]["motivo"]


@con_gcc
def test_el_informe_para_dredd_no_da_cifras_de_un_dibujo(tmp_path):
    from bishop.cli import generar_seccion_markdown

    seccion = generar_seccion_markdown(capturar_snapshot_gdb(_fuente(tmp_path, NO_COMPILA)))

    assert "Sin memoria real" in seccion and "Bloques activos" not in seccion


@con_gdb
@pytest.mark.skipif(not os.path.isdir("/proc/self"), reason="hace falta /proc")
def test_el_heap_sale_del_mapa_de_proc(tmp_path, monkeypatch):
    original = snapshot_gdb.script_gdb
    monkeypatch.setattr(snapshot_gdb, "script_gdb",
                        lambda: original().replace('CONFIG.get("seguir_reservas", True)', "False"))
    codigo = ("#include <stdlib.h>\nstatic int global = 1;\nint main(void) {\n    int *b = &global;\n"
              "    int *c = malloc(8);\n    *c = *b;\n    free(c);\n    return 0;\n}\n")

    datos = snapshot_gdb.capturar_con_python_gdb(_fuente(tmp_path, codigo), "prog.c:7")

    assert len(datos["heap"]) == 1  # c sí, y b, que apunta a datos estáticos, no


def _sin_proc_ni_seguimiento(monkeypatch):
    """Como en Windows: sin mapa de memoria, y sin que malloc esté registrado, el heap es lo que
    reconoce el allocator (`malloc_usable_size` acá, `_msize` allá)."""
    original = snapshot_gdb.script_gdb

    def script():
        return original().replace('CONFIG.get("seguir_reservas", True)', "False").replace(
            "programa = Programa(", "_rangos_heap = lambda: []\nprograma = Programa(")

    monkeypatch.setattr(snapshot_gdb, "script_gdb", script)


@con_gdb
def test_sin_proc_el_allocator_reconoce_los_bloques(tmp_path, monkeypatch):
    _sin_proc_ni_seguimiento(monkeypatch)

    datos = snapshot_gdb.capturar_con_python_gdb(_fuente(tmp_path, LISTA), "prog.c:7")

    assert len(datos["heap"]) == 1 and datos["heap"][0]["tamanio_bytes"] >= 16


@con_gdb
@pytest.mark.skipif(os.name != "nt", reason="malloc_usable_size no valida el puntero: sólo `_msize` lo hace")
def test_en_windows_un_puntero_a_la_pila_o_a_datos_no_es_heap(tmp_path, monkeypatch):
    _sin_proc_ni_seguimiento(monkeypatch)
    codigo = ("#include <stdlib.h>\nstatic int global = 1;\nint main(void) {\n    int local = 2;\n"
              "    int *a = &local;\n    int *b = &global;\n    int *c = malloc(8);\n    *c = *a + *b;\n"
              "    free(c);\n    return 0;\n}\n")

    datos = snapshot_gdb.capturar_con_python_gdb(_fuente(tmp_path, codigo), "prog.c:9")

    assert len(datos["heap"]) == 1
