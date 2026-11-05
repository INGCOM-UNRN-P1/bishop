"""Motor de trazado e inspección de memoria en BISHOP."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from bishop.core.models import BloqueHeap, SnapshotMemoria, StackFrameMemoria, VariableMemoria


def _compilar_con_daedalus(fuente_c: Path, out_bin: Path) -> Optional[Tuple[bool, Optional[Path], str]]:
    try:
        from daedalus.core.compiler import compilar_archivos
    except ImportError:
        return None  # sin el extra `ecosistema` se usa el camino propio
    res = compilar_archivos([fuente_c], binario_salida=out_bin, flags_adicionales=["-g", "-O0"])
    return res.exito, (out_bin if res.exito else None), res.stderr_crudo


def compilar_con_simbolos(fuente_c: Path, out_dir: Path) -> Tuple[bool, Optional[Path], str]:
    """Compila el código fuente con símbolos de depuración (-g -O0) delegando en DAEDALUS."""
    # En Windows gcc agrega .exe al binario: se usa esa ruta (N-ECO-10).
    binario = out_dir / (fuente_c.stem + (".exe" if os.name == "nt" else ""))
    daed_res = _compilar_con_daedalus(fuente_c, binario)
    if daed_res is not None:
        return daed_res

    gcc = shutil.which("gcc") or "gcc"
    cmd = [gcc, "-g", "-O0", "-std=c11", str(fuente_c.resolve()), "-o", str(binario.resolve()), "-lm"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return False, None, res.stderr
    return True, binario, ""


def _detectar_punto_corte_optimo(fuente_c: Path) -> str:
    """Detecta la mejor línea o punto de corte para pausar tras asignaciones dinámicas o al final de main."""
    try:
        contenido = fuente_c.read_text(encoding="utf-8")
    except Exception:
        return "main"

    lineas = contenido.splitlines()
    ultima_asignacion = None
    linea_return_main = None
    en_main = False

    for idx, linea in enumerate(lineas, 1):
        l_strip = linea.strip()
        if re.search(r"\b(int|void)\s+main\s*\(", l_strip):
            en_main = True
        if re.search(r"\b(malloc|calloc|realloc)\s*\(", l_strip):
            ultima_asignacion = idx
        if en_main and re.search(r"\breturn\b", l_strip):
            linea_return_main = idx

    if ultima_asignacion:
        linea_target = min(len(lineas), ultima_asignacion + 1)
        return f"{fuente_c.name}:{linea_target}"
    if linea_return_main:
        return f"{fuente_c.name}:{linea_return_main}"
    return "main"


def es_archivo_binario(ruta: Path) -> bool:
    """Comprueba si un archivo es un ejecutable/binario en lugar de código fuente C."""
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(1024)
            # Detección de ejecutables ELF, Mach-O, PE/COFF o presencia de bytes nulos
            if cabecera.startswith((b"\x7fELF", b"\xca\xfe\xba\xbe", b"\xfe\xed\xfa", b"MZ")):
                return True
            return b"\x00" in cabecera
    except Exception:
        return False


def capturar_snapshot_gdb(
    fuente_c: Path,
    punto_corte: Optional[str] = None,
    linea_corte: Optional[int] = None,
) -> SnapshotMemoria:
    """Captura un snapshot exacto de memoria ejecutando el binario bajo GDB."""
    fuente_c = Path(fuente_c)
    if not fuente_c.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {fuente_c}")

    if es_archivo_binario(fuente_c):
        raise ValueError(
            f"El archivo '{fuente_c.name}' es un binario compilado. "
            f"BISHOP espera un archivo de código fuente C (ej: '{fuente_c.stem}.c') para compilarlo con símbolos de depuración e inspeccionar su memoria."
        )

    from bishop.core.diagrama import snapshot_desde_dict
    from bishop.core.snapshot_gdb import ErrorDeSnapshot, capturar_con_python_gdb

    bp = punto_corte or (f"{fuente_c.name}:{linea_corte}" if linea_corte else _detectar_punto_corte_optimo(fuente_c))
    try:
        return snapshot_desde_dict(capturar_con_python_gdb(fuente_c, bp), str(fuente_c))
    except (ErrorDeSnapshot, OSError, ValueError, KeyError) as exc:
        # El detalle (la salida de gcc o de gdb, en inglés) no es para el estudiante.
        motivo = (str(exc).splitlines() or ["No se pudo ejecutar el programa."])[0]
        return _generar_snapshot_estatico(fuente_c, linea_corte or 1, motivo)


def _generar_snapshot_estatico(fuente: Path, linea: int, motivo: str = "") -> SnapshotMemoria:
    """Un dibujo aproximado a partir de las variables declaradas en el fuente, cuando no se pudo
    ejecutar: las direcciones son ilustrativas y los valores, los del código. `origen` y `motivo`
    lo dejan dicho, para que nadie lo lea como memoria real."""
    contenido = fuente.read_text(encoding="utf-8") if fuente.is_file() else ""
    variables: List[VariableMemoria] = []

    # Extraer variables simples
    re_vars = re.compile(r"\b(int|char|double|float|size_t)\s*(\*?)\s*([a-zA-Z0-9_]+)\s*(?:=\s*([^;]+))?;")
    base_addr = 0x7fffffffe000

    for idx, m in enumerate(re_vars.finditer(contenido), 1):
        tipo_base = m.group(1)
        es_ptr = bool(m.group(2))
        nombre = m.group(3)
        val = m.group(4).strip() if m.group(4) else "0"

        tipo_str = f"{tipo_base}*" if es_ptr else tipo_base
        var_addr = hex(base_addr - idx * 8)
        dest_addr = "0x5555555592a0" if es_ptr and "malloc" in val else None

        variables.append(VariableMemoria(
            nombre=nombre,
            tipo=tipo_str,
            direccion=var_addr,
            valor=val,
            es_puntero=es_ptr,
            direccion_apuntada=dest_addr,
        ))

    heap_bloques = []
    for v in variables:
        if v.es_puntero and v.direccion_apuntada:
            heap_bloques.append(BloqueHeap(
                direccion=v.direccion_apuntada,
                tamanio_bytes=64,
                punteros_referenciantes=[v.nombre],
                contenido="‹sin ejecutar›",
            ))

    frame = StackFrameMemoria(
        funcion="main",
        direccion_base=hex(base_addr),
        direccion_tope=hex(base_addr - len(variables) * 8),
        linea_actual=linea,
        variables=variables,
    )

    return SnapshotMemoria(
        archivo=fuente,
        linea=linea,
        frames=[frame],
        heap=heap_bloques,
        total_bytes_heap_activos=sum(b.tamanio_bytes for b in heap_bloques),
        origen="estatico",
        motivo=motivo,
    )
