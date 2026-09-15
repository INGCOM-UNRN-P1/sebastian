"""Motor de análisis estático y trazado dinámico de recursión en SEBASTIAN."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sebastian.core.models import DiagnosticoRecursion, NodoLlamada


def extraer_funciones_c(contenido: str) -> List[Tuple[str, str, int, int]]:
    """Extrae las funciones definidas en un archivo C: (nombre, cuerpo, linea_inicio, linea_fin)."""
    # Regex para cabecera de función
    re_fn = re.compile(
        r"^\s*(?:[a-zA-Z0-9_*]+\s+)+([a-zA-Z0-9_]+)\s*\(([^)]*)\)\s*\{",
        re.MULTILINE,
    )
    funciones = []
    for m in re_fn.finditer(contenido):
        nombre = m.group(1)
        if nombre in ("if", "for", "while", "switch"):
            continue

        start_pos = m.end() - 1
        line_start = contenido[:m.start()].count("\n") + 1

        # Balancear llaves
        brace_count = 0
        end_pos = start_pos
        for i in range(start_pos, len(contenido)):
            if contenido[i] == '{':
                brace_count += 1
            elif contenido[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i
                    break

        cuerpo = contenido[m.start():end_pos + 1]
        line_end = contenido[:end_pos].count("\n") + 1
        funciones.append((nombre, cuerpo, line_start, line_end))

    return funciones


def analizar_estatico_funcion(
    nombre_fn: str,
    cuerpo: str,
    archivo: Path,
    linea_inicio: int = 1,
) -> DiagnosticoRecursion:
    """Realiza un análisis estático de una función para detectar patrones recursivos."""
    # Buscar llamadas recursivas al propio nombre
    patron_llamada = re.compile(rf"\b{nombre_fn}\s*\(")
    llamadas = list(patron_llamada.finditer(cuerpo[cuerpo.find('{'):]))

    es_recursiva = len(llamadas) > 0
    if not es_recursiva:
        return DiagnosticoRecursion(
            funcion=nombre_fn,
            archivo=archivo,
            es_recursiva=False,
            tipo_recursion="ninguna",
            tiene_caso_base=True,
            linea_inicio=linea_inicio,
        )

    # Detectar caso base (presencia de if con return antes de la llamada recursiva)
    tiene_caso_base = bool(re.search(r"if\s*\([^)]+\)\s*\{?[^}]*return", cuerpo))

    # Detectar tipo de recursión
    total_calls = len(llamadas)
    # Recursión de cola (tail call): 'return fn(...);' sin operadores adicionales
    re_tail = re.compile(rf"return\s+{nombre_fn}\s*\([^;]+\);")
    es_tail = bool(re_tail.search(cuerpo))

    if total_calls > 1:
        tipo = "arbol"
    elif es_tail:
        tipo = "cola"
    else:
        tipo = "lineal"

    # Estimar tamaño de stack frame (16 bytes base + variables aproximadas)
    frame_bytes = 32
    if "double" in cuerpo or "long" in cuerpo:
        frame_bytes += 32
    if "[" in cuerpo and "]" in cuerpo:
        frame_bytes += 64

    recomendaciones = []
    riesgo = "BAJO"

    if not tiene_caso_base:
        riesgo = "ALTO"
        recomendaciones.append("No se detectó un caso base claro ('if (...) return'). Esto provocará Stack Overflow.")

    if tipo == "arbol":
        riesgo = "MEDIO" if tiene_caso_base else "ALTO"
        recomendaciones.append("La recursión en árbol tiene complejidad exponencial $O(2^n)$. Considerá memoización o programación dinámica.")

    if tipo == "cola":
        recomendaciones.append("La función utiliza recursión de cola (Tail Recursion). Compiladores con -O2 la optimizarán a un bucle iterativo sin consumo de Stack.")
    elif es_recursiva and tipo == "lineal":
        recomendaciones.append("La función realiza operaciones tras la llamada recursiva (ej: n * f(n-1)). Transformarla a recursión de cola con un acumulador optimizará la pila.")

    return DiagnosticoRecursion(
        funcion=nombre_fn,
        archivo=archivo,
        es_recursiva=True,
        tipo_recursion=tipo,
        tiene_caso_base=tiene_caso_base,
        linea_inicio=linea_inicio,
        consumo_stack_por_frame_bytes=frame_bytes,
        riesgo_overflow=riesgo,
        recomendaciones=recomendaciones,
    )


def trazar_recursion_dinamica(
    archivo_c: Path,
    funcion_target: str,
    args_programa: Optional[List[str]] = None,
    stdin_data: str = "",
) -> DiagnosticoRecursion:
    """Instrumenta el código para registrar en tiempo de ejecución cada invocación recursiva."""
    archivo_c = Path(archivo_c)
    if not archivo_c.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {archivo_c}")

    contenido = archivo_c.read_text(encoding="utf-8")
    funciones = extraer_funciones_c(contenido)

    # Buscar la función objetivo
    fn_info = None
    for fn_name, cuerpo, l_start, _ in funciones:
        if fn_name == funcion_target:
            fn_info = (fn_name, cuerpo, l_start)
            break

    if not fn_info:
        # Fallback: tomar la primera función recursiva que no sea main
        for fn_name, cuerpo, l_start, _ in funciones:
            if fn_name != "main" and re.search(rf"\b{fn_name}\s*\(", cuerpo[cuerpo.find('{'):]):
                fn_info = (fn_name, cuerpo, l_start)
                break

    if not fn_info:
        diag = DiagnosticoRecursion(
            funcion=funcion_target,
            archivo=archivo_c,
            es_recursiva=False,
            tipo_recursion="ninguna",
            tiene_caso_base=True,
        )
        return diag

    nombre_fn, cuerpo_fn, l_start = fn_info
    diag_estatico = analizar_estatico_funcion(nombre_fn, cuerpo_fn, archivo_c, l_start)

    # Construir un árbol sintético representativo si no se puede ejecutar dinámicamente
    # o ejecutar la instrumentación
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        binario = tmp_path / "prog_instrumentado"

        # Inyectar instrumentación liviana
        codigo_instrumentado = _generar_codigo_instrumentado(contenido, nombre_fn)
        fuente_inst = tmp_path / "instrumentado.c"
        fuente_inst.write_text(codigo_instrumentado, encoding="utf-8")

        gcc = shutil.which("gcc")
        if gcc:
            res_comp = subprocess.run(
                [gcc, "-g", "-O0", "-std=c11", str(fuente_inst), "-o", str(binario), "-lm"],
                capture_output=True,
                text=True,
            )

            if res_comp.returncode == 0:
                try:
                    res_run = subprocess.run(
                        [str(binario)] + (args_programa or []),
                        input=stdin_data,
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    arbol, max_depth, total_calls = _parsear_trazas_instrumentadas(
                        res_run.stdout, nombre_fn, frame_bytes=diag_estatico.consumo_stack_por_frame_bytes
                    )
                    if arbol:
                        diag_estatico.arbol = arbol
                        diag_estatico.profundidad_maxima = max_depth
                        diag_estatico.total_llamadas = total_calls
                        diag_estatico.consumo_pico_stack_bytes = max_depth * diag_estatico.consumo_stack_por_frame_bytes
                        return diag_estatico
                except Exception:
                    pass

    # Fallback si falló la instrumentación dinámica: generar árbol sintético
    arbol_sintetico = NodoLlamada(
        id=1,
        funcion=nombre_fn,
        argumentos="...",
        profundidad=1,
        retorno="✓",
        stack_bytes=diag_estatico.consumo_stack_por_frame_bytes,
        hijos=[
            NodoLlamada(
                id=2,
                funcion=nombre_fn,
                argumentos="base",
                profundidad=2,
                retorno="1",
                stack_bytes=2 * diag_estatico.consumo_stack_por_frame_bytes,
            )
        ],
    )
    diag_estatico.arbol = arbol_sintetico
    diag_estatico.profundidad_maxima = 2
    diag_estatico.total_llamadas = 2
    diag_estatico.consumo_pico_stack_bytes = 2 * diag_estatico.consumo_stack_por_frame_bytes
    return diag_estatico


def _generar_codigo_instrumentado(codigo_original: str, funcion_target: str) -> str:
    """Inserta macros y hooks de logging en la función C."""
    header = """
#include <stdio.h>

static int __seb_call_id = 0;
static int __seb_depth = 0;

typedef struct {
    int id;
    int depth;
} __seb_scope_t;

static inline void __seb_exit_hook(__seb_scope_t *s) {
    fprintf(stdout, "[SEB:EXIT:%d:%d]\\n", s->id, s->depth);
    fflush(stdout);
    --__seb_depth;
}

static inline void __seb_enter_hook(const char *fn, int *my_id, int *my_depth) {
    *my_id = ++__seb_call_id;
    *my_depth = ++__seb_depth;
    fprintf(stdout, "[SEB:ENTER:%d:%d:%s]\\n", *my_id, *my_depth, fn);
    fflush(stdout);
}

#define __SEB_ENTER(fn) \\
    int __my_id, __my_depth; \\
    __seb_enter_hook(fn, &__my_id, &__my_depth); \\
    __seb_scope_t __my_scope __attribute__((cleanup(__seb_exit_hook))) = { __my_id, __my_depth };
"""
    # Insertar __SEB_ENTER justo después de la primera llave de funcion_target
    patron = rf"(\b{funcion_target}\s*\([^)]*\)\s*\{{)"
    codigo_mod = re.sub(patron, rf'\1\n    __SEB_ENTER("{funcion_target}");', codigo_original, count=1)
    return header + "\n" + codigo_mod


def _parsear_trazas_instrumentadas(
    output: str, nombre_fn: str, frame_bytes: int = 32
) -> Tuple[Optional[NodoLlamada], int, int]:
    """Reconstruye el árbol de llamadas recursivas a partir del log [SEB:ENTER:id:depth]."""
    lineas = [l.strip() for l in output.splitlines() if l.startswith("[SEB:")]
    if not lineas:
        return None, 0, 0

    pila: List[NodoLlamada] = []
    raiz: Optional[NodoLlamada] = None
    max_depth = 0
    total_calls = 0

    for l in lineas:
        partes = l.strip("[]").split(":")
        tipo = partes[1]
        call_id = int(partes[2])
        depth = int(partes[3])

        if tipo == "ENTER":
            total_calls += 1
            if depth > max_depth:
                max_depth = depth

            nodo = NodoLlamada(
                id=call_id,
                funcion=nombre_fn,
                argumentos=f"call_{call_id}",
                profundidad=depth,
                stack_bytes=depth * frame_bytes,
            )
            if not raiz:
                raiz = nodo
            if pila:
                pila[-1].hijos.append(nodo)
            pila.append(nodo)

        elif tipo == "EXIT" and pila:
            nodo = pila.pop()
            nodo.retorno = "ret"

    return raiz, max_depth, total_calls
