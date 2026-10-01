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

<!-- p1:referencia:inicio — generado por p1-tools/scripts/readme_generado.py: no editar a mano -->

## Referencia rápida

### Requisitos

- Python ≥ 3.11 y [uv](https://docs.astral.sh/uv/getting-started/installation/).
- Programas del sistema: `gcc`.

| Sistema | `gcc` |
|:--|:--|
| Debian / Ubuntu | `sudo apt install gcc` |
| Fedora | `sudo dnf install gcc` |
| Windows | incluido en el entorno de la cátedra (MSYS2 UCRT64) |
| macOS | `xcode-select --install` (clang como `gcc`) |

### Comandos

| Comando | Descripción |
|:--|:--|
| `sebastian trace` | Ejecuta el código instrumentado, traza las llamadas recursivas y visualiza el árbol de ejecución. |
| `sebastian check`, `sebastian analyze` | Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento. |
| `sebastian report` | Genera directamente la sección de reporte Markdown de SEBASTIAN para Dredd. |
| `sebastian doctor` | Verifica el estado del entorno de análisis de recursión y stack SEBASTIAN (Python, GCC). |

Ayuda de cada comando: `sebastian <comando> -h`.

### Salida JSON

Con `--json`, estos comandos emiten el resultado como JSON por la salida estándar, para usarlo desde scripts, ripley o dredd: `sebastian trace`, `sebastian check`, `sebastian analyze`, `sebastian doctor`. El de `doctor --json` lleva `schema_version` y `ok`.

### Códigos de salida

| Código | Significado |
|:--|:--|
| `0` | Terminó bien (en `doctor`: está todo lo requerido). |
| `1` | El comando encontró problemas (hallazgos, pruebas que fallan, un umbral que no se alcanza) o un dato no se pudo usar (un archivo ilegible, un formato inválido). |
| `2` | Error de uso: comando, opción o argumento inválido. |

<!-- p1:referencia:fin -->
