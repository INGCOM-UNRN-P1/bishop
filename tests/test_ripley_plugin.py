from pathlib import Path

from bishop.ripley_plugin import BishopPlugin


def test_bishop_plugin_contract(tmp_path: Path, monkeypatch):
    fuente = tmp_path / "main.c"
    fuente.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    monkeypatch.setattr(
        "bishop.ripley_plugin.capturar_snapshot_gdb",
        lambda archivo, linea_corte=None: type(
            "Snapshot",
            (),
            {
                "heap": [],
                "to_dict": lambda self: {"archivo": str(archivo), "linea": 1},
            },
        )(),
    )

    resultado = BishopPlugin().execute(tmp_path, {})

    assert BishopPlugin().is_available()
    assert resultado["ok"] is True
    assert resultado["observaciones"] == []
