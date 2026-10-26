"""`bishop diagram --tda`: la forma de árboles y listas en Typst y Mermaid (Ola 10, QoL #58, #57, #49)."""

import json
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from bishop.cli import app
from bishop.core.diagrama import snapshot_desde_dict
from bishop.core.tda import (ErrorDeTDA, estructura_desde_json, estructura_desde_snapshot, generar_diagrama_tda,
                             posiciones_arbol, punto_final_de_main, recorrido_lista)

runner = CliRunner()
con_gdb = pytest.mark.skipif(not (shutil.which("gdb") and shutil.which("gcc")), reason="hace falta gcc y gdb")

ARBOL = """\
#include <stdlib.h>

typedef struct nodo {
    int dato;
    struct nodo *izq;
    struct nodo *der;
} Nodo;

Nodo *insertar(Nodo *raiz, int dato)
{
    if (raiz == NULL) {
        Nodo *n = malloc(sizeof(Nodo));
        n->dato = dato;
        n->izq = NULL;
        n->der = NULL;
        return n;
    }
    if (dato < raiz->dato) {
        raiz->izq = insertar(raiz->izq, dato);
    } else {
        raiz->der = insertar(raiz->der, dato);
    }
    return raiz;
}

int main(void)
{
    Nodo *raiz = NULL;
    int valores[] = {8, 3, 10, 1, 6, 14};
    for (int i = 0; i < 6; i++) {
        raiz = insertar(raiz, valores[i]);
    }
    return 0;
}
"""


def _nodo(direccion, dato, izq=None, der=None):
    salientes = [{"campo": c, "destino": d} for c, d in (("izq", izq), ("der", der)) if d]
    contenido = f"{{dato={dato}, izq={izq or 'NULL'}, der={der or 'NULL'}}}"
    return {"direccion": direccion, "tamanio_bytes": 24, "tipo": "struct nodo", "contenido": contenido,
            "punteros_salientes": salientes}


def _snapshot_arbol():
    # 8 con hijos 3 (sólo derecho: 6) y 10 (sin hijos); además una variable suelta que apunta al 3.
    return snapshot_desde_dict({
        "frames": [{"funcion": "main", "variables": [
            {"nombre": "aux", "tipo": "Nodo *", "valor": "0x20", "es_puntero": True, "direccion_apuntada": "0x20"},
            {"nombre": "raiz", "tipo": "Nodo *", "valor": "0x10", "es_puntero": True, "direccion_apuntada": "0x10"},
        ]}],
        "heap": [_nodo("0x10", 8, "0x20", "0x30"), _nodo("0x20", 3, None, "0x40"), _nodo("0x30", 10),
                 _nodo("0x40", 6)],
    })


def test_arbol_desde_la_memoria_elige_la_raiz_y_respeta_los_lados():
    est = estructura_desde_snapshot(_snapshot_arbol())
    assert est.nombre_raiz == "raiz" and est.nodos[est.raiz].etiqueta == "8"
    pos, aristas, binario = posiciones_arbol(est)
    assert binario and len(aristas) == 3
    x = {est.nodos[i].etiqueta: p[0] for i, p in pos.items()}
    nivel = {est.nodos[i].etiqueta: p[1] for i, p in pos.items()}
    # Inorden: 3 < 6 < 8 < 10, y el 6 (hijo derecho del 3) queda a la derecha del 3 aunque no haya izquierdo.
    assert x["3"] < x["6"] < x["8"] < x["10"] and nivel == {"8": 0, "3": 1, "10": 1, "6": 2}
    assert estructura_desde_snapshot(_snapshot_arbol(), raiz="aux").nombre_raiz == "aux"
    with pytest.raises(ErrorDeTDA, match="no hay un puntero «otro»"):
        estructura_desde_snapshot(_snapshot_arbol(), raiz="otro")


def test_mermaid_del_arbol_marca_el_lado_vacio():
    texto = generar_diagrama_tda(estructura_desde_snapshot(_snapshot_arbol()), "arbol", "mermaid")
    assert texto.startswith("graph TD") and 'raiz_var(["raiz"])' in texto
    # El 3 tiene sólo hijo derecho: el izquierdo se dibuja como NULL, antes del 6.
    lineas = texto.splitlines()
    nulo = next(i for i, l in enumerate(lineas) if "nulo1[NULL]" in l)
    assert "-->" in lineas[nulo + 1] and "classDef nulo" in texto
    assert '"8"' in texto and "nulo2" not in texto  # el 10 y el 6 son hojas: sin NULL


def test_typst_del_arbol_es_vectorial_y_sin_paquetes():
    texto = generar_diagrama_tda(estructura_desde_snapshot(_snapshot_arbol()), "arbol", "typst")
    assert texto.startswith("// Árbol generado por bishop") and "#import" not in texto
    assert texto.count("#place(line(") == 4  # tres aristas y la flecha de la variable raiz
    assert texto.count("radius:") == 4 and "[8]" in texto and "polygon" in texto


def test_arbol_desde_json_con_hojas_sueltas_y_n_ario():
    est = estructura_desde_json({"raiz": {"dato": "+", "izq": 2, "der": {"dato": "x", "der": {"dato": "y"}}},
                                 "nombre": "a"}, "arbol")
    etiquetas = sorted(n.etiqueta for n in est.nodos.values())
    assert etiquetas == ["+", "2", "x", "y"] and est.nombre_raiz == "a"
    nario = estructura_desde_json({"v": "A", "hijos": [{"v": "B"}, {"v": "C"}, {"v": "D"}]}, "arbol")
    pos, aristas, binario = posiciones_arbol(nario)
    assert not binario and len(aristas) == 3
    x = {nario.nodos[i].etiqueta: p[0] for i, p in pos.items()}
    assert x["B"] < x["C"] < x["D"] and x["A"] == x["C"]  # el padre, centrado sobre sus hijos


def test_listas_simple_doble_y_circular():
    simple = estructura_desde_json([1, 2, 3], "lista")
    assert recorrido_lista(simple)[1:] == (False, False, True)
    texto = generar_diagrama_tda(simple, "lista", "mermaid")
    assert "n1 --> n2" in texto and "n3 --> nulo[NULL]" in texto
    doble = estructura_desde_json({"valores": [1, 2], "doble": True, "circular": True}, "lista")
    orden, es_doble, circular, nulo = recorrido_lista(doble)
    assert len(orden) == 2 and es_doble and circular and not nulo
    assert "n2 <--> n1" in generar_diagrama_tda(doble, "lista", "mermaid")
    typst = generar_diagrama_tda(doble, "lista", "typst")
    assert typst.startswith("// Lista generado por bishop")
    assert "NULL" not in typst and typst.count("rect(") == 2


def test_errores():
    with pytest.raises(ErrorDeTDA, match="formato"):
        generar_diagrama_tda(estructura_desde_json([1], "lista"), "lista", "ascii")
    with pytest.raises(ErrorDeTDA, match="vacío"):
        generar_diagrama_tda(estructura_desde_json([], "lista"), "lista", "typst")
    with pytest.raises(ErrorDeTDA, match="una lista se escribe"):
        estructura_desde_json({"x": 1}, "lista")
    vacio = snapshot_desde_dict({"frames": [{"funcion": "main", "variables": []}], "heap": []})
    with pytest.raises(ErrorDeTDA, match="no se encontró un TDA"):
        estructura_desde_snapshot(vacio)


def test_punto_final_de_main(tmp_path):
    fuente = tmp_path / "arbol.c"
    fuente.write_text(ARBOL, encoding="utf-8")
    assert punto_final_de_main(fuente) == "arbol.c:34"


def test_cli_json_a_typst(tmp_path):
    entrada = tmp_path / "arbol.json"
    entrada.write_text(json.dumps({"dato": 5, "izq": {"dato": 2}, "der": None}), encoding="utf-8")
    salida = tmp_path / "arbol.typ"
    res = runner.invoke(app, ["diagram", str(entrada), "--tda", "arbol", "--formato", "typst", "-o", str(salida)])
    assert res.exit_code == 0, res.output
    assert "[5]" in salida.read_text(encoding="utf-8")
    res = runner.invoke(app, ["diagram", str(entrada), "--tda", "pila", "--formato", "typst"])
    assert res.exit_code == 2 and "desconocido" in res.output


@con_gdb
def test_cli_arbol_desde_la_memoria_real(tmp_path):
    fuente = tmp_path / "arbol.c"
    fuente.write_text(ARBOL, encoding="utf-8")
    res = runner.invoke(app, ["diagram", str(fuente), "--tda", "arbol", "--formato", "mermaid"])
    assert res.exit_code == 0, res.output
    for valor in (8, 3, 10, 1, 6, 14):
        assert f'(("{valor}"))' in res.output
    assert 'raiz_var(["raiz"])' in res.output


@pytest.mark.skipif(not shutil.which("typst"), reason="hace falta typst")
def test_el_typst_compila(tmp_path):
    for nombre, datos, tda in (("a", {"dato": 5, "izq": {"dato": 2, "der": 3}}, "arbol"),
                               ("l", {"valores": ["ana", 2], "doble": True, "circular": True}, "lista")):
        diagrama = generar_diagrama_tda(estructura_desde_json(datos, tda), tda, "typst")
        (tmp_path / f"{nombre}.typ").write_text(diagrama, encoding="utf-8")
        res = subprocess.run(["typst", "compile", f"{nombre}.typ", f"{nombre}.pdf"], cwd=tmp_path,
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
