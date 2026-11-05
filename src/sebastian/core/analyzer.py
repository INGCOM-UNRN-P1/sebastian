"""Motor de análisis estático y trazado dinámico de recursión en SEBASTIAN."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

from sebastian.core.masking import enmascarar_comentarios_y_literales
from sebastian.core.models import DiagnosticoRecursion, NodoLlamada
from sebastian.core.pila import directorios_include


# El árbol se recorre con recursión y se dibuja en la terminal: una recursión infinita llega a
# cientos de miles de marcos. Los contadores siguen midiendo todo; lo que se recorta es el dibujo.
PROFUNDIDAD_ARBOL = 50
NODOS_ARBOL = 2000
TIEMPO_LIMITE = 3.0
_TRAZA = re.compile(r"\[SEB:(ENTER|EXIT):(\d+):(\d+)(?::([^\]\n]*))?\]")
# Los parámetros admiten un nivel de paréntesis, el de un puntero a función: `int (*cmp)(int, int)`.
_PARAMETROS = r"\((?:[^()]|\([^()]*\))*\)"
_TITULO_SIN_TRADUCIR = "Diagnóstico del compilador"


def extraer_funciones_c(contenido: str) -> List[Tuple[str, str, int, int]]:
    """Extrae las funciones definidas en un archivo C: (nombre, cuerpo, linea_inicio, linea_fin)."""
    # Regex para cabecera de función
    re_fn = re.compile(
        rf"^[ \t]*(?:[a-zA-Z_]\w*[\s*]+)+([a-zA-Z_]\w*)\s*{_PARAMETROS}\s*\{{",
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


def _llamadas_entre_funciones(funciones: Sequence[Tuple[str, str, int, int]]) -> Dict[str, Set[str]]:
    nombres = {f[0] for f in funciones}
    grafo: Dict[str, Set[str]] = {}
    for nombre, cuerpo, _, _ in funciones:
        limpio = enmascarar_comentarios_y_literales(cuerpo)
        grafo[nombre] = (set(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", limpio[limpio.find("{"):])) & nombres) - {nombre}
    return grafo


def recursion_mutua(funciones: Sequence[Tuple[str, str, int, int]]) -> Dict[str, List[str]]:
    """Para cada función que se llama a sí misma a través de otras, esas otras (f → g → f)."""
    grafo = _llamadas_entre_funciones(funciones)

    def alcanzables(origen: str) -> Set[str]:
        vistos: Set[str] = set()
        pendientes = list(grafo[origen])
        while pendientes:
            actual = pendientes.pop()
            if actual not in vistos:
                vistos.add(actual)
                pendientes.extend(grafo[actual])
        return vistos

    alcance = {nombre: alcanzables(nombre) for nombre in grafo}
    ciclos = {nombre: sorted(otra for otra in alcance[nombre] if otra != nombre and nombre in alcance[otra])
              for nombre in grafo}
    return {nombre: otras for nombre, otras in ciclos.items() if otras}


def analizar_archivo(contenido: str, archivo: Path, includes: Sequence[Path] = ()) -> List[DiagnosticoRecursion]:
    """El análisis estático de cada función del archivo, con la recursión mutua incluida."""
    funciones = extraer_funciones_c(contenido)
    mutuas = recursion_mutua(funciones)
    cuerpos = {f[0]: f[1] for f in funciones}
    return [
        analizar_estatico_funcion(nombre, cuerpo, archivo, linea, includes=includes,
                                  companeras={otra: cuerpos[otra] for otra in mutuas.get(nombre, [])})
        for nombre, cuerpo, linea, _ in funciones
    ]


def analizar_estatico_funcion(
    nombre_fn: str,
    cuerpo: str,
    archivo: Path,
    linea_inicio: int = 1,
    includes: Sequence[Path] = (),
    companeras: Optional[Dict[str, str]] = None,
) -> DiagnosticoRecursion:
    """Realiza un análisis estático de una función para detectar patrones recursivos.

    `companeras`: las funciones con las que forma recursión mutua, con sus cuerpos; el caso base
    puede estar en cualquiera de ellas.
    """
    companeras = companeras or {}
    # Los comentarios y literales se blanquean antes de buscar: sin esto, el
    # nombre de la función mencionado en un comentario o en un printf cuenta
    # como llamada recursiva y la función se reporta como recursiva sin serlo.
    cuerpo_analizable = enmascarar_comentarios_y_literales(cuerpo)
    nombres = "|".join(re.escape(nombre) for nombre in [nombre_fn, *companeras])
    patron_llamada = re.compile(rf"\b(?:{nombres})\s*\(")
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

    # Detectar caso base (presencia de if con return antes de la llamada recursiva,
    # o un operador ternario, que elige entre la llamada y otro valor).
    tiene_caso_base = any(
        re.search(r"if\s*\([^)]+\)\s*\{?[^}]*return|\?[^;]*:", enmascarar_comentarios_y_literales(texto))
        for texto in [cuerpo, *companeras.values()]
    )

    # Detectar tipo de recursión
    total_calls = len(llamadas)
    # Recursión de cola (tail call): 'return fn(...);' sin operadores adicionales
    re_tail = re.compile(rf"return\s+(?:{nombres})\s*\([^;]+\);")
    es_tail = bool(re_tail.search(cuerpo_analizable))

    if companeras:
        tipo = "mutua"
    elif total_calls > 1:
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

    if tipo == "mutua":
        recomendaciones.append(f"Recursión mutua con {', '.join(companeras)}: se llaman entre sí, y el caso base "
                               "puede estar en cualquiera de ellas.")
    elif tipo == "cola":
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
    completar_limite_de_pila(diag, includes)
    return diag


def completar_limite_de_pila(diag: DiagnosticoRecursion, includes: Sequence[Path] = ()) -> None:
    """Cuántas llamadas anidadas entran en la pila antes del Stack Overflow (QoL #870)."""
    from sebastian.core.pila import limite_de_pila, marco_compilado, profundidad_maxima

    marco = marco_compilado(Path(diag.archivo), diag.funcion, includes)
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


def _flags_include(includes: Sequence[Path]) -> List[str]:
    return [f"-I{carpeta}" for carpeta in includes]


def _compilar_con_daedalus(fuentes: Sequence[Path], binario: Path, includes: Sequence[Path] = ()) -> Optional[Any]:
    try:
        from daedalus.core.compiler import compilar_archivos
    except ImportError:
        return None  # sin el extra `ecosistema` se usa el camino propio
    return compilar_archivos(list(fuentes), binario_salida=binario,
                             flags_adicionales=["-g", "-O0", *_flags_include(includes)])


def _errores_traducidos(archivo: Path, includes: Sequence[Path]) -> List[str]:
    """Los errores de `archivo` explicados por daedalus; vacío si no está o no los reconoce."""
    with tempfile.TemporaryDirectory() as tmp:
        res = _compilar_con_daedalus([archivo], Path(tmp) / "prog", includes)
    if res is None:
        return []
    errores = [f"{archivo.name}:{d.linea}: {d.mensaje_original}" if d.titulo == _TITULO_SIN_TRADUCIR
               else f"{archivo.name}:{d.linea}: {d.titulo}. {d.sugerencia}".strip()
               for d in res.diagnosticos if d.severidad == "error"]
    return list(dict.fromkeys(errores))


def errores_de_compilacion(archivo: Path, includes: Sequence[Path] = ()) -> Optional[List[str]]:
    """Los errores que impiden compilar `archivo`: vacío si compila, None si no hay gcc para saberlo."""
    carpetas = directorios_include(archivo, includes)
    gcc = shutil.which("gcc")
    if gcc is None:
        return None
    res = subprocess.run([gcc, "-std=c11", "-fsyntax-only", *_flags_include(carpetas), str(archivo)],
                         capture_output=True, text=True, errors="replace")
    if res.returncode == 0:
        return []
    crudos = [linea for linea in res.stderr.splitlines() if "error:" in linea]
    return (_errores_traducidos(archivo, carpetas) or crudos or res.stderr.splitlines())[:5]


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


class _Ejecucion(NamedTuple):
    salida: str
    corte: Optional[str]  # por qué se cortó; None si terminó solo
    codigo: int
    errores: str


def _ejecutar(binario: Path, args: Optional[List[str]], stdin_data: str) -> _Ejecucion:
    """Corre el programa instrumentado."""
    aislado = _try_import_nostromo()
    if aislado:
        res = aislado(binario, args=args, stdin_texto=stdin_data, timeout_segundos=TIEMPO_LIMITE, memoria_mb=64)
        return _Ejecucion(res.stdout, _describir_corte(res.codigo_retorno, res.error_tipo), res.codigo_retorno,
                          res.stderr)
    try:
        run = subprocess.run([str(binario)] + (args or []), input=stdin_data, capture_output=True, text=True,
                             errors="replace", timeout=TIEMPO_LIMITE)
    except subprocess.TimeoutExpired as exc:
        salida = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        return _Ejecucion(salida, _describir_corte(0, "TIMEOUT"), 0, "")
    return _Ejecucion(run.stdout, _describir_corte(run.returncode, None), run.returncode, run.stderr)


def _try_import_nostromo():
    try:
        from nostromo.core.sandbox import ejecutar_aislado
    except ImportError:
        return None  # sin el extra `ecosistema` se usa el camino propio
    return ejecutar_aislado


def _definen(nombres: Sequence[str], archivo: Path) -> List[Path]:
    """Los otros .c de la carpeta de `archivo` que definen alguna de esas funciones."""
    buscados = set(nombres)
    return [vecino for vecino in sorted(archivo.parent.glob("*.c")) if vecino != archivo and buscados & {
        f[0] for f in extraer_funciones_c(vecino.read_text(encoding="utf-8", errors="replace"))}]


def _pista_source(rutas: Sequence[Path]) -> str:
    return " ".join(f"--source {ruta}" for ruta in rutas)


def _motivo_sin_llamadas(nombre_fn: str, ejecucion: _Ejecucion) -> str:
    texto = _TRAZA.sub("", ejecucion.errores or ejecucion.salida)
    ultima = next((linea.strip() for linea in reversed(texto.splitlines()) if linea.strip()), "")
    codigo = f" con código {ejecucion.codigo}" if ejecucion.codigo else ""
    dijo = f" (lo último que escribió: «{ultima[:120]}»)" if ultima else ""
    return (f"El programa terminó{codigo} sin llamar a {nombre_fn}(){dijo}: revisá que main llegue hasta esa "
            "llamada, y si necesita datos pasalos con --stdin o como argumentos.")


def trazar_recursion_dinamica(
    archivo_c: Path,
    funcion_target: str,
    args_programa: Optional[List[str]] = None,
    stdin_data: str = "",
    includes: Sequence[Path] = (),
    otras_fuentes: Sequence[Path] = (),
) -> DiagnosticoRecursion:
    """Instrumenta el código para registrar en tiempo de ejecución cada invocación recursiva.

    `otras_fuentes`: los demás .c del programa (el que tiene main, por ejemplo), que se compilan sin
    instrumentar. `includes`: carpetas de headers, además del `include/` que se detecta solo.
    """
    archivo_c = Path(archivo_c)
    if not archivo_c.is_file():
        raise FileNotFoundError(f"No se encontró el archivo: {archivo_c}")

    otras_fuentes = [Path(otra) for otra in otras_fuentes]
    for fuente in [archivo_c, *otras_fuentes]:
        errores = errores_de_compilacion(fuente, includes)
        if errores:
            diag = _sin_traza(_diagnostico_vacio(archivo_c, funcion_target), "no_compila",
                              f"{fuente.name} no compila: corregí los errores y volvé a trazar.")
            diag.errores_compilacion = errores
            return diag

    contenido = archivo_c.read_text(encoding="utf-8")
    funciones = extraer_funciones_c(contenido)
    mutuas = recursion_mutua(funciones)

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
            limpio = enmascarar_comentarios_y_literales(cuerpo)
            if fn_name != "main" and (fn_name in mutuas or re.search(rf"\b{fn_name}\s*\(", limpio[limpio.find('{'):])):
                fn_info = (fn_name, cuerpo, l_start)
                break

    if not fn_info:
        return _sin_traza(_diagnostico_vacio(archivo_c, ""), "sin_recursion",
                          f"No encontré funciones recursivas en {archivo_c.name}: indicá con --function cuál querés "
                          "trazar.")

    nombre_fn, cuerpo_fn, l_start = fn_info
    cuerpos = {f[0]: f[1] for f in funciones}
    companeras = {otra: cuerpos[otra] for otra in mutuas.get(nombre_fn, [])}
    diag_estatico = analizar_estatico_funcion(nombre_fn, cuerpo_fn, archivo_c, l_start, includes=includes,
                                              companeras=companeras)

    # Sin una medición real se informa el análisis estático tal cual, sin inventar un árbol: una
    # profundidad fabricada es indistinguible de una medida y lleva a decisiones equivocadas sobre
    # el riesgo de desborde de pila.
    tiene_main = any(f[0] == "main" for f in funciones) or any(
        f[0] == "main" for otra in otras_fuentes
        for f in extraer_funciones_c(otra.read_text(encoding="utf-8", errors="replace")))
    if not tiene_main:
        con_main = _definen(["main"], archivo_c)
        pista = (f"Sumá el que lo tiene con {_pista_source(con_main[:1])}." if con_main else
                 f"Agregá uno que llame a {nombre_fn}(), o pasá el archivo que lo tiene con --source.")
        return _sin_traza(diag_estatico, "sin_main",
                          f"{archivo_c.name} no tiene main: no hay programa que ejecutar. {pista}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        binario = tmp_path / "prog_instrumentado"
        fuente_inst = tmp_path / "instrumentado.c"
        fuente_inst.write_text(_generar_codigo_instrumentado(contenido, nombre_fn, list(companeras)),
                               encoding="utf-8")

        # La copia vive en otra carpeta: sus #include "..." se buscan en la del original.
        carpetas = [archivo_c.resolve().parent, *directorios_include(archivo_c, includes)]
        problema = _compilar_instrumentado([fuente_inst, *otras_fuentes], binario, archivo_c, carpetas)
        if problema:
            return _sin_traza(diag_estatico, *problema)

        try:
            ejecucion = _ejecutar(binario, args_programa, stdin_data)
        except Exception as exc:
            return _sin_traza(diag_estatico, "fallo_ejecucion", f"No se pudo ejecutar el programa: {exc}")

    arbol, max_depth, total_calls, recortado = _parsear_trazas_instrumentadas(
        ejecucion.salida, nombre_fn, frame_bytes=diag_estatico.consumo_stack_por_frame_bytes
    )
    corte = ejecucion.corte
    if not arbol:
        if corte and "no terminó" in corte:
            return _sin_traza(diag_estatico, "tiempo_agotado", f"El programa {corte}")
        if corte:
            return _sin_traza(diag_estatico, "fallo_ejecucion", f"El programa {corte} antes de llamar a {nombre_fn}().")
        return _sin_traza(diag_estatico, "sin_llamadas", _motivo_sin_llamadas(nombre_fn, ejecucion))

    diag_estatico.origen_medicion = "dinamica"
    diag_estatico.arbol = arbol
    diag_estatico.arbol_recortado = recortado
    diag_estatico.ejecucion_cortada = corte
    diag_estatico.profundidad_maxima = max_depth
    diag_estatico.total_llamadas = total_calls
    diag_estatico.consumo_pico_stack_bytes = max_depth * diag_estatico.consumo_stack_por_frame_bytes
    completar_limite_de_pila(diag_estatico, includes)
    return diag_estatico


def _compilar_instrumentado(fuentes: Sequence[Path], binario: Path, original: Path,
                            includes: Sequence[Path] = ()) -> Optional[Tuple[str, str]]:
    """Compila la versión instrumentada; (causa, motivo) si no se pudo."""
    res = _compilar_con_daedalus(fuentes, binario, includes)
    if res is not None:
        exito, salida = res.exito, res.stderr_crudo
    else:
        gcc = shutil.which("gcc")
        if gcc is None:
            return "sin_compilador", "Falta gcc: hace falta para ejecutar el programa y trazar sus llamadas."
        proc = subprocess.run([gcc, "-g", "-O0", "-std=c11", *_flags_include(includes), *map(str, fuentes),
                               "-o", str(binario), "-lm"],
                              capture_output=True, text=True)
        exito, salida = proc.returncode == 0, proc.stderr
    if exito:
        return None
    faltan = sorted(set(re.findall(r"undefined reference to [`'\"](\w+)", salida)))
    if faltan:
        vecinos = _definen(faltan, original)
        pista = f"sumalo con {_pista_source(vecinos)}" if vecinos else "pasá el archivo que lo define con --source"
        return "no_enlaza", f"{original.name} compila, pero falta el código de {', '.join(faltan)}: {pista}."
    repetidas = sorted(set(re.findall(r"multiple definition of [`'\"](\w+)", salida)))
    if repetidas:
        return "no_enlaza", (f"{', '.join(repetidas)} está definido en más de un archivo: dejá un solo --source "
                             "con esa definición.")
    primero = next((linea.split("error:", 1)[1].strip() for linea in salida.splitlines() if "error:" in linea), "")
    return "instrumentacion", (f"{original.name} compila, pero no la copia que sebastian le agrega el registro de "
                               f"llamadas{': ' + primero if primero else '.'}")


def _generar_codigo_instrumentado(codigo_original: str, funcion_target: str, otras: Sequence[str] = ()) -> str:
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
    # Insertar __SEB_ENTER justo después de la primera llave de cada función
    codigo_mod = codigo_original
    for nombre in [funcion_target, *otras]:
        patron = rf"(\b{nombre}\s*{_PARAMETROS}\s*\{{)"
        codigo_mod = re.sub(patron, rf'\1\n    __SEB_ENTER("{nombre}");', codigo_mod, count=1)
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
                funcion=marca.group(4) or nombre_fn,
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
