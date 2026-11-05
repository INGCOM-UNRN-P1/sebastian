"""`sebastian trace` dice por qué no hay traza, en lugar de mostrar un resultado vacío."""

import json
import shutil

import pytest
from typer.testing import CliRunner

from sebastian.cli import app
from sebastian.core import analyzer
from sebastian.core.analyzer import PROFUNDIDAD_ARBOL, _parsear_trazas_instrumentadas, trazar_recursion_dinamica

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="requiere gcc")
runner = CliRunner()

RECURSIVA = "int f(int n)\n{\n    if (n == 0) return 0;\n    return 1 + f(n - 1);\n}\n"
MAIN = "int main(void)\n{\n    return f(3);\n}\n"


def _fuente(tmp_path, texto, nombre="prog.c"):
    ruta = tmp_path / nombre
    ruta.write_text(texto, encoding="utf-8")
    return ruta


@pytest.mark.parametrize("texto, causa, pista", [
    ("int f(int n)\n{\n    return n\n}\n" + MAIN, "no_compila", "no compila"),
    (RECURSIVA, "sin_main", "no tiene main"),
    (RECURSIVA + "int main(void)\n{\n    return 0;\n}\n", "sin_llamadas", "sin llamar a f()"),
    ("int g(int n);\nint f(int n)\n{\n    return n ? g(n) + f(n - 1) : 0;\n}\n" + MAIN, "no_enlaza", "g"),
    ("int g(int n)\n{\n    return n;\n}\nint main(void)\n{\n    return g(1);\n}\n", "sin_recursion", "--function"),
    ("int f(int n)\n{\n    while (1) { }\n    return f(n);\n}\n" + MAIN, "tiempo_agotado", "no terminó"),
])
def test_cada_falla_tiene_su_causa_y_sale_con_1(tmp_path, texto, causa, pista):
    fuente = _fuente(tmp_path, texto)
    diag = trazar_recursion_dinamica(fuente, "")
    assert diag.causa_sin_medicion == causa and pista in diag.motivo_sin_medicion
    res = runner.invoke(app, ["trace", str(fuente)])
    assert res.exit_code == 1 and pista in " ".join(res.stderr.split())
    res_json = runner.invoke(app, ["trace", str(fuente), "--json"])
    assert res_json.exit_code == 1 and json.loads(res_json.stdout)["causa_sin_medicion"] == causa


def test_no_compila_muestra_el_error_y_no_un_resultado_vacio(tmp_path):
    res = runner.invoke(app, ["trace", str(_fuente(tmp_path, "int f(int n)\n{\n    return n\n}\n" + MAIN))])
    assert "El código no compila" in res.stderr and "prog.c:3" in res.stderr
    assert "Riesgo" not in res.stdout and "Total de llamadas" not in res.stdout


def test_una_funcion_inexistente_no_se_reemplaza_por_otra(tmp_path):
    fuente = _fuente(tmp_path, RECURSIVA + MAIN)
    diag = trazar_recursion_dinamica(fuente, "otra")
    assert diag.causa_sin_medicion == "funcion_inexistente" and "f, main" in diag.motivo_sin_medicion


def test_mermaid_sin_arbol_explica_el_motivo(tmp_path):
    res = runner.invoke(app, ["trace", str(_fuente(tmp_path, RECURSIVA)), "--mermaid"])
    assert res.exit_code == 1 and "no tiene main" in res.stderr


def test_la_recursion_infinita_se_informa_sin_romper_la_herramienta(tmp_path):
    fuente = _fuente(tmp_path, "int f(int n)\n{\n    return 1 + f(n + 1);\n}\nint main(void)\n{\n    return f(0) & 1;\n}\n")
    res = runner.invoke(app, ["trace", str(fuente), "--json"])
    assert res.exit_code == 0
    datos = json.loads(res.stdout)
    assert datos["profundidad_maxima"] > PROFUNDIDAD_ARBOL and datos["arbol_recortado"] is True
    assert datos["ejecucion_cortada"]
    res_texto = runner.invoke(app, ["trace", str(fuente)])
    assert res_texto.exit_code == 0 and "La traza llega hasta ahí" in " ".join(res_texto.stderr.split())


def test_cuenta_las_llamadas_aunque_el_programa_escriba_sin_salto(tmp_path):
    fuente = _fuente(tmp_path, "#include <stdio.h>\n" + RECURSIVA +
                     'int main(void)\n{\n    printf("Ingresá n: ");\n    printf("%d\\n", f(2));\n    return 0;\n}\n')
    diag = trazar_recursion_dinamica(fuente, "f")
    assert (diag.total_llamadas, diag.profundidad_maxima) == (3, 3)


def test_el_arbol_se_recorta_y_los_totales_no():
    marcas = "".join(f"[SEB:ENTER:{i}:{i}:f]\n" for i in range(1, PROFUNDIDAD_ARBOL + 11))
    raiz, profundidad, llamadas, recortado = _parsear_trazas_instrumentadas(marcas, "f")
    assert (profundidad, llamadas, recortado) == (PROFUNDIDAD_ARBOL + 10, PROFUNDIDAD_ARBOL + 10, True)
    niveles = 0
    while raiz:
        niveles, raiz = niveles + 1, raiz.hijos[0] if raiz.hijos else None
    assert niveles == PROFUNDIDAD_ARBOL


def test_check_avisa_que_no_compila_y_mantiene_el_analisis(tmp_path):
    res = runner.invoke(app, ["check", str(_fuente(tmp_path, "int f(int n)\n{\n    return f(n)\n}\n" + MAIN))])
    assert res.exit_code == 0 and "no compila" in res.stderr and "Análisis de Recursión" in res.stdout


def test_sin_gcc_no_afirma_que_el_codigo_no_compila(tmp_path, monkeypatch):
    monkeypatch.setattr(analyzer.shutil, "which", lambda _: None)
    assert analyzer.errores_de_compilacion(_fuente(tmp_path, "esto no es C")) is None


def test_sin_gcc_dice_que_falta(tmp_path, monkeypatch):
    monkeypatch.setattr(analyzer.shutil, "which", lambda _: None)
    monkeypatch.setattr(analyzer, "_compilar_con_daedalus", lambda *_: None)
    diag = trazar_recursion_dinamica(_fuente(tmp_path, RECURSIVA + MAIN), "f")
    assert diag.causa_sin_medicion == "sin_compilador" and "gcc" in diag.motivo_sin_medicion


def _proyecto(tmp_path):
    """src/ + include/, con main en otro archivo: la forma de la actividad de ejemplo del corpus."""
    (tmp_path / "include").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "include" / "cuenta.h").write_text("int cuenta(int n);\n", encoding="utf-8")
    fuente = _fuente(tmp_path / "src", '#include "cuenta.h"\nint cuenta(int n)\n{\n    return n ? 1 + cuenta(n - 1) : 0;\n}\n',
                     "cuenta.c")
    principal = _fuente(tmp_path / "src", '#include "cuenta.h"\nint main(void)\n{\n    return cuenta(3);\n}\n', "main.c")
    return fuente, principal


def test_un_header_en_include_no_se_informa_como_error_de_compilacion(tmp_path):
    fuente, _ = _proyecto(tmp_path)
    assert analyzer.errores_de_compilacion(fuente) == []
    diag = trazar_recursion_dinamica(fuente, "")
    assert diag.causa_sin_medicion == "sin_main"


def test_sin_main_propone_el_archivo_que_lo_tiene(tmp_path):
    fuente, principal = _proyecto(tmp_path)
    assert f"--source {principal}" in trazar_recursion_dinamica(fuente, "").motivo_sin_medicion


def test_traza_un_programa_de_varios_archivos(tmp_path):
    fuente, principal = _proyecto(tmp_path)
    res = runner.invoke(app, ["trace", str(fuente), "--source", str(principal), "--json"])
    assert res.exit_code == 0 and json.loads(res.stdout)["total_llamadas"] == 4


def test_include_explicito_para_una_carpeta_que_no_se_detecta(tmp_path):
    (tmp_path / "cabeceras").mkdir()
    (tmp_path / "cabeceras" / "v.h").write_text("#define V 3\n", encoding="utf-8")
    fuente = _fuente(tmp_path, '#include "v.h"\n' + RECURSIVA + "int main(void)\n{\n    return f(V);\n}\n")
    assert trazar_recursion_dinamica(fuente, "").causa_sin_medicion == "no_compila"
    res = runner.invoke(app, ["trace", str(fuente), "-I", str(tmp_path / "cabeceras"), "--json"])
    assert res.exit_code == 0 and json.loads(res.stdout)["total_llamadas"] == 4


def test_source_inexistente_sale_con_2(tmp_path):
    res = runner.invoke(app, ["trace", str(_fuente(tmp_path, RECURSIVA)), "--source", str(tmp_path / "no.c")])
    assert res.exit_code == 2


def test_falta_de_codigo_propone_el_archivo_vecino_que_lo_define(tmp_path):
    fuente = _fuente(tmp_path, "int g(int n);\nint f(int n)\n{\n    return n ? g(n) + f(n - 1) : 0;\n}\n" + MAIN)
    vecino = _fuente(tmp_path, "int g(int n)\n{\n    return n;\n}\n", "otro.c")
    diag = trazar_recursion_dinamica(fuente, "")
    assert diag.causa_sin_medicion == "no_enlaza" and f"--source {vecino}" in diag.motivo_sin_medicion


def test_definicion_repetida_entre_archivos(tmp_path):
    fuente = _fuente(tmp_path, RECURSIVA + MAIN)
    otra = _fuente(tmp_path, "int main(void)\n{\n    return 0;\n}\n", "otro.c")
    diag = trazar_recursion_dinamica(fuente, "", otras_fuentes=[otra])
    assert diag.causa_sin_medicion == "no_enlaza" and "main" in diag.motivo_sin_medicion


def test_un_error_en_otro_archivo_se_atribuye_a_ese_archivo(tmp_path):
    fuente = _fuente(tmp_path, RECURSIVA)
    otra = _fuente(tmp_path, "int main(void)\n{\n    return 0\n}\n", "otro.c")
    diag = trazar_recursion_dinamica(fuente, "", otras_fuentes=[otra])
    assert diag.causa_sin_medicion == "no_compila" and "otro.c no compila" in diag.motivo_sin_medicion


@pytest.mark.parametrize("firma", [
    "const char *salta(const char *s)",
    "char* salta(const char *s)",
    "static const char *\nsalta(const char *s)",
])
def test_una_funcion_que_devuelve_puntero_se_encuentra(tmp_path, firma):
    fuente = _fuente(tmp_path, f"{firma}\n{{\n    return *s == ' ' ? salta(s + 1) : (char *)s;\n}}\n"
                               'int main(void)\n{\n    return *salta(" a");\n}\n')
    assert trazar_recursion_dinamica(fuente, "salta").total_llamadas == 2


def test_un_parametro_puntero_a_funcion_no_esconde_la_funcion(tmp_path):
    fuente = _fuente(tmp_path, "int ap(int (*g)(int), int n)\n{\n    return n ? ap(g, n - 1) : g(n);\n}\n"
                               "int id(int n)\n{\n    return n;\n}\n"
                               "int main(void)\n{\n    return ap(id, 2);\n}\n")
    assert trazar_recursion_dinamica(fuente, "ap").total_llamadas == 3


MUTUA = ("int impar(int n);\nint par(int n)\n{\n    if (n == 0) return 1;\n    return impar(n - 1);\n}\n"
         "int impar(int n)\n{\n    return par(n - 1);\n}\nint main(void)\n{\n    return par(2);\n}\n")


def test_la_recursion_mutua_se_traza_con_las_dos_funciones(tmp_path):
    diag = trazar_recursion_dinamica(_fuente(tmp_path, MUTUA), "")
    assert diag.funcion == "par" and diag.tipo_recursion == "mutua" and diag.tiene_caso_base
    assert diag.total_llamadas == 3 and diag.arbol.hijos[0].funcion == "impar"


def test_el_analisis_estatico_ve_la_recursion_mutua(tmp_path):
    res = runner.invoke(app, ["check", str(_fuente(tmp_path, MUTUA)), "--json"])
    por_nombre = {r["funcion"]: r for r in json.loads(res.stdout)}
    assert por_nombre["impar"]["tipo_recursion"] == "mutua" and por_nombre["impar"]["tiene_caso_base"]
    assert por_nombre["main"]["es_recursiva"] is False


def test_sin_llamadas_cuenta_el_codigo_y_lo_que_escribio_el_programa(tmp_path):
    fuente = _fuente(tmp_path, '#include <stdio.h>\n' + RECURSIVA +
                     'int main(int c, char **v)\n{\n    if (c < 2) { fputs("uso: prog n\\n", stderr); return 1; }\n'
                     "    return f(c);\n}\n")
    motivo = trazar_recursion_dinamica(fuente, "").motivo_sin_medicion
    assert "con código 1" in motivo and "uso: prog n" in motivo


def test_report_avisa_que_no_compila(tmp_path):
    fuente = _fuente(tmp_path, "int f(int n)\n{\n    return n\n}\n")
    res = runner.invoke(app, ["report", str(fuente)])
    assert "El código no compila" in res.stderr
    assert "status=fail" in res.stdout and "no compila" in res.stdout


def test_un_error_sin_traduccion_muestra_el_mensaje_del_compilador_una_vez(tmp_path):
    fuente = tmp_path / "raro.c"
    fuente.write_bytes(b"\xff\xfe int main(void) { return 0; }\n")
    errores = analyzer.errores_de_compilacion(fuente)
    assert errores and len(errores) == len(set(errores))
    assert not any("Diagnóstico del compilador" in error for error in errores)
