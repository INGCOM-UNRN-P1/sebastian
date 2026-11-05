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
