"""bishop reconoce los bloques del heap sin /proc, como en Windows (N-ECO-10).

Para saber si un puntero apunta al heap se usaban los mappings de /proc (`info proc mappings`) o,
sin ellos, una heurística por prefijo de dirección (0x55…, 0x56…) que solo vale para Linux x86_64:
en Windows la lista de bloques salía vacía. Ahora, sin mappings, cuenta como heap lo que no está en
las secciones de `info files` ni cerca del frame actual.
"""

from pathlib import Path

from bishop.core.tracer import _parsear_salida_gdb_memoria

SALIDA_WINDOWS = """Breakpoint 1, main () at C:/tp/mem.c:5
5\t    p[0] = 42;
===BISHOP_LOCALS===
p = 0x1d4f2c41450
q = 0x140009010 <contador>
r = 0x5ffe2c
x = 5
===BISHOP_MAPPINGS===
Not supported on this target.
===BISHOP_FRAME===
Stack level 0, frame at 0x5ffe50:
 rip = 0x140001460 in main (C:/tp/mem.c:5); saved rip = 0x1400012ee
===BISHOP_ARGS===
No arguments.
===BISHOP_FILES===
Symbols from "C:\\\\tp\\\\mem.exe".
Local exec file:
\t`C:\\\\tp\\\\mem.exe', file type pei-x86-64.
\tEntry point: 0x1400013f0
\t0x0000000140001000 - 0x0000000140008ab8 is .text
\t0x0000000140009000 - 0x0000000140009100 is .data
\t0x00007ffd1c3b1000 - 0x00007ffd1c4a1000 is .text in C:\\\\Windows\\\\System32\\\\ucrtbase.dll
"""


def test_sin_mappings_el_heap_se_reconoce_por_exclusion():
    snapshot = _parsear_salida_gdb_memoria(Path("mem.c"), SALIDA_WINDOWS, 5)
    # q apunta a datos estáticos (.data) y r a la pila: solo p es un bloque del heap.
    assert [b.punteros_referenciantes for b in snapshot.heap] == [["p"]]
