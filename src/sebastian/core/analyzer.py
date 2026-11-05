"""Motor de análisis estático y trazado dinámico de recursión en SEBASTIAN."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sebastian.core.masking import enmascarar_comentarios_y_literales
from sebastian.core.models import DiagnosticoRecursion, NodoLlamada


# El árbol se recorre con recursión y se dibuja en la terminal: una recursión infinita llega a
# cientos de miles de marcos. Los contadores siguen midiendo todo; lo que se recorta es el dibujo.
PROFUNDIDAD_ARBOL = 50
NODOS_ARBOL = 2000
TIEMPO_LIMITE = 3.0
_TRAZA = re.compile(r"\[SEB:(ENTER|EXIT):(\d+):(\d+)(?::[^\]\n]*)?\]")


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
    # Los comentarios y literales se blanquean antes de buscar: sin esto, el
    # nombre de la función mencionado en un comentario o en un printf cuenta
    # como llamada recursiva y la función se reporta como recursiva sin serlo.
    cuerpo_analizable = enmascarar_comentarios_y_literales(cuerpo)
    patron_llamada = re.compile(rf"\b{nombre_fn}\s*\(")
    llamadas = list(patron_llamada.finditer(cuerpo_analizable[cuerpo_analizable.find('{'):]))

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
    tiene_caso_base = bool(re.search(r"if\s*\([^)]+\)\s*\{?[^}]*return", cuerpo_analizable))

    # Detectar tipo de recursión
    total_calls = len(llamadas)
    # Recursión de cola (tail call): 'return fn(...);' sin operadores adicionales
    re_tail = re.compile(rf"return\s+{nombre_fn}\s*\([^;]+\);")
    es_tail = bool(re_tail.search(cuerpo_analizable))

    if total_calls > 1:
        tipo = "arbol"
    elif es_tail:
        tipo = "cola"
    else:
        tipo = "lineal"

    # Estimar tamaño de stack frame: 32 bytes base (dirección de retorno, rbp
    # guardado y alineación a 16) más un extra fijo si hay double/long o arreglos.
    frame_bytes = 32
    if "double" in cuerpo or "long" in cuerpo:
        frame_bytes += 32
    if "[" in cuerpo and "]" in cuerpo:
        frame_bytes += 64

    recomendaciones = []
    riesgo = "BAJO"

    if not tiene_caso_base:
        riesgo = "ALTO"
        recomendaciones.append("No se detectó un caso base claro ('if (...) return'). Esto provocará un desborde de pila (Stack Overflow).")

    if tipo == "arbol":
        riesgo = "MEDIO" if tiene_caso_base else "ALTO"
        recomendaciones.append("La recursión en árbol tiene complejidad exponencial $O(2^n)$. Considerá memoización o programación dinámica.")

    if tipo == "cola":
        recomendaciones.append("La función utiliza recursión de cola (Tail Recursion). Compiladores con -O2 la optimizarán a un lazo iterativo sin consumo de Stack.")
    elif es_recursiva and tipo == "lineal":
        recomendaciones.append("La función realiza operaciones tras la llamada recursiva (ej: n * f(n-1)). Transformarla a recursión de cola con un acumulador optimizará la pila.")

    diag = DiagnosticoRecursion(
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
    completar_limite_de_pila(diag)
    return diag


def completar_limite_de_pila(diag: DiagnosticoRecursion) -> None:
    """Cuántas llamadas anidadas entran en la pila antes del Stack Overflow (QoL #870)."""
    from sebastian.core.pila import limite_de_pila, marco_compilado, profundidad_maxima

    marco = marco_compilado(Path(diag.archivo), diag.funcion)
    if marco:
        diag.consumo_stack_por_frame_bytes = marco
        diag.marco_medido_por_gcc = True
    limite, origen = limite_de_pila()
    diag.limite_stack_bytes = limite
    diag.profundidad_maxima_estimada = profundidad_maxima(diag.consumo_stack_por_frame_bytes, limite)
    fuente_marco = "según gcc -fstack-usage" if diag.marco_medido_por_gcc else "estimados por el código"
    texto = (f"Con {diag.consumo_stack_por_frame_bytes} bytes por llamada ({fuente_marco}) y una pila de "
             f"{limite / 1048576:g} MiB ({origen}), '{diag.funcion}' admite unas "
             f"{diag.profundidad_maxima_estimada:,} llamadas anidadas antes del desborde de pila.")
    diag.recomendaciones = [r for r in diag.recomendaciones if not r.startswith("Con ") or "llamadas anidadas" not in r]
    if diag.profundidad_maxima:
        uso = 100.0 * diag.profundidad_maxima / max(1, diag.profundidad_maxima_estimada)
        texto += f" Esta ejecución llegó a {diag.profundidad_maxima:,} ({uso:.2g} % del máximo)."
        if uso >= 50 and diag.riesgo_overflow != "ALTO":
            diag.riesgo_overflow = "ALTO"
    diag.recomendaciones.append(texto)


def _compilar_con_daedalus(fuente_inst: Path, binario: Path) -> Optional[Any]:
    try:
        from daedalus.core.compiler import compilar_archivos
    except ImportError:
        return None  # sin el extra `ecosistema` se usa el camino propio
    return compilar_archivos([fuente_inst], binario_salida=binario, flags_adicionales=["-g", "-O0"])


def _errores_traducidos(archivo: Path) -> List[str]:
    """Los errores de `archivo` explicados por daedalus; vacío si no está o no los reconoce."""
    with tempfile.TemporaryDirectory() as tmp:
        res = _compilar_con_daedalus(archivo, Path(tmp) / "prog")
    if res is None:
        return []
    return [f"{archivo.name}:{d.linea}: {d.titulo}. {d.sugerencia}".strip()
            for d in res.diagnosticos if d.severidad == "error"]


def errores_de_compilacion(archivo: Path) -> Optional[List[str]]:
    """Los errores que impiden compilar `archivo`: vacío si compila, None si no hay gcc para saberlo."""
    gcc = shutil.which("gcc")
    if gcc is None:
        return None
    res = subprocess.run([gcc, "-std=c11", "-fsyntax-only", str(archivo)], capture_output=True, text=True)
    if res.returncode == 0:
        return []
    crudos = [linea for linea in res.stderr.splitlines() if "error:" in linea]
    return (_errores_traducidos(archivo) or crudos or res.stderr.splitlines())[:5]


def _sin_traza(diag: DiagnosticoRecursion, causa: str, motivo: str) -> DiagnosticoRecursion:
    diag.origen_medicion = "estatica"
    diag.causa_sin_medicion = causa
    diag.motivo_sin_medicion = motivo
    return diag


def _diagnostico_vacio(archivo: Path, funcion: str) -> DiagnosticoRecursion:
    return DiagnosticoRecursion(funcion=funcion, archivo=archivo, es_recursiva=False,
                                tipo_recursion="ninguna", tiene_caso_base=True)


def _describir_corte(codigo: int, error_tipo: Optional[str]) -> Optional[str]:
    """Por qué terminó mal el programa; None si terminó solo, con cualquier código propio."""
    if error_tipo == "TIMEOUT":
        return f"no terminó en {TIEMPO_LIMITE:.0f} s: ¿un lazo infinito, o está esperando entrada (--stdin)?"
    if error_tipo == "OOM":
        return "se quedó sin memoria"
    numero = -codigo if codigo < 0 else codigo - 128 if codigo > 128 else 0
    if not numero:
        return None
    try:
        nombre = signal.Signals(numero).name
    except ValueError:
        nombre = f"la señal {numero}"
    if nombre == "SIGSEGV":
        return "terminó con SIGSEGV: agotó la pila, o accedió a memoria inválida"
    return f"terminó con {nombre}"


def _ejecutar(binario: Path, args: Optional[List[str]], stdin_data: str) -> Tuple[str, Optional[str]]:
    """Corre el programa instrumentado: (lo que escribió, por qué se cortó)."""
    aislado = _try_import_nostromo()
    if aislado:
        res = aislado(binario, args=args, stdin_texto=stdin_data, timeout_segundos=TIEMPO_LIMITE, memoria_mb=64)
        return res.stdout, _describir_corte(res.codigo_retorno, res.error_tipo)
    try:
        run = subprocess.run([str(binario)] + (args or []), input=stdin_data, capture_output=True, text=True,
                             timeout=TIEMPO_LIMITE)
    except subprocess.TimeoutExpired as exc:
        salida = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return salida, _describir_corte(0, "TIMEOUT")
    return run.stdout, _describir_corte(run.returncode, None)


def _try_import_nostromo():
    try:
        from nostromo.core.sandbox import ejecutar_aislado
    except ImportError:
        return None  # sin el extra `ecosistema` se usa el camino propio
    return ejecutar_aislado


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

    errores = errores_de_compilacion(archivo_c)
    if errores:
        diag = _sin_traza(_diagnostico_vacio(archivo_c, funcion_target), "no_compila",
                          f"{archivo_c.name} no compila: corregí los errores y volvé a trazar.")
        diag.errores_compilacion = errores
        return diag

    contenido = archivo_c.read_text(encoding="utf-8")
    funciones = extraer_funciones_c(contenido)

    # Buscar la función objetivo
    fn_info = None
    for fn_name, cuerpo, l_start, _ in funciones:
        if fn_name == funcion_target:
            fn_info = (fn_name, cuerpo, l_start)
            break

    if funcion_target and not fn_info:
        disponibles = ", ".join(f[0] for f in funciones) or "ninguna"
        return _sin_traza(_diagnostico_vacio(archivo_c, funcion_target), "funcion_inexistente",
                          f"{archivo_c.name} no define la función '{funcion_target}'. Las que define: {disponibles}.")

    if not fn_info:
        # Sin --function: la primera función recursiva que no sea main
        for fn_name, cuerpo, l_start, _ in funciones:
            if fn_name != "main" and re.search(rf"\b{fn_name}\s*\(", cuerpo[cuerpo.find('{'):]):
                fn_info = (fn_name, cuerpo, l_start)
                break

    if not fn_info:
        return _sin_traza(_diagnostico_vacio(archivo_c, ""), "sin_recursion",
                          f"{archivo_c.name} no tiene funciones recursivas: indicá con --function cuál querés trazar.")

    nombre_fn, cuerpo_fn, l_start = fn_info
    diag_estatico = analizar_estatico_funcion(nombre_fn, cuerpo_fn, archivo_c, l_start)

    # Sin una medición real se informa el análisis estático tal cual, sin inventar un árbol: una
    # profundidad fabricada es indistinguible de una medida y lleva a decisiones equivocadas sobre
    # el riesgo de desborde de pila.
    if not any(f[0] == "main" for f in funciones):
        return _sin_traza(diag_estatico, "sin_main",
                          f"{archivo_c.name} no tiene main: no hay programa que ejecutar. Agregá uno que llame a "
                          f"{nombre_fn}() para ver sus llamadas.")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        binario = tmp_path / "prog_instrumentado"
        fuente_inst = tmp_path / "instrumentado.c"
        fuente_inst.write_text(_generar_codigo_instrumentado(contenido, nombre_fn), encoding="utf-8")

        problema = _compilar_instrumentado(fuente_inst, binario, archivo_c)
        if problema:
            return _sin_traza(diag_estatico, *problema)

        try:
            salida, corte = _ejecutar(binario, args_programa, stdin_data)
        except Exception as exc:
            return _sin_traza(diag_estatico, "fallo_ejecucion", f"No se pudo ejecutar el programa: {exc}")

    arbol, max_depth, total_calls, recortado = _parsear_trazas_instrumentadas(
        salida, nombre_fn, frame_bytes=diag_estatico.consumo_stack_por_frame_bytes
    )
    if not arbol:
        if corte and "no terminó" in corte:
            return _sin_traza(diag_estatico, "tiempo_agotado", f"El programa {corte}")
        if corte:
            return _sin_traza(diag_estatico, "fallo_ejecucion", f"El programa {corte} antes de llamar a {nombre_fn}().")
        return _sin_traza(diag_estatico, "sin_llamadas",
                          f"El programa terminó sin llamar a {nombre_fn}(): revisá que main llegue hasta esa "
                          "llamada, y si necesita datos pasalos con --stdin o como argumentos.")

    diag_estatico.origen_medicion = "dinamica"
    diag_estatico.arbol = arbol
    diag_estatico.arbol_recortado = recortado
    diag_estatico.ejecucion_cortada = corte
    diag_estatico.profundidad_maxima = max_depth
    diag_estatico.total_llamadas = total_calls
    diag_estatico.consumo_pico_stack_bytes = max_depth * diag_estatico.consumo_stack_por_frame_bytes
    completar_limite_de_pila(diag_estatico)
    return diag_estatico


def _compilar_instrumentado(fuente: Path, binario: Path, original: Path) -> Optional[Tuple[str, str]]:
    """Compila la versión instrumentada; (causa, motivo) si no se pudo."""
    res = _compilar_con_daedalus(fuente, binario)
    if res is not None:
        exito, salida = res.exito, res.stderr_crudo
    else:
        gcc = shutil.which("gcc")
        if gcc is None:
            return "sin_compilador", "Falta gcc: hace falta para ejecutar el programa y trazar sus llamadas."
        proc = subprocess.run([gcc, "-g", "-O0", "-std=c11", str(fuente), "-o", str(binario), "-lm"],
                              capture_output=True, text=True)
        exito, salida = proc.returncode == 0, proc.stderr
    if exito:
        return None
    faltan = sorted(set(re.findall(r"undefined reference to [`'\"](\w+)", salida)))
    if faltan:
        return "no_enlaza", (f"{original.name} compila, pero falta el código de {', '.join(faltan)}: sebastian "
                             "traza un solo archivo, con todo lo que usa definido en él.")
    primero = next((linea.split("error:", 1)[1].strip() for linea in salida.splitlines() if "error:" in linea), "")
    return "instrumentacion", (f"{original.name} compila, pero no la copia que sebastian le agrega el registro de "
                               f"llamadas{': ' + primero if primero else '.'}")


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
) -> Tuple[Optional[NodoLlamada], int, int, bool]:
    """Reconstruye el árbol de llamadas del log [SEB:ENTER:id:depth]: (raíz, profundidad, llamadas,
    recortado). Busca las marcas en todo el texto: el programa puede haber escrito antes en la misma
    línea, como un `printf("Ingresá n: ")` sin salto."""
    pila: List[Optional[NodoLlamada]] = []
    raiz: Optional[NodoLlamada] = None
    max_depth = 0
    total_calls = 0
    nodos = 0
    recortado = False

    for marca in _TRAZA.finditer(output):
        tipo, call_id, depth = marca.group(1), int(marca.group(2)), int(marca.group(3))

        if tipo == "ENTER":
            total_calls += 1
            max_depth = max(max_depth, depth)
            padre = pila[-1] if pila else None
            if depth > PROFUNDIDAD_ARBOL or nodos >= NODOS_ARBOL or (pila and padre is None):
                recortado = True
                pila.append(None)  # se cuenta, pero no se dibuja
                continue
            nodo = NodoLlamada(
                id=call_id,
                funcion=nombre_fn,
                argumentos=f"call_{call_id}",
                profundidad=depth,
                stack_bytes=depth * frame_bytes,
            )
            nodos += 1
            if not raiz:
                raiz = nodo
            if padre:
                padre.hijos.append(nodo)
            pila.append(nodo)

        elif pila:
            nodo_salida = pila.pop()
            if nodo_salida:
                nodo_salida.retorno = "ret"

    return raiz, max_depth, total_calls, recortado
