---
title: "Manual de Referencia: sebastian"
subtitle: "Sebastian — Analizador de Funciones Recursivas, Caso Base y Árboles de Llamadas"
author: "Cátedra de Algoritmos y Programación"
date: "2026-08-31"
---

(manual-sebastian)=
# Sebastian — Analizador de Funciones Recursivas, Caso Base y Árboles de Llamadas

````{abstract}
**Rol en el ecosistema:** Detección estática y dinámica de funciones recursivas, verificación formal de caso base, análisis de consumo de marcos de pila (Stack Depth) y exportación de árboles de llamadas en ASCII/Mermaid.
````

---

(manual-sebastian-proposito)=
## 1. Propósito y Filosofía Pedagógica

La herramienta **`sebastian`** forma parte del ecosistema oficial de software de la cátedra. Su diseño sigue principios pedagógicos rigurosos:

1. **Evidencia Técnica Directa**: Todo diagnóstico se fundamenta en la norma ISO C (C11/C23), en el modelo de memoria del sistema o en convenciones arquitectónicas formales.
2. **Acción Correctiva Concreta**: Cada advertencia incluye la prescripción técnica inmediata para resolver el defecto sin recurrir a conjeturas.
3. **Autonomía del Estudiante**: Facilita la autoevaluación local antes de la entrega final del trabajo práctico.
4. **Objetividad Docente**: Estandariza la corrección automática eliminando discrepancias subjetivas en la evaluación.

---

(manual-sebastian-instalacion)=
## 2. Instalación y Diagnóstico del Entorno

````{important}
Asegurate de contar con el compilador GCC/Clang y las librerías del sistema instaladas antes de ejecutar `sebastian`.
````

Para comprobar el estado de salud de tu entorno de trabajo y las dependencias auxiliares:

````{code-block} bash
# Comprobación de dependencias del sistema
sebastian doctor
````

Si se detecta la falta de alguna utilidad (como `gdb`, `valgrind`, `clang-format` o `typst`), el comando indicará el paquete exacto a instalar según tu distribución GNU/Linux o entorno MSYS2.

---

(manual-sebastian-comandos)=
## 3. Referencia Completa de Comandos CLI

A continuación se detallan los subcomandos principales disponibles en `sebastian`:

| Sintaxis del Comando | Descripción y Efecto |
| :--- | :--- |
| `sebastian trace src/recursivo.c` | Detecta funciones recursivas y verifica la presencia de caso base. |
| `sebastian tree src/arbol.c --function recorrer` | Dibuja el árbol de llamadas recursivas en ASCII o Mermaid. |
| `sebastian stack-profile -- ./bin/fibonacci 10` | Mide la profundidad máxima del Stack alcanzada en runtime. |
| `sebastian doctor` | Verifica analizadores de AST y perfiles de pila. |

````{tip}
Podés agregar el flag `--json` a la mayoría de los comandos para exportar resultados en formato estructurado o `--md` para generar reportes Markdown para el informe de entrega.
````

---

(manual-sebastian-tutorial)=
## 4. Tutorial Paso a Paso con Ejemplos Reales

### Caso de Estudio

Considerá el siguiente fragmento de código representativo:

````{code-block} c
:linenos:
// Función recursiva analizada por Sebastian
int factorial(int n) {
    if (n <= 1) { // Caso base verificado por Sebastian
        return 1;
    }
    return n * factorial(n - 1); // Llamada recursiva con reducción de tamaño
}
````

### Ejecución de la Herramienta

Ejecutá el análisis desde tu terminal:

````{code-block} bash
sebastian trace src/recursivo.c
````

### Salida Obtenida en Consola

````{code-block} text
[✓] SEBASTIAN RECURSION ANALYSIS: 'factorial()' en src/recursivo.c:
    • Tipo de recursión: Recursión lineal simple (no terminal).
    • Caso Base: Detectado en línea 2 ('if (n <= 1) return 1;').
    • Condición de Convergencia: Parámetro 'n' decrece hacia el caso base ('n - 1').
    • Profundidad de Stack estimada: O(N) marcos de pila (aprox. 32 bytes por marco).
````

````{note}
Prestá atención a la explicación pedagógica generada: la herramienta no solo señala la línea del problema, sino que explica la causa raíz y el impacto en memoria o arquitectura.
````

---

(manual-sebastian-ejercicios)=
## 5. Ejercicios Prácticos y Desafíos

Practicá el uso avanzado de **`sebastian`** resolviendo los siguientes ejercicios:

````{exercise} Desafío 1: Detección de Recursión Infinita sin Caso Base
Analizar una función recursiva defectuosa y encontrar por qué produce Stack Overflow.

**Instrucción de ejecución:**
```bash
sebastian trace src/bug_recursivo.c
```
````

````{solution} Desafío 1
```bash
sebastian trace src/bug_recursivo.c
# Verificá que la operación concluya exitosamente con código de salida 0.
```
````

````{exercise} Desafío 2: Renderizado de Árbol de Llamadas de Fibonacci
Visualizar el árbol de ramificación de Fibonacci en Mermaid.

**Instrucción de ejecución:**
```bash
sebastian tree src/fib.c --function fib --format mermaid
```
````

````{solution} Desafío 2
```bash
sebastian tree src/fib.c --function fib --format mermaid
# Revisá el archivo generado o el informe en terminal para confirmar la resolución del problema.
```
````

````{exercise} Desafío 3: Optimización a Recursión de Cola (Tail Recursion)
Transformar una función recursiva para permitir optimización TCO por el compilador.

**Instrucción de ejecución:**
```bash
sebastian trace src/tail_rec.c
```
````

````{solution} Desafío 3
```bash
sebastian trace src/tail_rec.c
# Comprobá que la salida confirme la ausencia de advertencias o errores pendientes.
```
````

---

(manual-sebastian-makefile)=
## 6. Integración en el Flujo de Trabajo y Makefile

Para incorporar `sebastian` de forma automática a tu flujo de desarrollo, agregá la siguiente regla en el `Makefile` de tu proyecto:

````{code-block} makefile
check-sebastian:
	@echo "=== Ejecutando verificación con sebastian ==="
	sebastian check src/ include/

.PHONY: check-sebastian
````

Ejecutá `make check-sebastian` antes de cada commit para asegurar que tu código conserve el estado de aprobación.
