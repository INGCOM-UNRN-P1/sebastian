from pathlib import Path

from sebastian.ripley_plugin import SebastianPlugin


def test_sebastian_plugin_contract(tmp_path: Path):
    fuente = tmp_path / "main.c"
    fuente.write_text("int main(void) { return 0; }\n", encoding="utf-8")

    resultado = SebastianPlugin().execute(tmp_path, {})

    assert SebastianPlugin().is_available()
    assert resultado["ok"] is True
    assert resultado["observaciones"] == []
