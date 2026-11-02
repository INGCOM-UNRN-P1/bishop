"""Memoria en vivo (Ola 42): el módulo que un depurador carga en su sesión de gdb con `source`
(`bishop gdb-script`), sigue el heap sin detener el programa y saca la foto de cada parada."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bishop.cli import app

FUENTE = Path(__file__).parent / "datos" / "memoria_en_vivo.c"
MODULO = Path(__file__).parent.parent / "src" / "bishop" / "gdb_memoria.py"


def _gdb_con_python() -> bool:
    gdb = shutil.which("gdb")
    if not gdb or not shutil.which("gcc"):
        return False
    res = subprocess.run([gdb, "-nx", "-batch", "-ex", "python print(1)"], capture_output=True, text=True)
    return res.stdout.strip() == "1"


def test_gdb_script_da_la_ruta_del_modulo():
    res = CliRunner().invoke(app, ["gdb-script"])
    assert res.exit_code == 0
    assert Path(res.output.strip()).resolve() == MODULO.resolve()


@pytest.fixture(scope="module")
def fotos(tmp_path_factory):
    if not _gdb_con_python():
        pytest.skip("requiere gcc y gdb con Python")
    tmp = tmp_path_factory.mktemp("vivo")
    binario = tmp / "programa"
    subprocess.run(["gcc", "-g", "-O0", "-o", str(binario), str(FUENTE)], check=True)
    pasos = ["-ex", "next"] * 6
    subprocess.run(
        ["gdb", "-nx", "-batch", "-ex", "set debuginfod enabled off", "-ex", f"source {MODULO}",
         "-ex", f"bishop-seguir {FUENTE.parent}", "-ex", "break main", "-ex", "run", *pasos,
         "-ex", f"bishop-memoria {tmp / 'primera.json'}", "-ex", f"break {FUENTE.name}:26", "-ex", "continue",
         "-ex", f"bishop-memoria {tmp / 'segunda.json'}", str(binario)],
        capture_output=True, text=True, timeout=60, cwd=tmp,
    )
    return [json.loads((tmp / f"{n}.json").read_text(encoding="utf-8")) for n in ("primera", "segunda")]


def test_cada_reserva_con_numero_y_linea(fotos):
    primera, segunda = fotos
    assert [(e["tipo"], e["id"], e["sitio"]["linea"]) for e in primera["eventos"]] == [("malloc", 1, 14)]
    por_id = {b["id"]: b for b in segunda["heap"]}
    assert {i: por_id[i]["sitio"]["linea"] for i in (1, 2, 3)} == {1: 14, 2: 14, 3: 14}
    nodo = por_id[3]
    assert nodo["campos"][0] == {"nombre": "dato", "tipo": "int", "valor": "2"}
    assert nodo["punteros_salientes"] == [{"campo": "sig", "destino": por_id[2]["direccion"]}]


def test_la_biblioteca_no_cuenta_salvo_strdup(fotos):
    _, segunda = fotos
    # printf reserva su búfer: no aparece. strdup reserva para el programa: sí, en su línea.
    copia = next(b for b in segunda["heap"] if b["id"] == 4)
    assert copia["sitio"]["linea"] == 20 and copia["tamanio_bytes"] == 5
    assert copia["esta_liberado"] and copia["sitio_free"]["linea"] == 24


def test_realloc_conserva_el_bloque_y_la_fuga_se_ve(fotos):
    _, segunda = fotos
    eventos = [(e["tipo"], e.get("id"), e.get("tamanio")) for e in segunda["eventos"]]
    assert ("realloc", 5, 400) in eventos and ("free", 4, None) in eventos
    assert sum(1 for e in segunda["eventos"] if e["tipo"] == "free") == 1
    fuga = next(b for b in segunda["heap"] if b["id"] == 5)
    assert fuga["alcanzable"] is False and fuga["tamanio_bytes"] == 400
    assert not any(b.get("alcanzable") is False for b in segunda["heap"] if b["id"] != 5)
