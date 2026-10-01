"""Página HTML navegable de una traza paso a paso (`bishop trace --html`).

Autocontenida (sin bibliotecas ni red): el código con la próxima línea a ejecutar marcada y la recién
ejecutada en otro tono, la pila de llamadas con sus variables (lo que cambió respecto del paso anterior,
resaltado; los punteros, con lo que apuntan) y la salida del programa hasta ese paso. Se navega con los
botones, el deslizador o las flechas del teclado.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from bishop.core.paso_a_paso import TrazaPasoAPaso

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Traza de __TITULO__</title>
<style>
:root {
  --fondo: #f7f7f5; --panel: #ffffff; --texto: #1d1d1f; --tenue: #6b6b70; --borde: #dddddb;
  --actual: #fff1b8; --actual-borde: #e0b400; --previa: #e6f4ea; --cambio: #ffe08a;
  --error: #b42318; --error-fondo: #fdecea; --acento: #2457c5; --codigo: #fbfbfa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fondo: #161618; --panel: #1f1f22; --texto: #ececee; --tenue: #9a9aa2; --borde: #34343a;
    --actual: #4a3f12; --actual-borde: #d4a72c; --previa: #1d3524; --cambio: #5c4a10;
    --error: #ff8a80; --error-fondo: #3d1d1b; --acento: #8ab4ff; --codigo: #1a1a1d;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--fondo); color: var(--texto);
       font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
header { position: sticky; top: 0; z-index: 1; background: var(--panel); border-bottom: 1px solid var(--borde);
         padding: 10px 16px; display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; }
header h1 { font-size: 16px; margin: 0; font-weight: 600; }
.controles { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; flex: 1 1 280px; min-width: 0; }
button { font: inherit; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--borde);
         background: var(--fondo); color: var(--texto); cursor: pointer; }
button:disabled { opacity: .45; cursor: default; }
input[type=range] { flex: 1 1 120px; min-width: 100px; accent-color: var(--acento); }
@media (max-width: 520px) { .texto-boton { display: none; } }
.contador { color: var(--tenue); white-space: nowrap; font-variant-numeric: tabular-nums; }
main { display: grid; grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr); gap: 16px; padding: 16px; }
@media (max-width: 820px) { main { grid-template-columns: minmax(0, 1fr); } }
section { background: var(--panel); border: 1px solid var(--borde); border-radius: 8px; padding: 12px; min-width: 0; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .04em; color: var(--tenue); margin: 0 0 8px; }
.estado { margin: 0 0 10px; }
.estado.error { color: var(--error); background: var(--error-fondo); padding: 6px 8px; border-radius: 6px; }
.codigo { font: 13px/1.5 ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace; background: var(--codigo);
          border-radius: 6px; overflow-x: auto; padding: 4px 0; }
.linea { display: grid; grid-template-columns: 1.6em 3.2em 1fr; white-space: pre; padding: 0 8px; }
.linea .marca { color: var(--actual-borde); font-weight: 700; }
.linea .num { color: var(--tenue); text-align: right; padding-right: 10px; user-select: none; }
.linea.actual { background: var(--actual); box-shadow: inset 3px 0 var(--actual-borde); }
.linea.previa { background: var(--previa); }
.marco { border: 1px solid var(--borde); border-radius: 6px; margin-bottom: 10px; overflow: hidden; }
.marco h3 { margin: 0; font: 600 13px ui-monospace, Menlo, Consolas, monospace; padding: 6px 8px;
            background: var(--codigo); border-bottom: 1px solid var(--borde); }
.marco h3 small { color: var(--tenue); font-weight: 400; }
.marco.activo h3 { box-shadow: inset 3px 0 var(--actual-borde); }
table { width: 100%; border-collapse: collapse; font: 13px ui-monospace, Menlo, Consolas, monospace; }
td { padding: 4px 8px; border-top: 1px solid var(--borde); vertical-align: top; overflow-wrap: anywhere; }
tr:first-child td { border-top: 0; }
td.nombre { font-weight: 600; width: 30%; }
td.tipo { color: var(--tenue); width: 25%; }
td.cambio { background: var(--cambio); }
.etiqueta { font: 11px system-ui, sans-serif; color: var(--tenue); border: 1px solid var(--borde);
            border-radius: 4px; padding: 0 4px; margin-left: 4px; }
.apunta { color: var(--acento); }
.vacio { color: var(--tenue); font-style: italic; padding: 4px 8px; }
pre.salida { margin: 0; white-space: pre-wrap; font: 13px ui-monospace, Menlo, Consolas, monospace;
             background: var(--codigo); border-radius: 6px; padding: 8px; min-height: 2.5em; }
footer { color: var(--tenue); font-size: 13px; padding: 0 16px 16px; }
</style>
</head>
<body>
<header>
  <h1>__TITULO__</h1>
  <div class="controles">
    <button id="inicio" title="Primer paso (Inicio)">⏮</button>
    <button id="atras" title="Paso anterior (←)">◀<span class="texto-boton"> Anterior</span></button>
    <input id="deslizador" type="range" min="0" value="0" aria-label="Paso">
    <button id="adelante" title="Paso siguiente (→)"><span class="texto-boton">Siguiente </span>▶</button>
    <button id="fin" title="Último paso (Fin)">⏭</button>
    <span class="contador" id="contador"></span>
  </div>
</header>
<main>
  <section aria-label="Código">
    <p class="estado" id="estado"></p>
    <div class="codigo" id="codigo"></div>
  </section>
  <div>
    <section aria-label="Pila de llamadas">
      <h2>Pila de llamadas</h2>
      <div id="pila"></div>
    </section>
    <section aria-label="Salida del programa" style="margin-top:16px">
      <h2>Salida del programa</h2>
      <pre class="salida" id="salida"></pre>
    </section>
  </div>
</main>
<footer>La flecha → marca la próxima línea a ejecutar; el verde, la que se acaba de ejecutar. Las variables
que cambiaron respecto del paso anterior se resaltan. Generado por bishop trace --html.</footer>
<script type="application/json" id="datos">__DATOS__</script>
<script>
(function () {
  "use strict";
  var datos = JSON.parse(document.getElementById("datos").textContent);
  var pasos = datos.pasos, actual = 0;
  var $ = function (id) { return document.getElementById(id); };
  var deslizador = $("deslizador");
  deslizador.max = Math.max(pasos.length - 1, 0);

  function el(etiqueta, clase, texto) {
    var e = document.createElement(etiqueta);
    if (clase) e.className = clase;
    if (texto !== undefined) e.textContent = texto;
    return e;
  }

  function valorDe(v) {
    var celda = el("td", "valor");
    celda.appendChild(document.createTextNode(v.valor));
    if (v.apunta !== undefined && v.apunta !== null) {
      celda.appendChild(el("span", "apunta", "  → " + v.apunta));
    }
    return celda;
  }

  function variablesPrevias(i, profundidadDesdeAfuera) {
    if (i === 0) return null;
    var pila = pasos[i - 1].pila, idx = pila.length - 1 - profundidadDesdeAfuera;
    var actualPila = pasos[i].pila, idxActual = actualPila.length - 1 - profundidadDesdeAfuera;
    if (idx < 0 || pila[idx].funcion !== actualPila[idxActual].funcion) return null;
    var mapa = {};
    pila[idx].variables.forEach(function (v) { mapa[v.nombre] = v.valor + "|" + (v.apunta || ""); });
    return mapa;
  }

  function mostrar(i) {
    actual = Math.max(0, Math.min(i, pasos.length - 1));
    var paso = pasos[actual], previo = actual > 0 ? pasos[actual - 1] : null;
    deslizador.value = actual;
    $("contador").textContent = "Paso " + (actual + 1) + " de " + pasos.length;
    $("inicio").disabled = $("atras").disabled = actual === 0;
    $("adelante").disabled = $("fin").disabled = actual === pasos.length - 1;

    var estado = $("estado");
    estado.className = "estado";
    if (paso.senal) {
      estado.className = "estado error";
      estado.textContent = "El programa recibió " + paso.senal + " al ejecutar la línea " + paso.linea +
        " (en " + paso.funcion + "()).";
    } else if (actual === pasos.length - 1 && datos.truncado) {
      estado.textContent = "La traza se cortó a los " + datos.max_pasos + " pasos (--max-steps).";
    } else if (actual === pasos.length - 1 && datos.codigo_salida !== null && datos.codigo_salida !== undefined) {
      estado.textContent = "Línea " + paso.linea + " de " + paso.funcion + "(); después, el programa termina " +
        "con código " + datos.codigo_salida + ".";
    } else {
      estado.textContent = "Línea " + paso.linea + " de " + paso.funcion + "(): es la próxima a ejecutar.";
    }

    var codigo = $("codigo");
    codigo.textContent = "";
    var lineaPrevia = previo && previo.archivo === paso.archivo ? previo.linea : null;
    datos.codigo.forEach(function (texto, n) {
      var numero = n + 1, fila = el("div", "linea");
      if (numero === paso.linea) fila.classList.add("actual");
      else if (numero === lineaPrevia) fila.classList.add("previa");
      fila.appendChild(el("span", "marca", numero === paso.linea ? "→" : ""));
      fila.appendChild(el("span", "num", String(numero)));
      fila.appendChild(el("span", "texto", texto || " "));
      codigo.appendChild(fila);
    });
    var marcada = codigo.querySelector(".actual");
    if (marcada) marcada.scrollIntoView({ block: "nearest" });

    var pila = $("pila");
    pila.textContent = "";
    paso.pila.forEach(function (marco, k) {
      var caja = el("div", "marco" + (k === 0 ? " activo" : ""));
      var titulo = el("h3", "", marco.funcion + "() ");
      titulo.appendChild(el("small", "", "línea " + marco.linea));
      caja.appendChild(titulo);
      var previas = variablesPrevias(actual, paso.pila.length - 1 - k);
      if (!marco.variables.length) {
        caja.appendChild(el("div", "vacio", "sin variables todavía"));
      } else {
        var tabla = el("table");
        marco.variables.forEach(function (v) {
          var fila = el("tr"), nombre = el("td", "nombre", v.nombre);
          if (v.argumento) nombre.appendChild(el("span", "etiqueta", "parámetro"));
          fila.appendChild(nombre);
          fila.appendChild(el("td", "tipo", v.tipo));
          var celda = valorDe(v);
          if (previas && previas[v.nombre] !== undefined && previas[v.nombre] !== v.valor + "|" + (v.apunta || "")) {
            celda.classList.add("cambio");
          }
          fila.appendChild(celda);
          tabla.appendChild(fila);
        });
        caja.appendChild(tabla);
      }
      pila.appendChild(caja);
    });

    var fin = actual === pasos.length - 1 && !datos.truncado ? datos.salida.length : paso.salida;
    $("salida").textContent = datos.salida.slice(0, fin);
  }

  $("inicio").onclick = function () { mostrar(0); };
  $("atras").onclick = function () { mostrar(actual - 1); };
  $("adelante").onclick = function () { mostrar(actual + 1); };
  $("fin").onclick = function () { mostrar(pasos.length - 1); };
  deslizador.oninput = function () { mostrar(parseInt(deslizador.value, 10)); };
  document.addEventListener("keydown", function (e) {
    if (e.target === deslizador) return;
    if (e.key === "ArrowRight") { mostrar(actual + 1); e.preventDefault(); }
    else if (e.key === "ArrowLeft") { mostrar(actual - 1); e.preventDefault(); }
    else if (e.key === "Home") { mostrar(0); e.preventDefault(); }
    else if (e.key === "End") { mostrar(pasos.length - 1); e.preventDefault(); }
  });
  mostrar(0);
})();
</script>
</body>
</html>
"""


def generar_html_traza(traza: TrazaPasoAPaso) -> str:
    """La página de la traza, con los datos embebidos como JSON."""
    fuente = Path(traza.fuente)
    datos = {**traza.to_dict(), "codigo": fuente.read_text(encoding="utf-8", errors="replace").splitlines()}
    # «</» dentro del JSON cerraría el <script> antes de tiempo.
    json_seguro = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    return PLANTILLA.replace("__TITULO__", html.escape(fuente.name)).replace("__DATOS__", json_seguro)
