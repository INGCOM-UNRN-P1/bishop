"""Motor de trazado e inspección de memoria en BISHOP."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
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

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ok, binario, err = compilar_con_simbolos(fuente_c, tmp_path)
        if not ok or not binario:
            # Si falla la compilación, generar snapshot sintético del código fuente
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)

        gdb_bin = shutil.which("gdb")
        if not gdb_bin:
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)

        bp = punto_corte or (f"{fuente_c.name}:{linea_corte}" if linea_corte else _detectar_punto_corte_optimo(fuente_c))
        # Primero con la API Python de gdb: direcciones y tipos reales y el heap recorrido por sus
        # punteros. Si gdb no tiene Python (o falla), queda el parseo de texto de abajo.
        try:
            from bishop.core.diagrama import snapshot_desde_dict
            from bishop.core.snapshot_gdb import ErrorDeSnapshot, capturar_con_python_gdb

            return snapshot_desde_dict(capturar_con_python_gdb(fuente_c, bp), str(fuente_c))
        except (ErrorDeSnapshot, OSError, ValueError, KeyError):
            pass
        # Cada comando va en su propio -ex: gdb sigue con el próximo aunque uno falle. Con un script
        # (-x) el primer error corta el resto, y en Windows `info proc mappings` siempre falla: sin
        # `info frame`, `info files` ni los límites de la pila, ningún puntero se reconocía como heap.
        comandos = [
            "set pagination off",
            "set confirm off",
            f"break {bp}",
            "run",
            "echo ===BISHOP_LOCALS===\\n",
            "info locals",
            "echo ===BISHOP_MAPPINGS===\\n",
            "info proc mappings",
            "echo ===BISHOP_FRAME===\\n",
            "info frame",
            "echo ===BISHOP_ARGS===\\n",
            "info args",
            # Secciones del ejecutable y de las bibliotecas: sin /proc (Windows) es lo que permite
            # distinguir un puntero al heap de uno a datos estáticos.
            "echo ===BISHOP_FILES===\\n",
            "info files",
            # Límites de la pila en Windows (bloque de información del hilo, $_tlb); en Linux no existe.
            "echo ===BISHOP_TLB===\\n",
            "print/x $_tlb->current_top_of_stack",
            "print/x $_tlb->current_bottom_of_stack",
            "kill",
        ]
        cmd = [gdb_bin, "-nx", "--batch"]
        for comando in comandos:
            cmd += ["-ex", comando]
        try:
            # En Windows gdb tarda más en arrancar (carga los símbolos de las DLL).
            res = subprocess.run(cmd + [str(binario.resolve())], capture_output=True, text=True, timeout=20)
            return _parsear_salida_gdb_memoria(fuente_c, res.stdout, linea_corte or 1)
        except Exception:
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)


def _parsear_salida_gdb_memoria(fuente: Path, gdb_output: str, linea: int) -> SnapshotMemoria:
    """Parsea variables locales y frame desde la salida de GDB."""
    variables: List[VariableMemoria] = []
    func_name = "main"

    # Extraer función
    m_fn = re.search(r"in\s+([a-zA-Z0-9_]+)\s*\(", gdb_output)
    if m_fn:
        func_name = m_fn.group(1)

    # Extraer locals
    locals_section = ""
    if "===BISHOP_LOCALS===" in gdb_output:
        partes = gdb_output.split("===BISHOP_LOCALS===")
        locals_section = partes[1].split("===BISHOP_MAPPINGS===")[0]

    # Extraer mappings para rangos reales de [heap] y [stack]
    heap_ranges: List[Tuple[int, int]] = []
    stack_ranges: List[Tuple[int, int]] = []
    if "===BISHOP_MAPPINGS===" in gdb_output:
        m_sec = gdb_output.split("===BISHOP_MAPPINGS===")[1].split("===BISHOP_FRAME===")[0]
        for l_map in m_sec.splitlines():
            partes_map = l_map.split()
            if len(partes_map) >= 2:
                try:
                    s_addr = int(partes_map[0], 16)
                    e_addr = int(partes_map[1], 16)
                    if "[heap]" in l_map:
                        heap_ranges.append((s_addr, e_addr))
                    elif "[stack]" in l_map:
                        stack_ranges.append((s_addr, e_addr))
                except (ValueError, TypeError):
                    continue

    # Dirección del frame actual y secciones estáticas (`info files`): con ellas se clasifica un
    # puntero cuando no hay mappings de /proc, como en Windows.
    frame_addr = None
    static_ranges: List[Tuple[int, int]] = []
    if "===BISHOP_FRAME===" in gdb_output:
        sec_frame = gdb_output.split("===BISHOP_FRAME===")[1].split("===BISHOP_ARGS===")[0]
        m_frame = re.search(r"frame at (0x[0-9a-fA-F]+)", sec_frame)
        if m_frame:
            frame_addr = int(m_frame.group(1), 16)
    if "===BISHOP_FILES===" in gdb_output:
        sec_files = gdb_output.split("===BISHOP_FILES===")[1].split("===BISHOP_TLB===")[0]
        for m_rango in re.finditer(r"(0x[0-9a-fA-F]+)\s*-\s*(0x[0-9a-fA-F]+)\s+is\s+\S+", sec_files):
            static_ranges.append((int(m_rango.group(1), 16), int(m_rango.group(2), 16)))
    # En Windows, la pila del hilo: entre current_bottom_of_stack y current_top_of_stack del TIB. Ahí
    # la pila y el heap pueden quedar a menos de 1 MiB, así que la distancia al frame no alcanza.
    if "===BISHOP_TLB===" in gdb_output:
        limites = [int(v, 16) for v in re.findall(r"^\$\d+ = (0x[0-9a-fA-F]+)", gdb_output.split("===BISHOP_TLB===")[1],
                                                   re.MULTILINE)]
        if len(limites) == 2 and min(limites) < max(limites):
            stack_ranges.append((min(limites), max(limites)))

    base_addr = 0x7fffffffe000
    for idx, l in enumerate(locals_section.splitlines(), 1):
        l_str = l.strip()
        if "=" in l_str and not l_str.startswith("#"):
            k, v = l_str.split("=", 1)
            var_name = k.strip()
            var_val = v.strip()

            es_ptr = "0x" in var_val or var_val in ("(nil)", "NULL")
            var_addr = hex(base_addr - idx * 8)
            ptr_dest = var_val if es_ptr and var_val.startswith("0x") else None

            variables.append(VariableMemoria(
                nombre=var_name,
                tipo="int*" if es_ptr else "int",
                direccion=var_addr,
                valor=var_val,
                es_puntero=es_ptr,
                direccion_apuntada=ptr_dest,
            ))

    frame = StackFrameMemoria(
        funcion=func_name,
        direccion_base=hex(base_addr),
        direccion_tope=hex(base_addr - 64),
        linea_actual=linea,
        variables=variables,
    )

    # Detectar bloques de heap:
    # 1. Si cae dentro del rango [heap] de /proc/mappings
    # 2. O si empieza con 0x55, 0x56, 0x40 (direcciones típicas de heap en Linux x86_64) y no es dirección de stack
    def _es_direccion_heap(addr_hex: str) -> bool:
        try:
            val = int(addr_hex, 16)
        except (ValueError, TypeError):
            return False
        if heap_ranges:
            return any(s <= val < e for s, e in heap_ranges)
        # Fallback heurístico: no en stack ni nulo
        if stack_ranges and any(s <= val < e for s, e in stack_ranges):
            return False
        if stack_ranges and static_ranges:
            # Sin /proc pero con los límites de la pila (Windows): heap es lo que no está en la pila
            # ni en las secciones del ejecutable o de las bibliotecas.
            return val > 0x10000 and not any(s <= val < e for s, e in static_ranges)
        if frame_addr is not None and static_ranges:
            # Sin /proc (Windows): heap es lo que no está en las secciones del ejecutable o de las
            # bibliotecas ni en la pila (a menos de 1 MiB del frame actual).
            if any(s <= val < e for s, e in static_ranges):
                return False
            return val > 0x10000 and abs(val - frame_addr) >= 1 << 20
        return addr_hex.startswith(("0x55", "0x56", "0x40", "0x60")) and val > 0x10000

    heap_bloques: List[BloqueHeap] = []
    bloques_vistos = set()
    for var in variables:
        if var.es_puntero and var.direccion_apuntada and _es_direccion_heap(var.direccion_apuntada):
            addr_norm = var.direccion_apuntada.lower()
            if addr_norm not in bloques_vistos:
                bloques_vistos.add(addr_norm)
                heap_bloques.append(BloqueHeap(
                    direccion=var.direccion_apuntada,
                    tamanio_bytes=32,
                    punteros_referenciantes=[var.nombre],
                ))
            else:
                # Agregar puntero referenciante adicional
                for b in heap_bloques:
                    if b.direccion.lower() == addr_norm and var.nombre not in b.punteros_referenciantes:
                        b.punteros_referenciantes.append(var.nombre)

    return SnapshotMemoria(
        archivo=fuente,
        linea=linea,
        frames=[frame],
        heap=heap_bloques,
        total_bytes_heap_activos=sum(b.tamanio_bytes for b in heap_bloques),
    )


def _generar_snapshot_estatico(fuente: Path, linea: int) -> SnapshotMemoria:
    """Genera un snapshot estático analizando las variables declaradas en el archivo C."""
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
                contenido="[ 10, 20, 30, ... ]",
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
    )
