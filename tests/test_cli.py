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


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "doctor" in res.stdout.lower()

    res_json = runner.invoke(app, ["doctor", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert data["herramienta"] == "bishop"
    assert data["ok"] is True
