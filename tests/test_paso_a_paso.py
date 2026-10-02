"""`bishop trace --html`: ejecución paso a paso con la API Python de gdb (revisión, 05 §3)."""

import json
import os
import re
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core.html_traza import generar_html_traza
from bishop.core.paso_a_paso import ErrorDeTraza, TrazaPasoAPaso, _texto_de_salida, trazar_paso_a_paso

runner = CliRunner()
con_gdb = pytest.mark.skipif(not (shutil.which("gdb") and shutil.which("gcc")), reason="hace falta gcc y gdb")

PROGRAMA = """\
#include <stdio.h>

int sumar(const int *v, int n)
{
    int total = 0;
    for (int i = 0; i < n; i++) {
        total += v[i];
    }
    return total;
}

int main(void)
{
    int datos[3] = {4, 5, 6};
    char *nombre = "ana";
    printf("suma: %d\\n", sumar(datos, 3));
    printf("%s\\n", nombre);
    return 0;
}
"""


def _fuente(tmp_path, texto=PROGRAMA, nombre="suma.c"):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def _variables(paso, marco=0):
    return {v["nombre"]: v for v in paso["pila"][marco]["variables"]}


@con_gdb
def test_traza_linea_por_linea(tmp_path):
    traza = trazar_paso_a_paso(_fuente(tmp_path))
    assert traza.codigo_salida == 0 and not traza.senal and not traza.truncado
    assert traza.salida == "suma: 15\nana\n"
    lineas = [p["linea"] for p in traza.pasos]
    assert lineas[0] == 14 and 7 in lineas and lineas[-1] == 19  # la llave final de main también es un paso
    # Entra a sumar() (dos marcos en la pila) y no a printf (no es código del estudiante).
    dentro = [p for p in traza.pasos if p["funcion"] == "sumar"]
    assert dentro and all(len(p["pila"]) == 2 for p in dentro)
    assert {p["funcion"] for p in traza.pasos} == {"main", "sumar"}
    # Una local aparece recién después de su declaración; la i del for sigue visible al volver a él.
    assert "datos" not in _variables(traza.pasos[0])
    vueltas = [p for p in dentro if p["linea"] == 6 and "i" in _variables(p)]
    assert len(vueltas) == 3
    assert _variables(traza.pasos[-1])["nombre"]["apunta"] == '"ana"'
    assert _variables(dentro[0])["v"]["puntero"] is True
    # La salida crece en el paso que la imprime.
    antes_del_segundo_printf = [p for p in traza.pasos if p["linea"] == 17][0]
    assert traza.pasos[0]["salida"] == 0 and antes_del_segundo_printf["salida"] == len("suma: 15\n")
    assert traza.pasos[-1]["salida"] == len(traza.salida)


@con_gdb
@pytest.mark.skipif(os.name == "nt", reason="MinGW no siempre trae libssp")
def test_con_stack_protector_el_primer_paso_no_es_la_llave(tmp_path, monkeypatch):
    """Ubuntu compila con -fstack-protector-strong por defecto: gdb se detenía en la llave de apertura
    de main (línea 13, donde se carga el canario) y ese era el primer paso de la traza."""
    from bishop.core import tracer

    def compilar(fuente, directorio):
        binario = directorio / fuente.stem
        res = subprocess.run(["gcc", "-g", "-O0", "-fstack-protector-strong", str(fuente), "-o", str(binario)],
                             capture_output=True, text=True)
        return res.returncode == 0, binario, res.stderr

    monkeypatch.setattr(tracer, "compilar_con_simbolos", compilar)
    traza = trazar_paso_a_paso(_fuente(tmp_path))
    lineas = [p["linea"] for p in traza.pasos]
    assert lineas[0] == 14 and 13 not in lineas and lineas[-1] == 19
    assert traza.salida == "suma: 15\nana\n"


@con_gdb
def test_lo_apuntado_no_lleva_el_simbolo_mas_cercano(tmp_path):
    """gdb antepone el símbolo más cercano a lo que apunta un char *: `<texto> "hola"` para un arreglo
    global y, en Windows, `<__mingw_module_is_dll+16> "ana"` para un literal (N-BISHOP-01)."""
    fuente = _fuente(tmp_path, '#include <stdio.h>\nchar texto[] = "hola";\nint main(void)\n{\n'
                               '    char *p = texto;\n    printf("%s\\n", p);\n    return 0;\n}\n', "global.c")
    traza = trazar_paso_a_paso(fuente)
    assert _variables(traza.pasos[-1])["p"]["apunta"] == '"hola"'


def test_salida_de_windows_sin_retornos_de_carro():
    """En Windows el programa escribe en modo texto: «\\n» sale como «\\r\\n» (N-ECO-10)."""
    assert _texto_de_salida(b"suma: 15\r\nana\r\n", "replace", en_windows=True) == "suma: 15\nana\n"
    assert _texto_de_salida(b"a\r\n", "replace", en_windows=False) == "a\r\n"


@con_gdb
def test_senal_entrada_y_limite_de_pasos(tmp_path):
    fuente = _fuente(tmp_path, "#include <stdio.h>\nint main(void)\n{\n    int n = 0;\n    scanf(\"%d\", &n);\n"
                               "    int *p = NULL;\n    return *p + n;\n}\n", "segv.c")
    (tmp_path / "entrada.txt").write_text("7\n", encoding="utf-8")
    traza = trazar_paso_a_paso(fuente, entrada=tmp_path / "entrada.txt")
    assert traza.senal == "SIGSEGV" and traza.pasos[-1]["senal"] == "SIGSEGV" and traza.pasos[-1]["linea"] == 7
    assert _variables(traza.pasos[-1])["n"]["valor"] == "7" and _variables(traza.pasos[-1])["p"]["valor"] == "NULL"
    corta = trazar_paso_a_paso(_fuente(tmp_path), max_pasos=5)
    assert corta.truncado and len(corta.pasos) == 5


@con_gdb
def test_cli_html(tmp_path):
    fuente = _fuente(tmp_path)
    pagina = tmp_path / "traza.html"
    res = runner.invoke(app, ["trace", str(fuente), "--html", str(pagina)])
    assert res.exit_code == 0, res.output
    contenido = pagina.read_text(encoding="utf-8")
    datos = json.loads(re.search(r'id="datos">(.*?)</script>', contenido, re.S).group(1).replace("<\\/", "</"))
    assert datos["schema_version"] == "1.0.0" and datos["codigo"][0] == "#include <stdio.h>" and datos["pasos"]
    roto = _fuente(tmp_path, "int main(void) { return 0 }\n", "roto.c")
    res = runner.invoke(app, ["trace", str(roto), "--html", str(tmp_path / "x.html")])
    assert res.exit_code == 2 and "no compila" in res.output


def test_html_escapa_el_cierre_de_script(tmp_path):
    fuente = _fuente(tmp_path, "/* </script><script>alert(1)</script> */\nint main(void) { return 0; }\n")
    traza = TrazaPasoAPaso(fuente=str(fuente), pasos=[{"linea": 2, "archivo": "suma.c", "funcion": "main",
                                                       "pila": [], "salida": 0, "senal": None}],
                           salida="</script>", codigo_salida=0)
    pagina = generar_html_traza(traza)
    # El único cierre de </script> del bloque de datos es el propio.
    bloque = re.search(r'id="datos">(.*?)</script>', pagina, re.S).group(1)
    assert "</" not in bloque and json.loads(bloque.replace("<\\/", "</"))["salida"] == "</script>"


def test_sin_gdb(monkeypatch, tmp_path):
    monkeypatch.setattr("bishop.core.paso_a_paso.shutil.which", lambda nombre: None)
    with pytest.raises(ErrorDeTraza, match="gdb"):
        trazar_paso_a_paso(_fuente(tmp_path))
