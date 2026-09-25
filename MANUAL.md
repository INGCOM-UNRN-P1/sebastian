# Manual de Uso y Referencia Técnica: sebastian

> **SEBASTIAN** — Analizador de llamadas recursivas, consumo de stack frame y riesgos de stack overflow en C
> **Versión:** `0.1.0` · **CLI principal:** `sebastian` · **Plugin Ripley:** `sebastian`

---

## 1. Arquitectura y Propósito Pedagógico

`sebastian` forma parte del ecosistema de herramientas de la cátedra de Programación 1 (UNRN). Su objetivo central es resolver de forma modular, determinista y automatizada las tareas asociadas a su dominio específico dentro del ciclo de desarrollo, evaluación y aprendizaje de software en C.

### Alcance Funcional (Qué cubre)
- Análisis **estático** (`analyze`/`check`, sin ejecutar nada) de algoritmos recursivos en programas C: tipo de recursión, caso base y riesgo de overflow.
- Trazado **dinámico** (`trace`): compila con instrumentación (vía `daedalus`) y ejecuta en el sandbox de `nostromo` para medir la profundidad máxima realmente alcanzada; requiere `gcc`. Si la medición falla, el resultado vuelve al análisis estático y el campo `origen_medicion` lo declara (`dinamica` o `estatica`).
- Tamaño del marco de pila (Stack Frame Size): es una **estimación heurística** (32 bytes base, +32 con `double`/`long`, +64 con arreglos), no una medición; el consumo pico = profundidad × bytes por frame.
- Detección temprana de riesgos de desbordamiento de pila (Stack Overflow) y ramas recursivas infinitas.
- Visualización del árbol de llamadas recursivas en consola terminal y en diagramas Mermaid.

### Límites de Responsabilidad y Delegación (Qué no cubre)
- Trazado de llamadas no recursivas en todo el proyecto (delegado a `giger`).
- Perfilado de contadores de hardware del procesador (delegado a `ferro`).
- Aislamiento de ejecución en sandbox (delegado a `nostromo`).

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
uv tool install --editable /home/mrtin/dev/tools/sebastian
```

### Verificación de Instalación
Ejecutá el comando `doctor` para constatar que todas las dependencias y binarios requeridos estén presentes y operativos:
```bash
sebastian doctor
```

---

## 3. Guía Integral de Comandos (CLI)

| Comando | Descripción Breve |
| :--- | :--- |
| [`sebastian trace`](#trace) | Ejecuta el código instrumentado, traza las llamadas recursivas y visualiza el árbol de ejecución. |
| [`sebastian check`](#check) | Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento. |
| [`sebastian analyze`](#analyze) | Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento. |
| [`sebastian report`](#report) | Genera directamente la sección de reporte Markdown de SEBASTIAN para Dredd. |
| [`sebastian doctor`](#doctor) | Verifica el estado del entorno de análisis de recursión y stack SEBASTIAN (Python, GCC). |

### `sebastian trace`

Ejecuta el código instrumentado, traza las llamadas recursivas y visualiza el árbol de ejecución.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C con la función recursiva a trazar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--function`, `-f` | `Optional[str]` | `None` | Nombre de la función recursiva a trazar. |
| `--args` | `Optional[List[str]]` | `None` | Argumentos para el programa al ejecutar. |
| `--stdin`, `-i` | `Optional[str]` | `None` | Entrada estándar para el programa. |
| `--tree/--no-tree` | `bool` | `True` | Mostrar árbol de llamadas en terminal. |
| `--mermaid`, `-m` | `bool` | `False` | Emitir diagrama en formato Mermaid. |
| `--json` | `bool` | `False` | Emitir reporte en formato JSON. |

#### Ejemplo de Invocación
```bash
sebastian trace <fuente>
```

### `sebastian check`

Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento.

Códigos de salida: 0 análisis correcto, 2 archivo inexistente y, solo con
--fail-on-high-risk, 1 si hay riesgo ALTO.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a analizar estáticamente. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Emitir reporte en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--fail-on-high-risk` | `bool` | `False` | Salir con código 1 si alguna función tiene riesgo de overflow ALTO (por defecto siempre 0). |

#### Ejemplo de Invocación
```bash
sebastian check <fuente>
```

### `sebastian analyze`

Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento.

Códigos de salida: 0 análisis correcto, 2 archivo inexistente y, solo con
--fail-on-high-risk, 1 si hay riesgo ALTO.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a analizar estáticamente. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Emitir reporte en JSON. |
| `--md`, `--output-md`, `-o` | `Optional[Path]` | `None` | Generar sección de reporte en formato Markdown para fusión en Dredd. |
| `--fail-on-high-risk` | `bool` | `False` | Salir con código 1 si alguna función tiene riesgo de overflow ALTO (por defecto siempre 0). |

#### Ejemplo de Invocación
```bash
sebastian analyze <fuente>
```

### `sebastian report`

Genera directamente la sección de reporte Markdown de SEBASTIAN para Dredd.

#### Argumentos
| Argumento | Tipo | Descripción |
| :--- | :--- | :--- |
| `fuente` | `Path` | Archivo C a analizar. |

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--output`, `-o` | `Optional[Path]` | `None` | Ruta de destino del archivo Markdown. |

#### Ejemplo de Invocación
```bash
sebastian report <fuente>
```

### `sebastian doctor`

Verifica el estado del entorno de análisis de recursión y stack SEBASTIAN (Python, GCC).

#### Opciones y Banderas
| Opción / Banderas | Tipo | Por Defecto | Descripción |
| :--- | :--- | :--- | :--- |
| `--json` | `bool` | `False` | Emitir diagnóstico en formato JSON estructurado. |

#### Ejemplo de Invocación
```bash
sebastian doctor
```

---

## 4. Formatos de Salida e Integración con el Ecosistema

### Modo Interactivo / Terminal (Rich)
Por defecto, la herramienta renderiza paneles, árboles y tablas estilizadas para facilitar la lectura del estudiante y docente en terminales modernas con soporte ANSI.

### Modo Estructurado JSON (`--json`)
Para integración con pipelines de CI/CD, scripts de automatización u orquestadores externos, la opción `--json` emite un documento JSON estricto por la salida estándar (`stdout`), dirigiendo cualquier mensaje de logging a `stderr`:
```bash
sebastian trace --json
```

### Integración con Dredd (`dredd-section`)
Cuando la herramienta genera reportes de evaluación para entregas de alumnos, produce una sección Markdown estandarizada conforme al contrato de integración de Dredd (v1.0.0):
```markdown
<!-- dredd-section: sebastian, tool=sebastian, version=0.1.0, status=ok -->
```
Este encabezado garantiza la agregación determinista de los hallazgos en la rúbrica docente.

### Integración con Ripley
`sebastian` está registrada en el catálogo de plugins satélites de Ripley (`SATELLITE_CATALOG`). Puede invocarse directamente a través del motor de evaluación de Ripley configurando el análisis en `ripley.toml`.

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
sebastian doctor
```
Comprueba la presencia de las dependencias requeridas y la integridad de los componentes del paquete.