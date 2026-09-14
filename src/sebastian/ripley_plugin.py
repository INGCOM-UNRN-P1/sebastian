"""Adaptador de SEBASTIAN para el protocolo de plugins de RIPLEY."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from sebastian.core.analyzer import analizar_estatico_funcion, extraer_funciones_c


class SebastianPlugin:
    """Expone el análisis de recursión de SEBASTIAN como observaciones JSON."""

    name = "sebastian"
    version = "0.1.0"

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        observaciones = []
        reportes = []
        for archivo in sorted(Path(workspace).rglob("*.c")):
            contenido = archivo.read_text(encoding="utf-8")
            diagnosticos = [
                analizar_estatico_funcion(nombre, cuerpo, archivo, linea)
                for nombre, cuerpo, linea, _ in extraer_funciones_c(contenido)
            ]
            reportes.extend(diagnostico.to_dict() for diagnostico in diagnosticos)
            for diagnostico in diagnosticos:
                if not diagnostico.es_recursiva:
                    continue
                observaciones.append({
                    "rule_code": "SEBASTIAN001",
                    "severity": "warning" if diagnostico.riesgo_overflow == "ALTO" else "info",
                    "file": str(archivo),
                    "line": diagnostico.linea_inicio,
                    "message": (
                        f"Recursión {diagnostico.tipo_recursion} en "
                        f"{diagnostico.funcion}; riesgo {diagnostico.riesgo_overflow}."
                    ),
                    "suggestion": " ".join(diagnostico.recomendaciones),
                    "source_plugin": self.name,
                })
        return {"ok": True, "observaciones": observaciones, "reportes": reportes}
