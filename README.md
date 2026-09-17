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
- `gcc`, `gdb` (opcional, para extracción de tablas de símbolos con información DWARF `-g`). Fallback automático a análisis estático de variables si no están presentes.

### Integración en el Ecosistema
- CLI `bishop`. Subcomando `bishop doctor` para validar soporte de introspección del entorno.
- **Contrato de Memoria Canónico (R-B7):**
  - **Dredd:** Bishop exporta secciones de informe formateadas con tablas de frames y bloques vía `bishop report` o `bishop trace --md`.
  - **Scorm-tools:** La salida estructurada `SnapshotMemoria.to_dict()` (`--json`) implementa claves canónicas bilingües y compatibles (`frames`/`stack`, `function`/`funcion`, `address`/`direccion`, `value`/`valor`, `target_address`/`direccion_apuntada`, `size`/`tamanio_bytes`, `heap[].pointers`/`punteros_referenciantes`) consumidas directamente por `scorm-tools diagram-memory` para generar diagramas Mermaid en lecciones interactivas.
  - **Deckard:** Deckard comparte y adopta las convenciones visuales de nomenclatura y layout de Stack/Heap de Bishop en `deckard diagram-memory` para la formulación pedagógica de enunciados de ejercicios.
  - **Ripley:** Plugin satélite registrado en `ripley.plugins` (`src/bishop/ripley_plugin.py`) para chequeos pedagógicos de memoria dinámica y fugas.
  - **Daedalus:** Delegación canónica de compilación de binarios de depuración (`-g -O0`) con fallback transparente.

---

## Uso Rápido

```bash
# 1. Trazar ejecución e inspeccionar memoria en punto de corte
bishop trace main.c --break invertir_vector
bishop trace main.c --mermaid                  # Diagrama de punteros Mermaid
bishop trace main.c --md -o reporte.md        # Sección Markdown para Dredd
bishop trace main.c --json                    # Schema JSON versionado 1.0.0

# 2. Tomar una foto exacta de memoria en una línea específica
bishop snapshot main.c --line 25 [--json]

# 3. Auditar estado del Heap (autodetección de breakpoint tras malloc o explícito)
bishop heap main.c [--break main:6] [--json]

# 4. Generar reporte Markdown o JSON para integración con evaluadores (Dredd)
bishop report main.c [-o reporte.md] [--break 15] [--json]

# 5. Modo pedagógico simplificado para principiantes en español rioplatense
bishop beginner main.c [--break 10] [--json]

# 6. Mapa visual de fragmentación del Heap (bloques activos vs liberados)
bishop heap-map main.c [--break 12] [--json]

# 7. Visualización ASCII direccional de punteros y marcos en terminal
bishop ascii main.c [--break main] [--json]

# 8. Auditoría estática/dinámica de punteros colgantes, fugas y desbordamiento
bishop audit main.c [--break 20] [--json]

# 9. Comparación diferencial de memoria antes y después de una llamada
bishop diff main.c --antes 5 --despues 10 [--json]

# 10. Diagnóstico del entorno (Python >= 3.10, GCC, GDB)
bishop doctor [--json]
```
