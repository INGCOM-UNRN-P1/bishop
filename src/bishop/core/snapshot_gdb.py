"""Snapshot de memoria con la API Python de gdb (revisión 07: `heap` y `ascii` sin parsear texto).

Es el único camino de `tracer.capturar_snapshot_gdb` a la memoria real. Este script corre dentro de gdb (`gdb -batch -x`), se detiene en el punto de corte y:

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

# El recorrido de la memoria está en `bishop/gdb_memoria.py` (el mismo que cargan los depuradores en
# vivo); en lote se le agrega esto: correr hasta el punto de corte, tomar la foto y terminar.
CONDUCTOR_GDB = r'''
CONFIG = json.load(open(os.environ["BISHOP_SNAPSHOT_CONFIG"], encoding="utf-8"))
for orden in ("set pagination off", "set confirm off", "set debuginfod enabled off", "set print pretty off",
              "set breakpoint pending on"):
    try:
        gdb.execute(orden, to_string=True)
    except gdb.error:
        pass
programa = Programa(nombres=CONFIG["fuentes"])
seguimiento = Seguimiento(programa)
if CONFIG.get("seguir_reservas", True):
    seguimiento.activar()
gdb.execute("break " + CONFIG["punto"], to_string=True)
comilla = '"' if os.name == "nt" else "'"
redireccion = " > " + comilla + CONFIG["salida_programa"] + comilla + " 2>&1"
if CONFIG.get("entrada"):
    redireccion = " < " + comilla + CONFIG["entrada"] + comilla + redireccion
gdb.execute("run" + redireccion, to_string=True)
try:
    gdb.newest_frame()
    resultado = tomar_memoria(programa, seguimiento, CONFIG["max_bloques"], CONFIG["max_elementos"])
except gdb.error:
    resultado = {"frames": [], "heap": [], "linea": 0, "error": "el programa terminó antes de llegar a " + CONFIG["punto"]}
try:
    gdb.execute("kill", to_string=True)
except gdb.error:
    pass
json.dump(resultado, open(CONFIG["resultado"], "w", encoding="utf-8"), ensure_ascii=False)
'''


def script_gdb() -> str:
    """El script de `gdb -batch -x`: el módulo de memoria más el conductor."""
    return (Path(__file__).parent.parent / "gdb_memoria.py").read_text(encoding="utf-8") + CONDUCTOR_GDB


class ErrorDeSnapshot(Exception):
    """No se pudo tomar el snapshot con la API Python de gdb (sin gdb, sin Python en gdb, no compila)."""


def capturar_con_python_gdb(fuente: Path, punto_corte: str, entrada: Optional[Path] = None,
                            timeout: float = 30.0) -> Dict[str, Any]:
    """El snapshot en el punto de corte, como diccionario (ver `snapshot_desde_dict`)."""
    from bishop.core.tracer import compilar_con_simbolos

    gdb = shutil.which("gdb")
    if not gdb:
        raise ErrorDeSnapshot("Falta gdb: instalalo para ver la memoria real (ver `bishop doctor`).")
    with tempfile.TemporaryDirectory(prefix="bishop-snapshot-") as tmp:
        directorio = Path(tmp)
        ok, binario, error = compilar_con_simbolos(fuente, directorio)
        if not ok or binario is None:
            raise ErrorDeSnapshot(f"{fuente.name} todavía no compila: corregilo con `daedalus` para ver la memoria real.\n"
                                 f"{error.strip()}")
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
        (directorio / "snapshot.py").write_text(script_gdb(), encoding="utf-8")
        entorno = {**os.environ, "BISHOP_SNAPSHOT_CONFIG": str(directorio / "config.json")}
        try:
            res = subprocess.run([gdb, "-nx", "-batch", "-iex", "set auto-load off", "-x", str(directorio / "snapshot.py"),
                                  str(binario)],
                                 capture_output=True, text=True, timeout=timeout, env=entorno)
        except subprocess.TimeoutExpired:
            raise ErrorDeSnapshot(f"El programa no llegó al punto de corte en {timeout:g} s (¿lazo infinito?).") from None
        archivo = directorio / "snapshot.json"
        if not archivo.is_file():
            raise ErrorDeSnapshot("gdb no pudo leer la memoria: puede que no tenga soporte de Python "
                                  "(ver `bishop doctor`).\n" + (res.stderr or res.stdout).strip()[-1500:])
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    if datos.get("error"):
        raise ErrorDeSnapshot(datos["error"])
    return datos
