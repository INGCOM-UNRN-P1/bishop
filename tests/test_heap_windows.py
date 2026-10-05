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


def test_con_los_limites_de_la_pila_del_tib():
    """En Windows la pila y el heap pueden quedar a menos de 1 MiB: con los límites de $_tlb, un
    puntero cercano al frame pero fuera de la pila es heap (y uno dentro de la pila, no)."""
    from bishop.core.tracer import _parsear_salida_gdb_memoria

    salida = (
        "===BISHOP_LOCALS===\np = 0x7d1450\nq = 0x5ffe20\n"
        "===BISHOP_MAPPINGS===\n"
        "===BISHOP_FRAME===\nStack level 0, frame at 0x5ffe60:\n"
        "===BISHOP_ARGS===\nNo arguments.\n"
        "===BISHOP_FILES===\n\t0x0000000140001000 - 0x0000000140002000 is .text\n"
        "===BISHOP_TLB===\n$1 = 0x600000\n$2 = 0x5fd000\n"
    )
    snap = _parsear_salida_gdb_memoria(Path("mem.c"), salida, 4)
    assert [b.direccion for b in snap.heap] == ["0x7d1450"]


def test_un_comando_que_falla_no_corta_los_siguientes(monkeypatch, tmp_path):
    """Con un script (`gdb -x`) el primer error corta el resto, y en Windows `info proc mappings`
    siempre falla: ni `info files` ni los límites de la pila llegaban a la salida. Cada comando va en
    su propio -ex, que gdb ejecuta aunque el anterior haya fallado."""
    import subprocess

    from bishop.core import tracer

    fuente = tmp_path / "mem.c"
    fuente.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    monkeypatch.setattr(tracer, "compilar_con_simbolos", lambda f, d: (True, d / "mem", ""))
    monkeypatch.setattr(tracer.shutil, "which", lambda nombre: "/usr/bin/gdb")
    llamadas = []

    def run(cmd, **kwargs):
        llamadas.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=SALIDA_WINDOWS, stderr="")

    monkeypatch.setattr(tracer.subprocess, "run", run)
    # Este test es del camino de texto, el respaldo cuando gdb no tiene Python.
    from bishop.core import snapshot_gdb

    def sin_python(*args, **kwargs):
        raise snapshot_gdb.ErrorDeSnapshot("gdb sin Python")

    monkeypatch.setattr(snapshot_gdb, "capturar_con_python_gdb", sin_python)
    snapshot = tracer.capturar_snapshot_gdb(fuente)

    (cmd,) = llamadas
    assert "-x" not in cmd
    comandos = [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "-ex"]
    assert comandos.index("info proc mappings") < comandos.index("info files") < comandos.index(
        "print/x $_tlb->current_top_of_stack")
    assert [b.direccion for b in snapshot.heap] == ["0x1d4f2c41450"]
