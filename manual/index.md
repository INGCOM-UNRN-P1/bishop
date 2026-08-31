---
title: "Manual de Referencia: bishop"
subtitle: "Bishop — Visualizador Pedagógico de Memoria Stack & Heap en ASCII y Mermaid"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-bishop)=
# Bishop — Visualizador Pedagógico de Memoria Stack & Heap en ASCII y Mermaid

````{abstract}
**Rol en el ecosistema:** Inspección dinámica de memoria en C, renderizando marcos de pila (Stack Frames), variables locales, punteros y bloques del Heap.
````

---

(manual-bishop-proposito)=
## 1. Propósito y Filosofía Pedagógica

La herramienta **`bishop`** forma parte del ecosistema oficial de software de la cátedra. Su diseño sigue principios pedagógicos rigurosos:

1. **Evidencia Técnica Directa**: Todo diagnóstico se fundamenta en la norma ISO C (C11/C23), en el modelo de memoria del sistema o en convenciones arquitectónicas formales.
2. **Acción Correctiva Concreta**: Cada advertencia incluye la prescripción técnica inmediata para resolver el defecto sin recurrir a conjeturas.
3. **Autonomía del Estudiante**: Facilita la autoevaluación local antes de la entrega final del trabajo práctico.
4. **Objetividad Docente**: Estandariza la corrección automática eliminando discrepancias subjetivas en la evaluación.

---

(manual-bishop-instalacion)=
## 2. Instalación y Diagnóstico del Entorno

````{important}
Asegurate de contar con el compilador GCC/Clang y las librerías del sistema instaladas antes de ejecutar `bishop`.
````

Para comprobar el estado de salud de tu entorno de trabajo y las dependencias auxiliares:

````{code-block} bash
# Comprobación de dependencias del sistema
bishop doctor
````

Si se detecta la falta de alguna utilidad (como `gdb`, `valgrind`, `clang-format` o `typst`), el comando indicará el paquete exacto a instalar según tu distribución GNU/Linux o entorno MSYS2.

---

(manual-bishop-comandos)=
## 3. Referencia Completa de Comandos CLI

A continuación se detallan los subcomandos principales disponibles en `bishop`:

| Sintaxis del Comando | Descripción y Efecto |
| :--- | :--- |
| `bishop trace -- ./bin/programa` | Ejecuta el binario bajo GDB y dibuja la memoria en cada instrucción. |
| `bishop trace --format mermaid -- ./bin/programa` | Exporta el estado de memoria a diagrama Mermaid para informes. |
| `bishop inspect <pid>` | Inspecciona la memoria de un proceso en ejecución. |
| `bishop snapshot -o memoria.txt -- ./bin/programa` | Guarda una captura completa del mapa de memoria en ASCII. |

````{tip}
Podés agregar el flag `--json` a la mayoría de los comandos para exportar resultados en formato estructurado o `--md` para generar reportes Markdown para el informe de entrega.
````

---

(manual-bishop-tutorial)=
## 4. Tutorial Paso a Paso con Ejemplos Reales

### Caso de Estudio

Considerá el siguiente fragmento de código representativo:

````{code-block} c
:linenos:
#include <stdlib.h>

void f(int a) {
    int *dinamico = malloc(sizeof(int) * 2);
    dinamico[0] = a;
    dinamico[1] = a * 2;
    // Inspección en este punto
    free(dinamico);
}

int main(void) {
    int x = 42;
    f(x);
    return 0;
}
````

### Ejecución de la Herramienta

Ejecutá el análisis desde tu terminal:

````{code-block} bash
bishop trace -- ./bin/programa
````

### Salida Obtenida en Consola

````{code-block} text
┌────────────────────────────────────────────────────────┐
│ STACK FRAME: f (ret 0x00401180)                        │
│ ├─ a: [ 42 ] @ 0x7fffffffe340                          │
│ └─ dinamico: [ 0x0055555556b2a0 ] @ 0x7fffffffe348    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼ (Heap Allocation: 8 bytes)
┌────────────────────────────────────────────────────────┐
│ HEAP CHUNK @ 0x0055555556b2a0                          │
│ [ 0 ]: 42  |  [ 1 ]: 84                                │
└────────────────────────────────────────────────────────┘
````

````{note}
Prestá atención a la explicación pedagógica generada: la herramienta no solo señala la línea del problema, sino que explica la causa raíz y el impacto en memoria o arquitectura.
````

---

(manual-bishop-ejercicios)=
## 5. Ejercicios Prácticos y Desafíos

Practicá el uso avanzado de **`bishop`** resolviendo los siguientes ejercicios:

````{exercise} Desafío 1: Paso por Referencia vs Paso por Valor
Escribir `swap(int *a, int *b)` y observar los marcos de pila en Bishop.

**Instrucción de ejecución:**
```bash
bishop trace -- ./bin/swap_test
```
````

````{solution} Desafío 1
```bash
bishop trace -- ./bin/swap_test
# Verificá que la operación concluya exitosamente con código de salida 0.
```
````

````{exercise} Desafío 2: Detección de Dangling Pointer
Inspeccionar un puntero tras llamar a free() sin asignarle NULL.

**Instrucción de ejecución:**
```bash
bishop trace -- ./bin/dangling_test
```
````

````{solution} Desafío 2
```bash
bishop trace -- ./bin/dangling_test
# Revisá el archivo generado o el informe en terminal para confirmar la resolución del problema.
```
````

````{exercise} Desafío 3: Diagrama Mermaid de Lista Enlazada
Generar diagrama de una lista de 3 nodos en el Heap.

**Instrucción de ejecución:**
```bash
bishop trace --format mermaid -o memoria.md -- ./bin/test_lista
```
````

````{solution} Desafío 3
```bash
bishop trace --format mermaid -o memoria.md -- ./bin/test_lista
# Comprobá que la salida confirme la ausencia de advertencias o errores pendientes.
```
````

---

(manual-bishop-makefile)=
## 6. Integración en el Flujo de Trabajo y Makefile

Para incorporar `bishop` de forma automática a tu flujo de desarrollo, agregá la siguiente regla en el `Makefile` de tu proyecto:

````{code-block} makefile
check-bishop:
	@echo "=== Ejecutando verificación con bishop ==="
	bishop check src/ include/

.PHONY: check-bishop
````

Ejecutá `make check-bishop` antes de cada commit para asegurar que tu código conserve el estado de aprobación.

---

(manual-bishop-arquitectura)=
## 7. Arquitectura Interna y Mecanismo Técnico

La herramienta **`bishop`** implementa un motor de alta precisión basado en:

- **Tecnología Núcleo:** `GDB/MI Machine Interface + DWARF Symbol Parser + Rich Terminal Tables + Mermaid JS Engine`.
- **Aislamiento y Determinismo:** Diseñada para operar sin efectos colaterales en entornos de integración continua (CI), terminales de estudiantes y servidores docentes headless.
- **Manejo de Errores Pedagógico:** Todo fallo de sintaxis, memoria o lógica se traduce en una acción prescriptiva concreta con su respectiva justificación técnica.

---

(manual-bishop-ecosistema)=
## 8. Integración y Conexión con el Ecosistema

````{note}
Ninguna herramienta opera de forma aislada. **`bishop`** forma parte del pipeline integral de evaluación, verificación y enseñanza de la cátedra.
````

### Diagrama de Flujo e Interoperabilidad

````{mermaid}
graph TD
    DAE[Daedalus: Compilador -g3] -->|Binario con DWARF| BSH[Bishop: Inspector de Memoria]
    BSH -->|Inspección Stack & Heap| GDB[GDB/MI Protocol]
    BSH -->|Diagramas ASCII| TERM[Terminal del Estudiante]
    BSH -->|Diagramas Mermaid| MYST[Myst-Tools: Apuntes y Guías]
    BSH -->|Contexto de Punteros| HAL[Hal: Forense de Crashes]
````

### Matriz de Intercambio de Datos

| Canal | Herramientas Conectadas | Tipo de Datos Transferidos |
| :--- | :--- | :--- |
| **Entradas (Inputs)** | - `daedalus (binarios C con símbolos de depuración -g3)` | Código fuente, AST, binarios, testcases, contratos |
| **Salidas (Outputs)** | - `hal (trazas de memoria)`
- `deckard (diagramas para enunciados)`
- `myst-tools (apuntes)` | Informes Markdown, diagnósticos Rich, JSON, actas |
| **Sincronización** | `sebastian`, `brett`, `hal` | Validación cruzada, flags compartidos y autofix |

### Pipeline de Integración Recomendado

Podés encadenar `bishop` con otras herramientas del ecosistema en una única línea de comando:

````{code-block} bash
# Pipeline de integración típico
daedalus compile src/main.c -g3 -o bin/app && bishop trace --format mermaid -o memoria.md -- ./bin/app
````

