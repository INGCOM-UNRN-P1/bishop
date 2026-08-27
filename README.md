# 🧠 BISHOP — Visualizador Pedagógico de Memoria C

BISHOP es una herramienta standalone diseñada para inspeccionar y visualizar el estado vivo de la memoria (Stack Frames, variables locales, direcciones y bloques asignados en el Heap) en programas C, renderizando diagramas ASCII interactivos en terminal y diagramas Mermaid.

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
