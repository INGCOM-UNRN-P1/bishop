"""Tests de integración de la CLI de BISHOP."""

import json
from pathlib import Path
from typer.testing import CliRunner
from bishop.cli import app

runner = CliRunner()


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "BISHOP" in res.stdout


def test_cli_trace_json(tmp_path):
    fuente = tmp_path / "prog.c"
    fuente.write_text("int main(void) { int x = 5; return 0; }\n")

    res = runner.invoke(app, ["trace", str(fuente), "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert "frames" in data
    assert len(data["frames"]) >= 1


def test_cli_heap(tmp_path):
    fuente = tmp_path / "prog.c"
    fuente.write_text("int main(void) { return 0; }\n")

    res = runner.invoke(app, ["heap", str(fuente)])
    assert res.exit_code == 0


def test_cli_heap_con_malloc_y_break(tmp_path):
    fuente = tmp_path / "mem.c"
    fuente.write_text("""#include <stdlib.h>
int main(void) {
    int *p = malloc(16);
    p[0] = 42;
    free(p);
    return 0;
}
""")
    # 1. Autodetección de breakpoint tras malloc
    res_auto = runner.invoke(app, ["heap", str(fuente), "--json"])
    assert res_auto.exit_code == 0
    bloques_auto = json.loads(res_auto.stdout)
    assert len(bloques_auto) >= 1
    assert "address" in bloques_auto[0]
    assert "direccion" in bloques_auto[0]

    # 2. Breakpoint explícito con --break
    res_break = runner.invoke(app, ["heap", str(fuente), "--break", f"{fuente.name}:5", "--json"])
    assert res_break.exit_code == 0
    bloques_break = json.loads(res_break.stdout)
    assert len(bloques_break) >= 1


def test_cli_json_en_todos_los_comandos(tmp_path):
    fuente = tmp_path / "prog.c"
    fuente.write_text("""#include <stdlib.h>
int main(void) {
    int x = 10;
    int *p = malloc(16);
    return 0;
}
""")
    # report --json
    res = runner.invoke(app, ["report", str(fuente), "--json"])
    assert res.exit_code == 0
    d = json.loads(res.stdout)
    assert d["herramienta"] == "bishop"
    assert "snapshot" in d

    # beginner --json
    res = runner.invoke(app, ["beginner", str(fuente), "--json"])
    assert res.exit_code == 0
    d = json.loads(res.stdout)
    assert d["modo"] == "beginner"

    # heap-map --json
    res = runner.invoke(app, ["heap-map", str(fuente), "--json"])
    assert res.exit_code == 0
    d = json.loads(res.stdout)
    assert "mapa" in d

    # ascii --json
    res = runner.invoke(app, ["ascii", str(fuente), "--json"])
    assert res.exit_code == 0
    d = json.loads(res.stdout)
    assert "frames" in d

    # audit --json
    res = runner.invoke(app, ["audit", str(fuente), "--json"])
    assert res.exit_code in (0, 1)
    d = json.loads(res.stdout)
    assert "punteros_colgantes" in d

    # diff --json
    res = runner.invoke(app, ["diff", str(fuente), "--antes", "3", "--despues", "4", "--json"])
    assert res.exit_code == 0
    d = json.loads(res.stdout)
    assert "diff" in d


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "doctor" in res.stdout.lower()

    res_json = runner.invoke(app, ["doctor", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert data["herramienta"] == "bishop"
    assert data["ok"] is True


def test_cli_error_al_recibir_binario(tmp_path):
    binario = tmp_path / "app.bin"
    binario.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 64)

    for cmd in ("trace", "snapshot", "heap", "report", "beginner", "heap-map", "ascii", "audit", "diff"):
        args = [cmd, str(binario)]
        if cmd == "snapshot":
            args.extend(["--line", "10"])
        elif cmd == "diff":
            args.extend(["--antes", "1", "--despues", "2"])
        res = runner.invoke(app, args)
        assert res.exit_code == 1
        assert "binario ejecutable" in res.stderr
        assert "Traceback" not in res.stderr


def test_tracer_capturar_snapshot_gdb_error_binario(tmp_path):
    import pytest
    from bishop.core.tracer import capturar_snapshot_gdb

    binario = tmp_path / "test_bin"
    binario.write_bytes(b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 32)

    with pytest.raises(ValueError, match="es un binario compilado"):
        capturar_snapshot_gdb(binario)
