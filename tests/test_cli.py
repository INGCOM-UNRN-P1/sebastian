"""Tests de integración de la CLI de SEBASTIAN."""

import json
from pathlib import Path
from typer.testing import CliRunner
from sebastian.cli import app

runner = CliRunner()


def test_cli_version():
    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert "SEBASTIAN" in res.stdout


def test_cli_analyze(tmp_path):
    fuente = tmp_path / "recursion.c"
    fuente.write_text("""
    int contar(int n) {
        if (n == 0) return 0;
        return 1 + contar(n - 1);
    }
    int main(void) { return 0; }
    """)

    res = runner.invoke(app, ["analyze", str(fuente)])
    assert res.exit_code == 0
    assert "contar" in res.stdout
    assert "lineal" in res.stdout


def test_cli_trace_json(tmp_path):
    fuente = tmp_path / "fact.c"
    fuente.write_text("""
    #include <stdio.h>
    int fact(int n) {
        if (n <= 1) return 1;
        return n * fact(n - 1);
    }
    int main(void) { fact(3); return 0; }
    """)

    res = runner.invoke(app, ["trace", str(fuente), "--function", "fact", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["es_recursiva"] is True
    assert data["funcion"] == "fact"
    assert data["profundidad_maxima"] >= 1
