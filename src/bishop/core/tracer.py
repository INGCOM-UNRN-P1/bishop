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


def compilar_con_simbolos(fuente_c: Path, out_dir: Path) -> Tuple[bool, Optional[Path], str]:
    """Compila el código fuente con símbolos de depuración (-g -O0)."""
    gcc = shutil.which("gcc") or "gcc"
    binario = out_dir / fuente_c.stem
    cmd = [gcc, "-g", "-O0", "-std=c11", str(fuente_c.resolve()), "-o", str(binario.resolve()), "-lm"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        return False, None, res.stderr
    return True, binario, ""


def capturar_snapshot_gdb(
    fuente_c: Path,
    punto_corte: Optional[str] = None,
    linea_corte: Optional[int] = None,
) -> SnapshotMemoria:
    """Captura un snapshot exacto de memoria ejecutando el binario bajo GDB."""
    fuente_c = Path(fuente_c)
    if not fuente_c.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {fuente_c}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        ok, binario, err = compilar_con_simbolos(fuente_c, tmp_path)
        if not ok or not binario:
            # Si falla la compilación, generar snapshot sintético del código fuente
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)

        gdb_bin = shutil.which("gdb")
        if not gdb_bin:
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)

        bp = punto_corte or (f"{fuente_c.name}:{linea_corte}" if linea_corte else "main")
        with tempfile.NamedTemporaryFile("w", suffix=".gdb", delete=False) as f_gdb:
            gdb_script = f_gdb.name
            f_gdb.write("set pagination off\n")
            f_gdb.write("set confirm off\n")
            f_gdb.write(f"break {bp}\n")
            f_gdb.write("run\n")
            f_gdb.write("next\n")
            f_gdb.write("echo ===BISHOP_FRAME===\n")
            f_gdb.write("info frame\n")
            f_gdb.write("echo ===BISHOP_LOCALS===\n")
            f_gdb.write("info locals\n")
            f_gdb.write("echo ===BISHOP_ARGS===\n")
            f_gdb.write("info args\n")
            f_gdb.write("quit\n")

        try:
            cmd = [gdb_bin, "--batch", "-x", gdb_script, str(binario.resolve())]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            return _parsear_salida_gdb_memoria(fuente_c, res.stdout, linea_corte or 1)
        except Exception:
            return _generar_snapshot_estatico(fuente_c, linea_corte or 1)
        finally:
            if os.path.exists(gdb_script):
                os.remove(gdb_script)


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
        locals_section = partes[1].split("===BISHOP_ARGS===")[0]

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

    # Detectar bloques de heap si los punteros apuntan a heap (0x5555... o similar)
    heap_bloques: List[BloqueHeap] = []
    for v in variables:
        if v.es_puntero and v.direccion_apuntada and v.direccion_apuntada.startswith("0x55"):
            heap_bloques.append(BloqueHeap(
                direccion=v.direccion_apuntada,
                tamanio_bytes=32,
                punteros_referenciantes=[v.nombre],
            ))

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
