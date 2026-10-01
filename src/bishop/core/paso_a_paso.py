"""Ejecución paso a paso con la API Python de gdb (`bishop trace --html`).

Revisión 05 §3: faltaba un «Python Tutor para C». bishop mostraba un instante de la memoria; esto ejecuta
el programa línea por línea (`step`, entrando a las funciones del estudiante y saliendo de las de la
biblioteca) y guarda en cada paso la línea, la pila de llamadas con sus variables (los punteros, con lo
que apuntan) y cuánta salida lleva el programa. `html_traza` arma con eso una página navegable.

El script corre dentro de gdb (`gdb -batch -x`): recibe la configuración por un JSON cuya ruta va en la
variable de entorno BISHOP_TRAZA_CONFIG y deja el resultado en otro JSON.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_PASOS = 300

SCRIPT_GDB = r'''
import json, os
import gdb

CONFIG = json.load(open(os.environ["BISHOP_TRAZA_CONFIG"], encoding="utf-8"))
# Por nombre de archivo y sin mayúsculas: en Windows, la ruta que da gdb (C:/Users/…) no coincide
# con la de Python (C:\\Users\\…), ni siquiera con realpath.
def nombre_de(ruta):
    return ruta.replace("\\", "/").rsplit("/", 1)[-1].lower()


NOMBRES = {nombre_de(f) for f in CONFIG["fuentes"]}
pasos, estado = [], {"senal": None, "codigo_salida": None, "truncado": False}


def _al_detenerse(evento):
    if isinstance(evento, gdb.SignalEvent):
        estado["senal"] = evento.stop_signal


def _al_terminar(evento):
    estado["codigo_salida"] = getattr(evento, "exit_code", None)


gdb.events.stop.connect(_al_detenerse)
gdb.events.exited.connect(_al_terminar)


def en_fuente(sal):
    if sal is None or sal.symtab is None:
        return False
    return nombre_de(sal.symtab.filename) in NOMBRES


def describir(valor):
    try:
        tipo = valor.type.strip_typedefs()
        if tipo.code == gdb.TYPE_CODE_PTR:
            direccion = int(valor)
            if direccion == 0:
                return {"valor": "NULL", "puntero": True}
            destino = tipo.target().strip_typedefs()
            apunta = None
            try:
                if destino.code == gdb.TYPE_CODE_INT and destino.sizeof == 1:
                    apunta = valor.format_string(max_elements=60, address=False)  # "ana"
                elif destino.code not in (gdb.TYPE_CODE_VOID, gdb.TYPE_CODE_FUNC):
                    apunta = str(valor.dereference())[:120]
            except (gdb.MemoryError, gdb.error, UnicodeDecodeError):
                apunta = "‹dirección inválida›"
            return {"valor": hex(direccion), "puntero": True, "apunta": apunta}
        return {"valor": str(valor)[:200]}
    except (gdb.error, gdb.MemoryError) as exc:
        return {"valor": "‹" + str(exc) + "›"}


def variables(marco, linea, volvio):
    resultado, vistos = [], set()
    try:
        bloque = marco.block()
    except RuntimeError:
        return resultado
    while bloque is not None:
        for simbolo in bloque:
            if not (simbolo.is_variable or simbolo.is_argument) or simbolo.name in vistos:
                continue
            # Una local declarada más abajo todavía no existe para quien lee el código; la de la línea
            # actual, tampoco, salvo que se haya vuelto a esa línea (la `i` de la cabecera de un for).
            if not simbolo.is_argument and (simbolo.line > linea or (simbolo.line == linea and not volvio)):
                continue
            vistos.add(simbolo.name)
            datos = describir(simbolo.value(marco))
            datos.update(nombre=simbolo.name, tipo=str(simbolo.type), argumento=simbolo.is_argument,
                         declarada=simbolo.line)
            resultado.append(datos)
        if bloque.function is not None:
            break
        bloque = bloque.superblock
    return sorted(resultado, key=lambda v: (not v["argumento"], v["declarada"]))


anterior = []  # (función, línea) de cada marco del paso anterior, desde main hacia adentro


def pila():
    global anterior
    crudos, marco = [], gdb.newest_frame()
    while marco is not None and len(crudos) < 20:
        sal = marco.find_sal()
        if en_fuente(sal):
            crudos.append((marco, sal))
        marco = marco.older()
    marcos, actual = [], []
    for profundidad, (marco, sal) in enumerate(reversed(crudos)):
        # La misma llamada que en el paso anterior (misma función a la misma profundidad, sin haber
        # vuelto antes a un marco de afuera): si la línea anterior era más abajo, se volvió a esta.
        misma = profundidad < len(anterior) and anterior[profundidad][0] == marco.name()
        volvio = misma and anterior[profundidad][1] > sal.line
        marcos.append({"funcion": marco.name(), "linea": sal.line, "archivo": os.path.basename(sal.symtab.filename),
                       "variables": variables(marco, sal.line, volvio)})
        actual.append((marco.name(), sal.line))
    anterior = actual
    return list(reversed(marcos))


def salida_hasta_ahora():
    try:
        return os.path.getsize(CONFIG["salida_programa"])
    except OSError:
        return 0


for orden in ("set pagination off", "set confirm off", "set debuginfod enabled off", "set print pretty off"):
    try:
        gdb.execute(orden, to_string=True)
    except gdb.error:
        pass
if CONFIG.get("envoltorio"):
    gdb.execute("set exec-wrapper " + CONFIG["envoltorio"], to_string=True)
gdb.execute("break " + CONFIG["inicio"], to_string=True)
# En Windows gdb hace la redirección sin shell: las rutas van entre comillas dobles.
comilla = '"' if os.name == "nt" else "'"
redireccion = " > " + comilla + CONFIG["salida_programa"] + comilla + " 2>&1"
if CONFIG.get("entrada"):
    redireccion = " < " + comilla + CONFIG["entrada"] + comilla + redireccion
gdb.execute("run" + redireccion, to_string=True)

while True:
    try:
        marco = gdb.selected_frame()
        sal = marco.find_sal()
    except gdb.error:
        break  # el programa terminó
    if not en_fuente(sal):
        try:
            gdb.execute("finish", to_string=True)  # una función de la biblioteca: volver al código
        except gdb.error:
            break
        continue
    if len(pasos) >= CONFIG["max_pasos"]:
        estado["truncado"] = True
        break
    pasos.append({"linea": sal.line, "archivo": os.path.basename(sal.symtab.filename),
                  "funcion": marco.name(), "pila": pila(), "salida": salida_hasta_ahora(),
                  "senal": estado["senal"]})
    if estado["senal"]:
        break  # el programa recibió una señal (SIGSEGV…): el último paso muestra dónde
    try:
        gdb.execute("step", to_string=True)
    except gdb.error:
        break

try:
    gdb.execute("kill", to_string=True)
except gdb.error:
    pass
json.dump({"pasos": pasos, **estado}, open(CONFIG["resultado"], "w", encoding="utf-8"), ensure_ascii=False)
'''


class ErrorDeTraza(Exception):
    """No se pudo trazar: falta gdb, el programa no compila o gdb no devolvió resultado."""


@dataclass
class TrazaPasoAPaso:
    fuente: str
    pasos: List[Dict[str, Any]] = field(default_factory=list)
    salida: str = ""
    senal: Optional[str] = None
    codigo_salida: Optional[int] = None
    truncado: bool = False
    max_pasos: int = MAX_PASOS

    def to_dict(self) -> Dict[str, Any]:
        return {"schema_version": "1.0.0", "fuente": self.fuente, "pasos": self.pasos, "salida": self.salida,
                "senal": self.senal, "codigo_salida": self.codigo_salida, "truncado": self.truncado,
                "max_pasos": self.max_pasos}


def trazar_paso_a_paso(fuente: Path, entrada: Optional[Path] = None, inicio: str = "main",
                       max_pasos: int = MAX_PASOS, timeout: float = 60.0) -> TrazaPasoAPaso:
    """Compila `fuente` con -g y la ejecuta paso a paso dentro de gdb."""
    from bishop.core.tracer import compilar_con_simbolos

    gdb = shutil.which("gdb")
    if not gdb:
        raise ErrorDeTraza("no se encontró gdb: la traza paso a paso lo necesita (bishop doctor).")
    with tempfile.TemporaryDirectory(prefix="bishop-traza-") as tmp:
        directorio = Path(tmp)
        ok, binario, error = compilar_con_simbolos(fuente, directorio)
        if not ok or binario is None:
            raise ErrorDeTraza(f"{fuente.name} no compila:\n{error.strip()}")
        configuracion = {
            "fuentes": [os.path.realpath(fuente)],
            "inicio": inicio,
            "max_pasos": max_pasos,
            "entrada": str(entrada.resolve()) if entrada else None,
            "salida_programa": str(directorio / "salida.txt"),
            "resultado": str(directorio / "traza.json"),
            # Sin búfer, la salida aparece en el paso que la imprime y no recién al final. stdbuf usa
            # LD_PRELOAD, que en Windows no existe: ahí la salida aparece cuando el programa la vuelca.
            "envoltorio": "stdbuf -o0 -e0" if shutil.which("stdbuf") and os.name != "nt" else None,
        }
        (directorio / "config.json").write_text(json.dumps(configuracion), encoding="utf-8")
        (directorio / "traza.py").write_text(SCRIPT_GDB, encoding="utf-8")
        entorno = {**os.environ, "BISHOP_TRAZA_CONFIG": str(directorio / "config.json")}
        try:
            res = subprocess.run([gdb, "-nx", "-batch", "-x", str(directorio / "traza.py"), str(binario)],
                                 capture_output=True, text=True, timeout=timeout, env=entorno)
        except subprocess.TimeoutExpired:
            raise ErrorDeTraza(f"la traza superó {timeout:g} s: probá con menos pasos (--max-steps).") from None
        resultado = directorio / "traza.json"
        if not resultado.is_file():
            raise ErrorDeTraza("gdb no pudo trazar el programa:\n" + (res.stderr or res.stdout).strip()[-1500:])
        datos = json.loads(resultado.read_text(encoding="utf-8"))
        salida_programa = directorio / "salida.txt"
        crudo = salida_programa.read_bytes() if salida_programa.is_file() else b""
    # gdb cuenta bytes; la página corta el texto por caracteres («leí» son 4 bytes y 3 caracteres).
    for paso in datos["pasos"]:
        paso["salida"] = len(crudo[:paso["salida"]].decode("utf-8", errors="ignore"))
    salida = crudo.decode("utf-8", errors="replace")
    return TrazaPasoAPaso(fuente=str(fuente), pasos=datos["pasos"], salida=salida, senal=datos.get("senal"),
                          codigo_salida=datos.get("codigo_salida"), truncado=datos.get("truncado", False),
                          max_pasos=max_pasos)
