"""Regresión de SEBASTIAN-D0302/D0303: no inventar recursión ni mediciones."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sebastian.core.analyzer import (
    analizar_estatico_funcion,
    extraer_funciones_c,
    trazar_recursion_dinamica,
)

FUENTE = """#include <stdio.h>
int no_recursiva(int n) {
    /* ojo: no_recursiva(n-1) aparece solo en este comentario */
    printf("no_recursiva(%d) es el nombre\\n", n);
    return n * 2;
}
int factorial(int n) {
    if (n <= 1) { return 1; }
    return n * factorial(n - 1);
}
"""


@pytest.fixture
def archivo(tmp_path):
    ruta = tmp_path / "rec.c"
    ruta.write_text(FUENTE, encoding="utf-8")
    return ruta


def _diagnosticos(archivo):
    contenido = archivo.read_text(encoding="utf-8")
    return {
        nombre: analizar_estatico_funcion(nombre, cuerpo, archivo, ini)
        for nombre, cuerpo, ini, _ in extraer_funciones_c(contenido)
    }


def test_mencion_en_comentario_o_string_no_es_recursion(archivo):
    """SEBASTIAN-D0302."""
    assert _diagnosticos(archivo)["no_recursiva"].es_recursiva is False


def test_la_recursion_real_se_sigue_detectando(archivo):
    diagnostico = _diagnosticos(archivo)["factorial"]
    assert diagnostico.es_recursiva is True
    assert diagnostico.tiene_caso_base is True


def test_sin_instrumentacion_no_se_fabrica_un_arbol(archivo):
    """SEBASTIAN-D0303: antes devolvía profundidad 2 y 2 llamadas inventadas."""
    with patch("sebastian.core.analyzer.shutil.which", return_value=None), \
         patch("sebastian.core.analyzer._compilar_con_daedalus", return_value=False):
        diagnostico = trazar_recursion_dinamica(archivo, "factorial")

    assert diagnostico.origen_medicion == "estatica"
    assert diagnostico.motivo_sin_medicion
    assert diagnostico.arbol is None
    assert diagnostico.profundidad_maxima == 0
    assert diagnostico.total_llamadas == 0


def test_la_medicion_dinamica_se_marca_como_tal(tmp_path):
    ruta = tmp_path / "fact.c"
    ruta.write_text(
        "#include <stdio.h>\n"
        "int factorial(int n) {\n    if (n <= 1) { return 1; }\n    return n * factorial(n - 1);\n}\n"
        "int main(void) { printf(\"%d\\n\", factorial(5)); return 0; }\n",
        encoding="utf-8",
    )
    diagnostico = trazar_recursion_dinamica(ruta, "factorial")
    if diagnostico.origen_medicion == "estatica":
        pytest.skip(f"sin toolchain para instrumentar: {diagnostico.motivo_sin_medicion}")
    assert diagnostico.profundidad_maxima == 5
    assert diagnostico.motivo_sin_medicion is None
