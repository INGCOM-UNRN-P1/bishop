# 🧠 BISHOP — Visualizador Pedagógico de Memoria C

BISHOP es una herramienta standalone diseñada para inspeccionar y visualizar el estado vivo de la memoria (Stack Frames, variables locales, direcciones y bloques asignados en el Heap) en programas C, renderizando diagramas ASCII interactivos en terminal y diagramas Mermaid.

---

## 🎯 Alcance

### Qué cubre
- Inspección, análisis y representación visual de memoria en tiempo de ejecución para programas C.
- Trazado de marcos de llamada de pila (Stack Frames), variables locales y parámetros.
- Representación de punteros, relaciones de direccionamiento e indirecciones multinivel.
- Monitoreo de memoria dinámica en el Heap (`malloc`, `calloc`, `realloc`, `free`).
- Renderizado multi-formato: tablas de texto plano, consola interactiva Rich y diagramas Mermaid.

### Qué no cubre (Límites y Delegación)
- Aislamiento o contención de ejecuciones inseguras (delegado a `nostromo`).
- Diagnóstico forense post-mortem de core dumps o segfaults (delegado a `hal`).
- Auditoría teórica de alineación y padding de estructuras (delegado a `brett`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Linux / POSIX o Windows (WSL / MSYS2). Python >= 3.10.

### Dependencias Externas y Binarios
- `gcc`, `gdb` (opcional, para extracción de tablas de símbolos con información DWARF `-g3`).

### Integración en el Ecosistema
- CLI `bishop`. Subcomando `bishop doctor` para validar soporte de introspección.

---

## Uso Rápido

```bash
# 1. Trazar ejecución e inspeccionar memoria en breakpoint
bishop trace main.c --break invertir_vector

# 2. Emitir diagrama de punteros en sintaxis Mermaid
bishop trace main.c --mermaid

# 3. Tomar una foto del estado de memoria en una línea específica
bishop snapshot main.c --line 25

# 4. Auditar bloques activos en Heap y detectar punteros huérfanos
bishop heap main.c

# 5. Salida estructurada JSON
bishop trace main.c --json
```
