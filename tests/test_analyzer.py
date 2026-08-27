"""Tests unitarios para el analizador de recursión en SEBASTIAN."""

from pathlib import Path
import pytest
from sebastian.core.analyzer import (
    analizar_estatico_funcion,
    extraer_funciones_c,
    trazar_recursion_dinamica,
)
from sebastian.core.visualizer import generar_mermaid_diagram


def test_detectar_recursion_lineal_factorial(tmp_path):
    """Verifica la detección de recursión lineal en factorial."""
    fuente = tmp_path / "fact.c"
    fuente.write_text("""
    int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }
    """)
    funcs = extraer_funciones_c(fuente.read_text())
    assert len(funcs) == 1
    fn_name, cuerpo, l_start, _ = funcs[0]

    diag = analizar_estatico_funcion(fn_name, cuerpo, fuente, l_start)
    assert diag.es_recursiva is True
    assert diag.tipo_recursion == "lineal"
    assert diag.tiene_caso_base is True
    assert diag.riesgo_overflow == "BAJO"


def test_detectar_recursion_arbol_fibonacci(tmp_path):
    """Verifica detección de recursión múltiple/árbol en fibonacci."""
    fuente = tmp_path / "fib.c"
    fuente.write_text("""
    int fib(int n) {
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
    }
    """)
    funcs = extraer_funciones_c(fuente.read_text())
    diag = analizar_estatico_funcion("fib", funcs[0][1], fuente, funcs[0][2])
    assert diag.es_recursiva is True
    assert diag.tipo_recursion == "arbol"
    assert diag.riesgo_overflow == "MEDIO"


def test_detectar_recursion_sin_caso_base(tmp_path):
    """Verifica alerta de riesgo ALTO ante recursión sin caso base."""
    fuente = tmp_path / "infinita.c"
    fuente.write_text("""
    void loop_infinito(int x) {
        loop_infinito(x + 1);
    }
    """)
    funcs = extraer_funciones_c(fuente.read_text())
    diag = analizar_estatico_funcion("loop_infinito", funcs[0][1], fuente, funcs[0][2])
    assert diag.es_recursiva is True
    assert diag.tiene_caso_base is False
    assert diag.riesgo_overflow == "ALTO"


def test_trazado_dinamico_con_mermaid(tmp_path):
    """Verifica el trazado dinámico y la generación de diagramas Mermaid."""
    fuente = tmp_path / "prog.c"
    fuente.write_text("""
    #include <stdio.h>
    int fact(int n) {
        if (n <= 1) return 1;
        return n * fact(n - 1);
    }
    int main(void) {
        printf("Fact(3) = %d\\n", fact(3));
        return 0;
    }
    """)
    diag = trazar_recursion_dinamica(fuente, "fact")
    assert diag.es_recursiva is True
    assert diag.arbol is not None
    mermaid = generar_mermaid_diagram(diag.arbol)
    assert "graph TD" in mermaid
    assert "node" in mermaid
