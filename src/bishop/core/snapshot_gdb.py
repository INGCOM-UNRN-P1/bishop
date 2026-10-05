"""Snapshot de memoria con la API Python de gdb (revisión 07: `heap` y `ascii` sin parsear texto).

`tracer.capturar_snapshot_gdb` leía la salida de `info locals` como texto: inventaba las
direcciones de las variables, adivinaba los tipos y no veía nada dentro del heap, así que una
lista doblemente enlazada o una matriz `int **` se dibujaban como un bloque suelto. Este script
corre dentro de gdb (`gdb -batch -x`), se detiene en el punto de corte y:

- toma de cada marco del programa sus variables con la dirección, el tipo y el valor reales;
- sigue los punteros hacia el heap y, en cada bloque, sus campos puntero (`sig`, `ant`, `izq`…) o
  sus elementos puntero (las filas de una matriz), hasta MAX_BLOQUES bloques: las listas
  circulares terminan porque cada dirección se visita una vez (QoL #58, #49);
- mide cada bloque con `malloc_usable_size` (glibc) o `_msize` (Windows): es el tamaño útil, que
  puede ser algo mayor que el pedido.

Recibe la configuración por un JSON (ruta en BISHOP_SNAPSHOT_CONFIG) y deja el resultado en otro,
con la forma de `SnapshotMemoria.to_dict()` más `punteros_salientes` en cada bloque.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

MAX_BLOQUES = 64
MAX_ELEMENTOS = 16

SCRIPT_GDB = r'''
import json, os, re
import gdb

CONFIG = json.load(open(os.environ["BISHOP_SNAPSHOT_CONFIG"], encoding="utf-8"))
MAX_BLOQUES, MAX_ELEMENTOS = CONFIG["max_bloques"], CONFIG["max_elementos"]


def nombre_de(ruta):
    return ruta.replace("\\", "/").rsplit("/", 1)[-1].lower()


NOMBRES = {nombre_de(f) for f in CONFIG["fuentes"]}
resultado = {"frames": [], "heap": [], "linea": 0, "error": None}

for orden in ("set pagination off", "set confirm off", "set debuginfod enabled off", "set print pretty off",
              "set breakpoint pending on"):
    try:
        gdb.execute(orden, to_string=True)
    except gdb.error:
        pass
# Tamaño pedido de cada reserva y bloques liberados: se detiene en malloc, calloc, realloc y free
# (los argumentos en los registros del ABI: System V en Linux, Microsoft x64 en Windows), y con
# `finish` se lee la dirección devuelta. Sin esto quedaría el tamaño útil del allocator, algo mayor
# que el pedido. Pasadas MAX_RESERVAS reservas se deja de seguir (el resto, con el tamaño útil).
asignados, liberados = {}, set()
ARGUMENTOS = ("$rcx", "$rdx") if os.name == "nt" else ("$rdi", "$rsi")
MAX_RESERVAS = 5000


def en_el_programa(marco):
    sal = marco.find_sal()
    return sal.symtab is not None and nombre_de(sal.symtab.filename) in NOMBRES


def funcion_de_reserva(marco):
    """La función del allocator donde se detuvo (glibc la nombra `__GI___libc_malloc`, etc.). None
    si la parada es otra: un `malloc` en línea dentro de otra función de la biblioteca (el cargador
    dinámico tiene el suyo) o el punto de corte."""
    nombre = marco.name() or ""
    return next((f for f in ("realloc", "calloc", "malloc", "free") if f in nombre), None)


def argumento(i):
    return int(gdb.parse_and_eval(ARGUMENTOS[i]))


vigilancia = []
if CONFIG.get("seguir_reservas", True):
    for funcion in ("malloc", "calloc", "realloc", "free"):
        try:
            vigilancia.append(gdb.Breakpoint(funcion, internal=True))
        except (gdb.error, RuntimeError):
            pass

gdb.execute("break " + CONFIG["punto"], to_string=True)
comilla = '"' if os.name == "nt" else "'"
redireccion = " > " + comilla + CONFIG["salida_programa"] + comilla + " 2>&1"
if CONFIG.get("entrada"):
    redireccion = " < " + comilla + CONFIG["entrada"] + comilla + redireccion
gdb.execute("run" + redireccion, to_string=True)

while True:
    try:
        marco = gdb.selected_frame()
    except gdb.error:
        break  # el programa terminó sin llegar al punto de corte
    if en_el_programa(marco):
        break  # el punto de corte (o una señal en el código del programa)
    funcion = funcion_de_reserva(marco)
    try:
        if funcion is None:
            pass  # una parada dentro de otra función de la biblioteca: seguir
        elif funcion == "free":
            direccion = argumento(0)
            if direccion in asignados:
                liberados.add(direccion)
        else:
            a, b = argumento(0), argumento(1)
            tamanio = {"malloc": a, "calloc": a * b, "realloc": b}[funcion]
            gdb.execute("finish", to_string=True)
            if not en_el_programa(gdb.selected_frame()) and funcion_de_reserva(gdb.selected_frame()) is not None:
                continue  # `finish` se detuvo en una reserva anidada: se atiende esa
            direccion = int(gdb.parse_and_eval("$rax"))
            if funcion == "realloc" and a and a != direccion:
                asignados.pop(a, None)
            if direccion:
                asignados[direccion] = tamanio
                liberados.discard(direccion)
    except (gdb.error, ValueError):
        pass
    if len(asignados) >= MAX_RESERVAS and vigilancia:
        for bp in vigilancia:
            bp.delete()
        vigilancia = []
    try:
        gdb.execute("continue", to_string=True)
    except gdb.error:
        break

rangos_heap = []
try:
    for linea in gdb.execute("info proc mappings", to_string=True).splitlines():
        if "[heap]" in linea:
            partes = linea.split()
            rangos_heap.append((int(partes[0], 16), int(partes[1], 16)))
except gdb.error:
    pass
direcciones_locales = set()


def es_heap(direccion):
    if direccion == 0 or direccion in direcciones_locales:
        return False
    if direccion in asignados:
        return True
    if rangos_heap:
        return any(a <= direccion < b for a, b in rangos_heap)
    return tamanio_util(direccion) is not None  # sin /proc (Windows): lo que el allocator reconoce


def tamanio_util(direccion):
    if direccion in asignados:
        return asignados[direccion]
    for funcion in ("malloc_usable_size", "_msize"):
        try:
            return int(gdb.parse_and_eval("(unsigned long) %s((void *) %d)" % (funcion, direccion)))
        except gdb.error:
            continue
    return None


def corto(valor, limite=40):
    try:
        texto = valor.format_string(max_elements=8, address=False, symbols=False)
    except (gdb.error, gdb.MemoryError, UnicodeDecodeError):
        texto = "‹ilegible›"
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


bloques, pendientes = {}, []


def encolar(direccion, tipo_apuntado):
    if direccion and direccion not in bloques and len(bloques) + len(pendientes) < MAX_BLOQUES and es_heap(direccion):
        pendientes.append((direccion, tipo_apuntado))


def recorrer_bloque(direccion, tipo):
    tipo = tipo.strip_typedefs()
    if direccion in liberados:
        # Un puntero colgante: el bloque ya se liberó y leerlo no tiene sentido.
        bloques[direccion] = {"direccion": hex(direccion), "tamanio_bytes": asignados.get(direccion, 0),
                              "tipo": str(tipo), "contenido": "‹liberado›", "esta_liberado": True,
                              "punteros_salientes": []}
        return
    elemento_bytes = max(1, tipo.sizeof) if tipo.code != gdb.TYPE_CODE_VOID else 1
    util = tamanio_util(direccion)
    cantidad = max(1, (util or elemento_bytes) // elemento_bytes)
    partes, salientes = [], []
    if tipo.code == gdb.TYPE_CODE_VOID:
        bloques[direccion] = {"direccion": hex(direccion), "tamanio_bytes": util or 0, "contenido": "void *",
                              "punteros_salientes": []}
        return
    base = gdb.Value(direccion).cast(tipo.pointer())
    for i in range(min(cantidad, MAX_ELEMENTOS)):
        try:
            elemento = (base + i).dereference()
            if tipo.code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
                campos = []
                for campo in tipo.fields():
                    if campo.name is None:
                        continue
                    v = elemento[campo.name]
                    tc = campo.type.strip_typedefs()
                    if tc.code == gdb.TYPE_CODE_PTR:
                        destino = int(v)
                        etiqueta = campo.name if cantidad == 1 else "[%d].%s" % (i, campo.name)
                        campos.append("%s=%s" % (campo.name, hex(destino) if destino else "NULL"))
                        if destino:
                            salientes.append({"campo": etiqueta, "destino": hex(destino)})
                            encolar(destino, tc.target())
                    else:
                        campos.append("%s=%s" % (campo.name, corto(v, 24)))
                partes.append("{" + ", ".join(campos) + "}")
            elif tipo.code == gdb.TYPE_CODE_PTR:
                destino = int(elemento)
                partes.append(hex(destino) if destino else "NULL")
                if destino:
                    salientes.append({"campo": "[%d]" % i, "destino": hex(destino)})
                    encolar(destino, tipo.target())
            else:
                partes.append(corto(elemento, 24))
        except (gdb.error, gdb.MemoryError):
            partes.append("‹ilegible›")
            break
    if cantidad > MAX_ELEMENTOS:
        partes.append("…")
    contenido = ("[ " + ", ".join(partes) + " ]") if cantidad > 1 else (partes[0] if partes else "")
    bloques[direccion] = {"direccion": hex(direccion), "tamanio_bytes": util or tipo.sizeof,
                          "tipo": str(tipo), "contenido": contenido, "punteros_salientes": salientes}


try:
    marco = gdb.selected_frame()
    resultado["linea"] = marco.find_sal().line
except gdb.error:
    resultado["error"] = "el programa terminó antes de llegar a " + CONFIG["punto"]
    marco = None

marcos = []
while marco is not None and len(marcos) < 20:
    sal = marco.find_sal()
    if sal.symtab is not None and nombre_de(sal.symtab.filename) in NOMBRES:
        marcos.append(marco)
    marco = marco.older()

punteros = []
for marco in marcos:
    variables, vistos = [], set()
    try:
        bloque = marco.block()
    except RuntimeError:
        bloque = None
    linea = marco.find_sal().line
    while bloque is not None:
        for simbolo in bloque:
            if not (simbolo.is_variable or simbolo.is_argument) or simbolo.name in vistos:
                continue
            if not simbolo.is_argument and simbolo.line > linea:
                continue
            vistos.add(simbolo.name)
            try:
                valor = simbolo.value(marco)
                tipo = valor.type.strip_typedefs()
                direccion = int(valor.address) if valor.address is not None else 0
                direcciones_locales.add(direccion)
                datos = {"nombre": simbolo.name, "tipo": str(simbolo.type), "direccion": hex(direccion),
                         "tamanio_bytes": tipo.sizeof}
                if tipo.code == gdb.TYPE_CODE_PTR:
                    destino = int(valor)
                    datos.update(valor=hex(destino) if destino else "NULL", es_puntero=True,
                                 direccion_apuntada=hex(destino) if destino else None)
                    if destino:
                        punteros.append((destino, tipo.target()))
                else:
                    datos.update(valor=corto(valor, 60), es_puntero=False)
                variables.append(datos)
            except (gdb.error, gdb.MemoryError) as exc:
                variables.append({"nombre": simbolo.name, "tipo": str(simbolo.type), "direccion": "",
                                  "valor": "‹" + str(exc) + "›", "es_puntero": False})
        if bloque.function is not None:
            break
        bloque = bloque.superblock
    try:
        base = hex(int(marco.read_register("rbp")))
        tope = hex(int(marco.read_register("rsp")))
    except (gdb.error, ValueError):
        base = tope = ""
    resultado["frames"].append({"funcion": marco.name(), "direccion_base": base, "direccion_tope": tope,
                                "linea_actual": marco.find_sal().line, "variables": variables})

for destino, tipo in punteros:
    encolar(destino, tipo)
while pendientes:
    direccion, tipo = pendientes.pop(0)
    if direccion not in bloques:
        recorrer_bloque(direccion, tipo)
resultado["heap"] = list(bloques.values())

try:
    gdb.execute("kill", to_string=True)
except gdb.error:
    pass
json.dump(resultado, open(CONFIG["resultado"], "w", encoding="utf-8"), ensure_ascii=False)
'''


class ErrorDeSnapshot(Exception):
    """No se pudo tomar el snapshot con la API Python de gdb (sin gdb, sin Python en gdb, no compila)."""


def capturar_con_python_gdb(fuente: Path, punto_corte: str, entrada: Optional[Path] = None,
                            timeout: float = 30.0) -> Dict[str, Any]:
    """El snapshot en el punto de corte, como diccionario (ver `snapshot_desde_dict`)."""
    from bishop.core.tracer import compilar_con_simbolos

    gdb = shutil.which("gdb")
    if not gdb:
        raise ErrorDeSnapshot("no se encontró gdb")
    with tempfile.TemporaryDirectory(prefix="bishop-snapshot-") as tmp:
        directorio = Path(tmp)
        ok, binario, error = compilar_con_simbolos(fuente, directorio)
        if not ok or binario is None:
            raise ErrorDeSnapshot(f"{fuente.name} no compila:\n{error.strip()}")
        configuracion = {
            "fuentes": [os.path.realpath(fuente)],
            "punto": punto_corte,
            "entrada": str(entrada.resolve()) if entrada else None,
            "salida_programa": str(directorio / "salida.txt"),
            "resultado": str(directorio / "snapshot.json"),
            "max_bloques": MAX_BLOQUES,
            "max_elementos": MAX_ELEMENTOS,
        }
        (directorio / "config.json").write_text(json.dumps(configuracion), encoding="utf-8")
        (directorio / "snapshot.py").write_text(SCRIPT_GDB, encoding="utf-8")
        entorno = {**os.environ, "BISHOP_SNAPSHOT_CONFIG": str(directorio / "config.json")}
        try:
            res = subprocess.run([gdb, "-nx", "-batch", "-x", str(directorio / "snapshot.py"), str(binario)],
                                 capture_output=True, text=True, timeout=timeout, env=entorno)
        except subprocess.TimeoutExpired:
            raise ErrorDeSnapshot(f"gdb superó {timeout:g} s") from None
        archivo = directorio / "snapshot.json"
        if not archivo.is_file():
            raise ErrorDeSnapshot("gdb no pudo tomar el snapshot:\n" + (res.stderr or res.stdout).strip()[-1500:])
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos.get("error"):
        raise ErrorDeSnapshot(datos["error"])
    return datos
