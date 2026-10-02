"""`bishop diagram`: el dueño de los diagramas de memoria (deckard y scorm-tools delegan acá)."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core.diagrama import generar_diagrama, snapshot_desde_dict

runner = CliRunner()
con_gdb = pytest.mark.skipif(not (shutil.which("gcc") and shutil.which("gdb")), reason="hace falta gcc y gdb")

TRAZA_SCORM = {"stack": [{"function": "main", "variables": [
    {"name": "v", "type": "int *", "address": "0x7ffd18", "value": "0x55a1b0", "points_to": "0x55a1b0"},
    {"name": "n", "type": "int", "address": "0x7ffd10", "value": "5"}]}],
    "heap": [{"address": "0x55a1b0", "size": 20, "preview": "{10, 20, 30, 40, 50}"}]}


def test_traza_en_el_formato_de_scorm():
    snap = snapshot_desde_dict(TRAZA_SCORM)
    mermaid = generar_diagrama(snap, "mermaid")
    assert "var_main_v == desreferencia ==> heap_55a1b0" in mermaid
    assert "0x55a1b0 [Heap 20B]" in generar_diagrama(snap, "ascii")


def test_cli_con_traza_json(tmp_path):
    traza = tmp_path / "t.json"
    traza.write_text(json.dumps(TRAZA_SCORM), encoding="utf-8")
    res = runner.invoke(app, ["diagram", str(traza), "--formato", "ascii"])
    assert res.exit_code == 0 and "[int * v @ 0x7ffd18] --->" in res.stdout
    assert runner.invoke(app, ["diagram", str(traza), "--formato", "png"]).exit_code == 2


@con_gdb
def test_cli_con_fuente_real(tmp_path):
    fuente = tmp_path / "m.c"
    fuente.write_text("#include <stdlib.h>\nint main(void)\n{\n    int *v = malloc(5 * sizeof(int));\n    v[0] = 1;\n"
                      "    free(v);\n    return 0;\n}\n", encoding="utf-8")
    res = runner.invoke(app, ["diagram", str(fuente)])
    assert res.exit_code == 0 and "graph LR" in res.stdout and "var_main_v" in res.stdout
