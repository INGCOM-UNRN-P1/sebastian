# 🌀 SEBASTIAN — Analizador de Recursión y Stack Frame en C

> 📖 **Manual de Usuario:** Para una guía exhaustiva de comandos, banderas, arquitectura y ejemplos, consultá el [Manual de Uso](MANUAL.md).

SEBASTIAN es una herramienta pedagógica diseñada para analizar algoritmos recursivos en C, medir el consumo de memoria en la pila de ejecución (Stack), detectar riesgos de `Stack Overflow` y renderizar árboles de ejecución interactivos en terminal y diagramas Mermaid.

---

## 🎯 Alcance

### Qué cubre
- Análisis **estático** (`analyze`/`check`, sin ejecutar nada) de algoritmos recursivos en programas C: tipo de recursión, caso base y riesgo de overflow.
- Trazado **dinámico** (`trace`): compila con instrumentación (vía `daedalus`) y ejecuta en el sandbox de `nostromo` para medir la profundidad máxima realmente alcanzada; requiere `gcc`. Si la medición falla, el resultado vuelve al análisis estático y el campo `origen_medicion` lo declara (`dinamica` o `estatica`).
- Tamaño del marco de pila (Stack Frame Size): es una **estimación heurística** (32 bytes base, +32 con `double`/`long`, +64 con arreglos), no una medición; el consumo pico = profundidad × bytes por frame.
- Detección temprana de riesgos de desbordamiento de pila (Stack Overflow) y ramas recursivas infinitas.
- Visualización del árbol de llamadas recursivas en consola terminal y en diagramas Mermaid.

### Qué no cubre (Límites y Delegación)
- Trazado de llamadas no recursivas en todo el proyecto (delegado a `giger`).
- Perfilado de contadores de hardware del procesador (delegado a `ferro`).
- Aislamiento de ejecución en sandbox (delegado a `nostromo`).

---

## 📋 Requisitos

### Requisitos de Sistema y Entorno
- Linux / POSIX o Windows (MSYS2 / WSL). Python >= 3.10.

### Dependencias Externas y Binarios
- `gcc`.

### Integración en el Ecosistema
- CLI `sebastian`. Subcomando `sebastian doctor`.

---

## Uso Rápido

```bash
# 1. Trazar ejecución recursiva y renderizar árbol en terminal
sebastian trace factorial.c --function factorial

# 2. Emitir diagrama en sintaxis Mermaid
sebastian trace fibonacci.c --mermaid

# 3. Analizar estáticamente todas las funciones de un archivo
sebastian analyze algoritmo.c

# 4. Salida estructurada JSON para pipelines CI
sebastian trace factorial.c --json
```
