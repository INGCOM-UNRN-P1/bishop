"""La memoria del programa desde adentro de gdb, con su API Python.

Lo usan `bishop snapshot` y compañía (en lote, ver `core/snapshot_gdb.py`) y los depuradores que
lo cargan en su propia sesión para mostrar la memoria en cada paso (jonesy, Ola 42). La ruta de
este archivo la da `bishop gdb-script`; se carga con `source <ruta>` y define dos comandos:

- `bishop-seguir [RAIZ]`: sigue malloc, calloc, realloc y free sin detener el programa (los
  breakpoints internos devuelven False en `stop`). Cada reserva hecha desde el código de RAIZ (el
  directorio actual si no se indica) queda con un número (#1, #2…), su tamaño pedido y la línea
  que la pidió; cada free, con la suya.
- `bishop-memoria ARCHIVO`: escribe en ARCHIVO, en JSON, la memoria de la parada actual: cada
  marco del programa con sus variables (dirección, tipo y valor reales), los bloques del heap a
  los que se llega siguiendo punteros (con sus campos y sus punteros salientes), los bloques vivos
  a los que ya no llega ninguno (fugas) y lo que pasó con el heap desde la foto anterior.

La forma es la de `SnapshotMemoria.to_dict()` más `punteros_salientes`, `id`, `sitio` y `campos`
en cada bloque y `eventos` en la raíz. Sólo usa la biblioteca estándar y el módulo gdb: corre con
el Python de gdb, no con el de bishop.
"""

import json
import os

import gdb

MAX_BLOQUES = 64
MAX_ELEMENTOS = 16
# Pasadas estas reservas se dejan de numerar (las demás se ven con el tamaño útil del allocator).
MAX_RESERVAS = 5000
# Los argumentos y el valor devuelto, en los registros del ABI: System V en Linux, Microsoft x64
# en Windows.
ARGUMENTOS = ("$rcx", "$rdx") if os.name == "nt" else ("$rdi", "$rsi")
RETORNO = "$rax"
# Funciones de la biblioteca que reservan para el programa: su malloc cuenta como del programa.
RESERVAN_PARA_EL_PROGRAMA = ("strdup", "strndup")
FUNCIONES = ("malloc", "calloc", "realloc", "free")


def nombre_de(ruta):
    return ruta.replace("\\", "/").rsplit("/", 1)[-1].lower()


class Programa:
    """Qué código es del programa y no de la biblioteca: por nombre de archivo (en lote, los
    fuentes que se compilaron) o por directorio (en vivo, la raíz del proyecto)."""

    def __init__(self, nombres=(), raiz=None):
        self.nombres = {nombre_de(n) for n in nombres}
        self.raiz = os.path.normcase(os.path.realpath(raiz)) if raiz else None

    def contiene(self, marco):
        try:
            symtab = marco.find_sal().symtab
        except (gdb.error, RuntimeError):
            return False
        if symtab is None:
            return False
        if self.raiz is not None:
            completo = os.path.normcase(os.path.realpath(symtab.fullname()))
            return completo.startswith(self.raiz + os.sep)
        return nombre_de(symtab.filename) in self.nombres

    def sitio(self, marco):
        """Archivo, línea y función del primer marco del programa desde `marco` hacia afuera."""
        while marco is not None:
            if self.contiene(marco):
                sal = marco.find_sal()
                return {"archivo": sal.symtab.fullname(), "linea": sal.line, "funcion": marco.name() or "?"}
            marco = marco.older()
        return None


def argumento(i):
    return int(gdb.parse_and_eval(ARGUMENTOS[i]))


class _Reserva(gdb.Breakpoint):
    """Breakpoint interno en malloc, calloc, realloc o free que anota y sigue de largo."""

    def __init__(self, seguimiento, funcion):
        super().__init__(funcion, internal=True)
        self.seguimiento = seguimiento
        self.funcion = funcion

    def stop(self):
        try:
            marco = gdb.newest_frame()
            # gdb informa dos veces la primera llamada a free, sin ejecutar nada en el medio (misma
            # pila, mismo argumento, misma dirección de retorno): la repetición se descarta. Entre
            # dos reservas en un ciclo siempre vuelve una (y `reservado` la olvida); un free doble
            # verdadero vuelve desde otra instrucción.
            parada = (self.funcion, int(gdb.parse_and_eval("$sp")), int(gdb.parse_and_eval("*(void **) $sp")),
                      argumento(0))
            if parada == self.seguimiento.ultima:
                return False
            self.seguimiento.ultima = parada
            # glibc la nombra `__GI___libc_malloc`; un `malloc` en línea dentro de otra función de
            # la biblioteca (el cargador dinámico tiene el suyo) no cuenta.
            if self.funcion not in (marco.name() or ""):
                return False
            llamador = marco.older()
            programa = self.seguimiento.programa
            if llamador is None:
                return False
            if not programa.contiene(llamador):
                # printf y compañía reservan sus búferes: no son del programa. strdup sí.
                nombre = llamador.name() or ""
                siguiente = llamador.older()
                if not (any(f in nombre for f in RESERVAN_PARA_EL_PROGRAMA)
                        and siguiente is not None and programa.contiene(siguiente)):
                    return False
            if self.funcion == "free":
                self.seguimiento.liberado(argumento(0), llamador)
            else:
                a, b = argumento(0), argumento(1)
                tamanio = {"malloc": a, "calloc": a * b, "realloc": b}[self.funcion]
                _Retorno(marco, self.seguimiento, self.funcion, tamanio, a if self.funcion == "realloc" else 0)
        except (gdb.error, RuntimeError, ValueError):
            pass
        return False


class _Retorno(gdb.FinishBreakpoint):
    """Al volver de la reserva: la dirección que devolvió."""

    def __init__(self, marco, seguimiento, funcion, tamanio, anterior):
        super().__init__(marco, internal=True)
        self.seguimiento = seguimiento
        self.funcion = funcion
        self.tamanio = tamanio
        self.anterior = anterior

    def stop(self):
        try:
            direccion = int(gdb.parse_and_eval(RETORNO))
            self.seguimiento.reservado(self.funcion, self.tamanio, direccion, self.anterior, gdb.newest_frame())
        except (gdb.error, RuntimeError, ValueError):
            pass
        return False

    def out_of_scope(self):
        pass  # un longjmp o el fin del programa: la reserva no volvió


class Seguimiento:
    """Las reservas y liberaciones del programa, y lo que pasó desde la última foto."""

    def __init__(self, programa):
        self.programa = programa
        self.asignados = {}  # dirección → {"id", "tamanio", "sitio"}
        self.liberados = {}  # dirección → lo mismo más "sitio_free"
        self.eventos = []
        self.siguiente = 1
        self.breakpoints = []
        self.ultima = None  # la última parada en el allocator (ver `_Reserva.stop`)

    def activar(self):
        # Antes de `run` la biblioteca no está cargada: calloc sin entrada en la PLT queda pendiente.
        try:
            gdb.execute("set breakpoint pending on", to_string=True)
        except gdb.error:
            pass
        for funcion in FUNCIONES:
            try:
                self.breakpoints.append(_Reserva(self, funcion))
            except (gdb.error, RuntimeError):
                pass

    @property
    def completo(self):
        return self.siguiente <= MAX_RESERVAS

    def _evento(self, **datos):
        if len(self.eventos) < 200:
            self.eventos.append(datos)

    def reservado(self, funcion, tamanio, direccion, anterior, marco):
        self.ultima = None
        sitio = self.programa.sitio(marco)
        if not direccion:
            self._evento(tipo=funcion, tamanio=tamanio, falla=True, sitio=sitio)
            return
        previo = self.asignados.pop(anterior, None) if anterior else None
        if previo is not None:
            # realloc: el mismo bloque, quizás en otro lugar.
            previo.update(tamanio=tamanio)
            self.asignados[direccion] = previo
            self.liberados.pop(direccion, None)
            self._evento(tipo="realloc", id=previo["id"], direccion=hex(direccion), tamanio=tamanio,
                         movido=direccion != anterior, sitio=sitio)
            return
        if not self.completo:
            return
        self.asignados[direccion] = {"id": self.siguiente, "tamanio": tamanio, "sitio": sitio}
        self.liberados.pop(direccion, None)
        self._evento(tipo=funcion, id=self.siguiente, direccion=hex(direccion), tamanio=tamanio, sitio=sitio)
        self.siguiente += 1

    def liberado(self, direccion, marco):
        sitio = self.programa.sitio(marco)
        if not direccion:
            self._evento(tipo="free", nulo=True, sitio=sitio)
        elif direccion in self.asignados:
            info = self.asignados.pop(direccion)
            info["sitio_free"] = sitio
            self.liberados[direccion] = info
            self._evento(tipo="free", id=info["id"], direccion=hex(direccion), sitio=sitio)
        elif direccion in self.liberados:
            self._evento(tipo="free", id=self.liberados[direccion]["id"], direccion=hex(direccion),
                         doble=True, sitio=sitio)
        elif self.completo:
            self._evento(tipo="free", direccion=hex(direccion), desconocido=True, sitio=sitio)

    def tomar_eventos(self):
        eventos, self.eventos = self.eventos, []
        return eventos


def _rangos_heap():
    """El heap según /proc, que el núcleo escribe siempre igual. En Windows no existe: ver `es_heap`."""
    rangos = []
    try:
        with open("/proc/%d/maps" % gdb.selected_inferior().pid, encoding="utf-8", errors="replace") as mapa:
            for linea in mapa:
                if linea.rstrip().endswith("[heap]"):
                    desde, hasta = linea.split()[0].split("-")
                    rangos.append((int(desde, 16), int(hasta, 16)))
    except OSError:
        pass
    return rangos


def _corto(valor, limite=40):
    try:
        texto = valor.format_string(max_elements=8, address=False, symbols=False)
    except (gdb.error, gdb.MemoryError, UnicodeDecodeError):
        texto = "‹ilegible›"
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def tomar_memoria(programa, seguimiento=None, max_bloques=MAX_BLOQUES, max_elementos=MAX_ELEMENTOS):
    """La memoria de la parada actual (ver el docstring del módulo). Lanza gdb.error si el programa
    no está corriendo."""
    asignados = seguimiento.asignados if seguimiento else {}
    liberados = seguimiento.liberados if seguimiento else {}
    rangos_heap = _rangos_heap()
    direcciones_locales = set()
    bloques, pendientes = {}, []

    def tamanio_util(direccion):
        if direccion in asignados:
            return asignados[direccion]["tamanio"]
        for funcion in ("malloc_usable_size", "_msize"):
            try:
                return int(gdb.parse_and_eval("(unsigned long) %s((void *) %d)" % (funcion, direccion)))
            except gdb.error:
                continue
        return None

    def es_heap(direccion):
        if direccion == 0 or direccion in direcciones_locales:
            return False
        if direccion in asignados or direccion in liberados:
            return True
        if rangos_heap:
            return any(a <= direccion < b for a, b in rangos_heap)
        return tamanio_util(direccion) is not None  # sin /proc (Windows): lo que el allocator reconoce

    def encolar(direccion, tipo_apuntado):
        if direccion and direccion not in bloques and len(bloques) + len(pendientes) < max_bloques and es_heap(direccion):
            pendientes.append((direccion, tipo_apuntado))

    def con_seguimiento(datos, direccion, info):
        if info is not None:
            datos["id"] = info["id"]
            if info.get("sitio"):
                datos["sitio"] = info["sitio"]
            if info.get("sitio_free"):
                datos["sitio_free"] = info["sitio_free"]
        return datos

    def recorrer_bloque(direccion, tipo):
        tipo = tipo.strip_typedefs()
        if direccion in liberados:
            # Un puntero colgante: el bloque ya se liberó y leerlo no tiene sentido.
            bloques[direccion] = con_seguimiento(
                {"direccion": hex(direccion), "tamanio_bytes": liberados[direccion]["tamanio"], "tipo": str(tipo),
                 "contenido": "‹liberado›", "esta_liberado": True, "punteros_salientes": []},
                direccion, liberados[direccion])
            return
        info = asignados.get(direccion)
        util = tamanio_util(direccion)
        if tipo.code == gdb.TYPE_CODE_VOID:
            bloques[direccion] = con_seguimiento(
                {"direccion": hex(direccion), "tamanio_bytes": util or 0, "contenido": "void *",
                 "punteros_salientes": []}, direccion, info)
            return
        elemento_bytes = max(1, tipo.sizeof)
        cantidad = max(1, (util or elemento_bytes) // elemento_bytes)
        partes, salientes, campos = [], [], []
        base = gdb.Value(direccion).cast(tipo.pointer())
        for i in range(min(cantidad, max_elementos)):
            try:
                elemento = (base + i).dereference()
                if tipo.code in (gdb.TYPE_CODE_STRUCT, gdb.TYPE_CODE_UNION):
                    textos = []
                    for campo in tipo.fields():
                        if campo.name is None:
                            continue
                        v = elemento[campo.name]
                        tc = campo.type.strip_typedefs()
                        if tc.code == gdb.TYPE_CODE_PTR:
                            destino = int(v)
                            etiqueta = campo.name if cantidad == 1 else "[%d].%s" % (i, campo.name)
                            texto = hex(destino) if destino else "NULL"
                            if destino:
                                salientes.append({"campo": etiqueta, "destino": hex(destino)})
                                encolar(destino, tc.target())
                        else:
                            texto = _corto(v, 24)
                        textos.append("%s=%s" % (campo.name, texto))
                        if cantidad == 1:
                            dato = {"nombre": campo.name, "tipo": str(campo.type), "valor": texto}
                            if tc.code == gdb.TYPE_CODE_PTR:
                                dato["es_puntero"] = True
                            campos.append(dato)
                    partes.append("{" + ", ".join(textos) + "}")
                elif tipo.code == gdb.TYPE_CODE_PTR:
                    destino = int(elemento)
                    partes.append(hex(destino) if destino else "NULL")
                    if destino:
                        salientes.append({"campo": "[%d]" % i, "destino": hex(destino)})
                        encolar(destino, tipo.target())
                else:
                    partes.append(_corto(elemento, 24))
            except (gdb.error, gdb.MemoryError):
                partes.append("‹ilegible›")
                break
        if cantidad > max_elementos:
            partes.append("…")
        contenido = ("[ " + ", ".join(partes) + " ]") if cantidad > 1 else (partes[0] if partes else "")
        datos = {"direccion": hex(direccion), "tamanio_bytes": util or tipo.sizeof, "tipo": str(tipo),
                 "contenido": contenido, "punteros_salientes": salientes}
        if campos:
            datos["campos"] = campos
        bloques[direccion] = con_seguimiento(datos, direccion, info)

    resultado = {"frames": [], "heap": [], "linea": 0, "error": None}
    marcos = []
    marco = gdb.newest_frame()
    while marco is not None and len(marcos) < 20:
        if programa.contiene(marco):
            marcos.append(marco)
        marco = marco.older()
    if marcos:
        resultado["linea"] = marcos[0].find_sal().line

    punteros = []
    for marco in marcos:
        variables, vistos = [], set()
        try:
            bloque = marco.block()
        except RuntimeError:
            bloque = None
        sal = marco.find_sal()
        linea = sal.line
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
                        datos.update(valor=_corto(valor, 60), es_puntero=False)
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
        resultado["frames"].append({"funcion": marco.name(), "archivo": sal.symtab.fullname() if sal.symtab else "",
                                    "direccion_base": base, "direccion_tope": tope, "linea_actual": linea,
                                    "variables": variables})

    for destino, tipo in punteros:
        encolar(destino, tipo)
    while pendientes:
        direccion, tipo = pendientes.pop(0)
        if direccion not in bloques:
            recorrer_bloque(direccion, tipo)
    # Los bloques vivos a los que no se llegó: nadie los apunta, ya no se pueden liberar.
    for direccion, info in sorted(asignados.items(), key=lambda par: par[1]["id"]):
        if direccion not in bloques and len(bloques) < max_bloques:
            bloques[direccion] = con_seguimiento(
                {"direccion": hex(direccion), "tamanio_bytes": info["tamanio"], "contenido": "",
                 "punteros_salientes": [], "alcanzable": False}, direccion, info)
    resultado["heap"] = list(bloques.values())
    if seguimiento is not None:
        resultado["eventos"] = seguimiento.tomar_eventos()
    return resultado


SEGUIMIENTO = None


# La ayuda de los comandos y sus errores van en ASCII: gdb los pasa al juego de caracteres de la
# terminal, y con LC_ALL=C (jonesy lo usa) una tilde hace fallar la carga del módulo entero.
def _argumentos_de_ruta(argumento):
    """Los argumentos de un comando que recibe una ruta.

    `gdb.string_to_argv` trata la barra invertida como escape: una ruta de Windows sin comillas
    (`C:\\Temp\\foto.json`) perdería las barras. Entre comillas, quien llama ya la escapó.
    """
    texto = argumento.strip()
    if texto and not any(c in texto for c in "\"'"):
        return [texto]
    return gdb.string_to_argv(argumento)


class _Seguir(gdb.Command):
    """bishop-seguir [RAIZ]: sigue malloc, calloc, realloc y free del programa bajo RAIZ."""

    def __init__(self):
        super().__init__("bishop-seguir", gdb.COMMAND_DATA)

    def invoke(self, argumento, from_tty):
        global SEGUIMIENTO
        args = _argumentos_de_ruta(argumento)
        raiz = args[0] if args else os.getcwd()
        if SEGUIMIENTO is not None:
            for bp in SEGUIMIENTO.breakpoints:
                bp.delete()
        SEGUIMIENTO = Seguimiento(Programa(raiz=raiz))
        SEGUIMIENTO.activar()


class _Memoria(gdb.Command):
    """bishop-memoria ARCHIVO: escribe en ARCHIVO (JSON) la memoria de la parada actual."""

    def __init__(self):
        super().__init__("bishop-memoria", gdb.COMMAND_DATA)

    def invoke(self, argumento, from_tty):
        args = _argumentos_de_ruta(argumento)
        if len(args) != 1:
            raise gdb.GdbError("uso: bishop-memoria ARCHIVO")
        try:
            gdb.newest_frame()
        except gdb.error:
            raise gdb.GdbError("no hay un programa detenido") from None
        programa = SEGUIMIENTO.programa if SEGUIMIENTO is not None else Programa(raiz=os.getcwd())
        datos = tomar_memoria(programa, SEGUIMIENTO)
        with open(args[0], "w", encoding="utf-8") as salida:
            json.dump(datos, salida, ensure_ascii=False)


_Seguir()
_Memoria()
