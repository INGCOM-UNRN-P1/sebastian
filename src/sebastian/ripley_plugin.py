"""Adaptador de SEBASTIAN para el protocolo de plugins de RIPLEY."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from sebastian import __version__
from sebastian.core.analyzer import analizar_archivo, errores_de_compilacion


class SebastianPlugin:
    """Expone el análisis de recursión de SEBASTIAN como observaciones JSON."""

    name = "sebastian"
    version = __version__

    def is_available(self) -> bool:
        return True

    def execute(self, workspace: Path, manifest_config: Dict[str, Any]) -> Dict[str, Any]:
        observaciones = []
        reportes: List[Dict[str, Any]] = []
        includes = sorted({header.parent for header in Path(workspace).rglob("*.h")})
        for archivo in sorted(Path(workspace).rglob("*.c")):
            contenido = archivo.read_text(encoding="utf-8")
            errores = errores_de_compilacion(archivo, includes)
            if errores:
                observaciones.append({
                    "rule_code": "SEBASTIAN002",
                    "severity": "warning",
                    "file": str(archivo),
                    "line": 1,
                    "message": f"{archivo.name} no compila: el análisis de recursión puede no ser confiable.",
                    "suggestion": " ".join(errores),
                    "source_plugin": self.name,
                })
            diagnosticos = analizar_archivo(contenido, archivo, includes)
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
