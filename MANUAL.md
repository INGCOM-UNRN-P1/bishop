# Manual de Uso y Referencia Técnica: bishop

> **BISHOP** — Visualizador pedagógico de memoria C (Stack, Heap y punteros) en terminal y diagramas
> **Versión:** `0.1.0` · **CLI principal:** `bishop` · **Plugin Ripley:** `bishop`

---

## 1. Arquitectura y Propósito Pedagógico

`bishop` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Inspección, análisis y representación visual de memoria en tiempo de ejecución para programas C.
- Trazado de marcos de llamada de pila (Stack Frames), variables locales y parámetros.
- Representación de punteros, relaciones de direccionamiento e indirecciones multinivel.
- Monitoreo de memoria dinámica en el Heap (`malloc`, `calloc`, `realloc`, `free`).
- Renderizado multi-formato: tablas de texto plano, consola interactiva Rich y diagramas Mermaid.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Aislamiento o contención de ejecuciones inseguras (delegado a `nostromo`).
- Diagnóstico forense post-mortem de core dumps o segfaults (delegado a `hal`).
- Auditoría teórica de alineación y padding de estructuras (delegado a `brett`).

### Principios de Diseño
- **Enfoque Pedagógico:** Diagnósticos y mensajes en español rioplatense orientados a facilitar la comprensión de errores conceptuales.
- **Salida Estructurada Dual:** Soporte nativo para visualización enriquecida en terminal (Rich) y salida parseable para orquestadores (`--json`).
- **Integración Contractual:** Capacidad de emitir secciones de reporte para `dredd` (`dredd-section`) y actuar como satélite orquestado por `ripley`.
- **Idempotencia y Robustez:** Validación de precondiciones y comandos de autodiagnóstico (`doctor`) para verificación del entorno.

---

## 2. Instalación y Requisitos

### Requisitos del Sistema
- **Python:** `>= 3.10` (recomendado Python 3.11 o 3.12).
- **Gestor de paquetes:** [`uv`](https://github.com/astral-sh/uv) (entorno estándar de cátedra).
- **Toolchain C (si aplica):** GCC / Clang, Make, GDB y bibliotecas estándar de desarrollo.

### Instalación en el Entorno de Usuario
Para instalar la herramienta de forma global y aislada en el sistema mediante `uv tool`:
```bash
uv tool install --editable /home/mrtin/dev/tools/bishop
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
bishop doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`bishop trace`](#trace) | Ejecuta el programa, pausa en el punto indicado e inspecciona el estado vivo del Stack y Heap. |
| [`bishop snapshot`](#snapshot) | Toma una foto exacta del estado del Stack y Heap en una línea específica de código. |
| [`bishop heap`](#heap) | Audita exclusivamente el estado del Heap, bloques activos y detección de punteros huérfanos. |
| [`bishop report`](#report) | Genera directamente la sección de reporte Markdown de BISHOP para Dredd o JSON estructurado. |
| [`bishop beginner`](#beginner) | Modo visualización simplificada para principiantes en español rioplatense. |
| [`bishop heap-map`](#heapmap) | Muestra un mapa visual de fragmentación del Heap con bloques libres y ocupados. |
| [`bishop ascii`](#ascii) | Muestra punteros y marcos de Stack con flechas direccionales ASCII en terminal. |
| [`bishop audit`](#audit) | Audita punteros colgantes (en rojo), fugas/huérfanos (en amarillo) y solapamiento de buffers. |
| [`bishop diff`](#diff) | Compara snapshots de memoria antes y después de una invocación de función. |
| [`bishop doctor`](#doctor) | Verifica el estado del entorno de inspección dinámica de memoria BISHOP (Python, GCC, GDB). |

### `bishop trace`

Ejecuta el programa, pausa en el punto indicado e inspecciona el estado vivo del Stack y Heap.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a trazar e inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Función o línea donde pausar la ejecución (ej: 'invertir_vector', 'main:15'). |
| `--mermaid`, `-m` | `bool` | `False` | Emitir diagrama de punteros en formato Mermaid. |
| `--json` | `bool` | `False` | Emitir reporte en formato JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |

#### Ejemplo de Invocación
```bash
bishop trace <fuente>
```

### `bishop snapshot`

Toma una foto exacta del estado del Stack y Heap en una línea específica de código.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--line`, `-l` | `int` | `1` | Número de línea donde tomar la foto de memoria. |
| `--json` | `bool` | `False` | Emitir salida en JSON. |

#### Ejemplo de Invocación
```bash
bishop snapshot <fuente>
```

### `bishop heap`

Audita exclusivamente el estado del Heap, bloques activos y detección de punteros huérfanos.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a auditar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte opcional para el snapshot. |
| `--json` | `bool` | `False` | Emitir reporte en JSON. |

#### Ejemplo de Invocación
```bash
bishop heap <fuente>
```

### `bishop report`

Genera directamente la sección de reporte Markdown de BISHOP para Dredd o JSON estructurado.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[Path]` | `None` | Ruta de destino del archivo Markdown. |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte para el snapshot. |
| `--json` | `bool` | `False` | Emitir reporte estructurado en JSON. |

#### Ejemplo de Invocación
```bash
bishop report <fuente>
```

### `bishop beginner`

Modo visualización simplificada para principiantes en español rioplatense.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte. |
| `--json` | `bool` | `False` | Emitir guía en JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop beginner <fuente>
```

### `bishop heap-map`

Muestra un mapa visual de fragmentación del Heap con bloques libres y ocupados.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte. |
| `--json` | `bool` | `False` | Emitir fragmentación en JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop heap-map <fuente>
```

### `bishop ascii`

Muestra punteros y marcos de Stack con flechas direccionales ASCII en terminal.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte. |
| `--json` | `bool` | `False` | Emitir punteros y relaciones en JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop ascii <fuente>
```

### `bishop audit`

Audita punteros colgantes (en rojo), fugas/huérfanos (en amarillo) y solapamiento de buffers.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a auditar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--break`, `-b` | `Optional[str]` | `None` | Punto de corte. |
| `--json` | `bool` | `False` | Emitir auditoría en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop audit <fuente>
```

### `bishop diff`

Compara snapshots de memoria antes y después de una invocación de función.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a inspeccionar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--antes`, `-a` | `int` | `1` | Línea antes de la llamada. |
| `--despues`, `-d` | `int` | `2` | Línea después de la llamada. |
| `--json` | `bool` | `False` | Emitir diff de memoria en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop diff <fuente>
```

### `bishop doctor`

Verifica el estado del entorno de inspección dinámica de memoria BISHOP (Python, GCC, GDB).

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Emitir diagnóstico en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
bishop doctor
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
bishop trace --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: bishop, tool=bishop, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`bishop` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

---

## 5. Diagnóstico y Códigos de Salida

### Códigos de Retorno (`exit code`)
| Código | Significado |
| :---: | :--- |
| `0` | Ejecución exitosa sin hallazgos críticos ni errores de sintaxis. |
| `1` | Hallazgos pedagógicos detectados, infracción de reglas o advertencias activas. |
| `2` | Error de sintaxis en argumentos CLI o archivo fuente no encontrado. |
| `>2` | Error no recuperable del sistema, fallo de memoria o excepción interna. |

### Diagnóstico del Entorno (`doctor`)
Ante comportamientos inesperados, verificá el estado operativo con:
```bash
bishop doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.