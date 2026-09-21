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


def test_cli_doctor():
    res = runner.invoke(app, ["doctor"])
    assert res.exit_code == 0
    assert "doctor" in res.stdout.lower()

    res_json = runner.invoke(app, ["doctor", "--json"])
    assert res_json.exit_code == 0
    data = json.loads(res_json.stdout)
    assert data["herramienta"] == "sebastian"
    assert data["ok"] is True


def test_check_fail_on_high_risk(tmp_path):
    """SEBASTIAN-D0402: exit 1 opt-in cuando hay recursión sin caso base (riesgo ALTO)."""
    f = tmp_path / "r.c"
    f.write_text("int f(int n) { return f(n + 1); }\nint main(void) { return 0; }\n")
    assert runner.invoke(app, ["check", str(f)]).exit_code == 0
    assert runner.invoke(app, ["check", str(f), "--fail-on-high-risk"]).exit_code == 1
    assert runner.invoke(app, ["check", str(f), "--json", "--fail-on-high-risk"]).exit_code == 1
    ok = tmp_path / "ok.c"
    ok.write_text("int g(int n) { if (n <= 1) return 1; return n * g(n - 1); }\nint main(void) { return 0; }\n")
    assert runner.invoke(app, ["check", str(ok), "--fail-on-high-risk"]).exit_code == 0


def test_frame_estimado_y_traza_usan_la_misma_base():
    """SEBASTIAN-D0304: base 32 B documentada, con extras por double/arreglos."""
    from pathlib import Path
    from sebastian.core.analyzer import analizar_estatico_funcion
    base = analizar_estatico_funcion("f", "int f(int n) { if (n<1) return 0; return f(n-1); }", Path("x.c"), 1)
    doble = analizar_estatico_funcion("f", "double f(int n) { if (n<1) return 0; return f(n-1); }", Path("x.c"), 1)
    assert base.consumo_stack_por_frame_bytes == 32
    assert doble.consumo_stack_por_frame_bytes == 64
