# Changelog

Todos los cambios notables de este proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/);
versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Agregado

- `bishop gdb-script` y el módulo `gdb_memoria.py`, que un depurador carga en su sesión de gdb:
  - `bishop-seguir` numera cada reserva del programa con su línea, sin detenerlo.
  - `bishop-memoria` escribe la memoria de la parada actual: marcos, bloques con sus campos, fugas sin referencias y lo que pasó con el heap desde la foto anterior.
  - jonesy lo dibuja en cada paso (Ola 42).
- `bishop layout --abi`: el layout con los tamaños de los tipos de otra plataforma (`x86_64-windows` para MSYS2, `i386`…), con la misma tabla de brett que usa kane (Ola 28).

### Cambiado

- `snapshot`, `heap` y `diagram` usan el mismo módulo:
  - Las reservas se siguen con breakpoints que no detienen el programa.
  - Sólo cuentan las del código del programa (más `strdup`).
  - Un bloque vivo sin referencias aparece como fuga.
- brett fijado en `044dfa4` (publicado, con `ABIS`).

## [0.2.0] - 2026-09-28

Primera versión con registro de cambios; lo anterior está en el historial de git.

### Agregado

- **cli**: cumplir el contrato de línea de comandos de LINEAMIENTOS §3.2 (N-ECO-04) (`c527b8b`)

### Documentación

- agregar el texto de la licencia GPL-3.0-or-later que declara pyproject (N-ECO-06) (`cb2353a`)
- incorporar manual de uso integral y referencia tecnica (bishop) (`c9133e6`)

### Mantenimiento

- **calidad**: verificar errores de Python y dependencias vulnerables (N-ECO-08, N-ECO-13) (`b129106`)
- **deps**: mover las dependencias de desarrollo a dependency-groups (N-ECO-07) (`3f63048`)
