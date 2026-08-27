"""Tests adicionales para maximizar la cobertura en SEBASTIAN."""

import json
from pathlib import Path
from typer.testing import CliRunner
import sebastian.cli
from sebastian.cli import app
from sebastian.core.analyzer import (
    analizar_estatico_funcion,
    extraer_funciones_c,
    trazar_recursion_dinamica,
    _parsear_trazas_instrumentadas,
    _generar_codigo_instrumentado,
)
from sebastian.core.models import NodoLlamada, DiagnosticoRecursion
from sebastian.core.visualizer import construir_rich_tree, generar_mermaid_diagram

runner = CliRunner()


def test_visualizer_rich_y_mermaid():
    n_hijo1 = NodoLlamada(id=2, funcion="fib", argumentos="1", profundidad=1, retorno="1", stack_bytes=32)
    n_hijo2 = NodoLlamada(id=3, funcion="fib", argumentos="0", profundidad=1, retorno="0", stack_bytes=32)
    n_raiz = NodoLlamada(id=1, funcion="fib", argumentos="2", profundidad=0, retorno="1", stack_bytes=32, hijos=[n_hijo1, n_hijo2])

    tree = construir_rich_tree(n_raiz)
    assert tree is not None

    mermaid = generar_mermaid_diagram(n_raiz)
    assert "graph TD" in mermaid
    assert "node1" in mermaid
    assert "node2" in mermaid


def test_parsear_trazas_instrumentadas():
    log = (
        "[SEB:ENTER:1:1:factorial]\n"
        "[SEB:ENTER:2:2:factorial]\n"
        "[SEB:EXIT:2:2]\n"
        "[SEB:EXIT:1:1]\n"
    )
    raiz, max_depth, total = _parsear_trazas_instrumentadas(log, "factorial")
    assert raiz is not None
    assert max_depth == 2
    assert total == 2
    assert len(raiz.hijos) == 1

    # Empty log
    r_empty, d_empty, t_empty = _parsear_trazas_instrumentadas("", "factorial")
    assert r_empty is None


def test_cli_trace_rich_and_mermaid(tmp_path):
    fuente = tmp_path / "fact.c"
    fuente.write_text("""
    #include <stdio.h>
    int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }
    int main(void) {
        printf("%d\\n", factorial(3));
        return 0;
    }
    """)

    # Trace default tree
    res_tree = runner.invoke(app, ["trace", str(fuente)])
    assert res_tree.exit_code == 0
    assert "Análisis de Recursión" in res_tree.stdout

    # Trace mermaid
    res_m = runner.invoke(app, ["trace", str(fuente), "--mermaid"])
    assert res_m.exit_code == 0


def test_cli_analyze_rich_table(tmp_path):
    fuente = tmp_path / "funcs.c"
    fuente.write_text("""
    int rec(int n) { if (n <= 0) return 0; return rec(n-1); }
    int no_rec(int a) { return a + 1; }
    """)

    res = runner.invoke(app, ["analyze", str(fuente)])
    assert res.exit_code == 0
    assert "Análisis de Recursión" in res.stdout


def test_cli_file_not_found():
    res1 = runner.invoke(app, ["trace", "/no/existe.c"])
    assert res1.exit_code == 2

    res2 = runner.invoke(app, ["analyze", "/no/existe.c"])
    assert res2.exit_code == 2


def test_cli_main_block(monkeypatch):
    monkeypatch.setattr("sys.argv", ["sebastian", "--version"])
    try:
        sebastian.cli.main()
    except SystemExit as e:
        assert e.code == 0
