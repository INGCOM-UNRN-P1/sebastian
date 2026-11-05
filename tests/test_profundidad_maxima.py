"""Profundidad máxima antes del Stack Overflow (QoL #870)."""

import shutil
from pathlib import Path

import pytest

from sebastian.core.analyzer import extraer_funciones_c, analizar_estatico_funcion
from sebastian.core.pila import limite_de_pila, marco_compilado, profundidad_maxima

FUENTE = "long fact(long n)\n{\n    char buf[1000];\n    buf[0] = 0;\n    if (n <= 1) return 1;\n    return n * fact(n - 1) + buf[0];\n}\n"


def test_profundidad_maxima():
    assert profundidad_maxima(1024, 8 * 1024 * 1024) == 8192


def test_limite_de_pila():
    limite, origen = limite_de_pila()
    assert limite > 0 and origen


@pytest.mark.skipif(not shutil.which("gcc"), reason="requiere gcc")
def test_marco_de_gcc_y_recomendacion(tmp_path: Path):
    f = tmp_path / "r.c"
    f.write_text(FUENTE, encoding="utf-8")
    assert marco_compilado(f, "fact") >= 1000
    (nombre, cuerpo, linea, _), = extraer_funciones_c(FUENTE)
    diag = analizar_estatico_funcion(nombre, cuerpo, f, linea)
    assert diag.marco_medido_por_gcc and diag.profundidad_maxima_estimada == diag.limite_stack_bytes // diag.consumo_stack_por_frame_bytes
    assert "llamadas anidadas antes del desborde de pila" in diag.recomendaciones[-1]
