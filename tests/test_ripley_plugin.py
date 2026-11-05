from pathlib import Path

from sebastian.ripley_plugin import SebastianPlugin


def test_sebastian_plugin_contract(tmp_path: Path):
    fuente = tmp_path / "main.c"
    fuente.write_text("int main(void) { return 0; }\n", encoding="utf-8")

    resultado = SebastianPlugin().execute(tmp_path, {})

    assert SebastianPlugin().is_available()
    assert resultado["ok"] is True
    assert resultado["observaciones"] == []


def test_avisa_el_archivo_que_no_compila(tmp_path: Path):
    (tmp_path / "roto.c").write_text("int f(void)\n{\n    return 1\n}\n", encoding="utf-8")

    resultado = SebastianPlugin().execute(tmp_path, {})

    assert [o["rule_code"] for o in resultado["observaciones"]] == ["SEBASTIAN002"]


def test_los_headers_del_workspace_no_son_un_error(tmp_path: Path):
    (tmp_path / "cabeceras").mkdir()
    (tmp_path / "cabeceras" / "v.h").write_text("#define V 1\n", encoding="utf-8")
    (tmp_path / "main.c").write_text('#include "v.h"\nint main(void) { return V; }\n', encoding="utf-8")

    assert SebastianPlugin().execute(tmp_path, {})["observaciones"] == []
