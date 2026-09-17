"""Modelos de datos para el análisis de recursión en SEBASTIAN."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class NodoLlamada:
    """Representa un nodo en el árbol de ejecución de llamadas recursivas."""
    id: int
    funcion: str
    argumentos: str
    profundidad: int
    retorno: Optional[str] = None
    stack_bytes: int = 0
    hijos: List[NodoLlamada] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "funcion": self.funcion,
            "argumentos": self.argumentos,
            "profundidad": self.profundidad,
            "retorno": self.retorno,
            "stack_bytes": self.stack_bytes,
            "hijos": [h.to_dict() for h in self.hijos],
        }


@dataclass
class DiagnosticoRecursion:
    """Resultado del análisis estático y dinámico de recursión sobre una función C."""
    funcion: str
    archivo: Path
    es_recursiva: bool
    tipo_recursion: str            # "ninguna", "lineal", "cola" (tail), "arbol" (multiple), "mutua"
    tiene_caso_base: bool
    linea_inicio: int = 1
    total_llamadas: int = 0
    profundidad_maxima: int = 0
    consumo_stack_por_frame_bytes: int = 0
    consumo_pico_stack_bytes: int = 0
    riesgo_overflow: str = "BAJO"  # "BAJO", "MEDIO", "ALTO"
    arbol: Optional[NodoLlamada] = None
    recomendaciones: List[str] = field(default_factory=list)
    # "dinamica" cuando el árbol, la profundidad y el consumo salen de ejecutar
    # el programa instrumentado; "estatica" cuando solo se pudo inspeccionar el
    # fuente. Sin esta distinción, una medición fallida se veía igual que una
    # real.
    origen_medicion: str = "estatica"
    motivo_sin_medicion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "1.0.0",
            "funcion": self.funcion,
            "archivo": str(self.archivo),
            "es_recursiva": self.es_recursiva,
            "tipo_recursion": self.tipo_recursion,
            "tiene_caso_base": self.tiene_caso_base,
            "linea_inicio": self.linea_inicio,
            "origen_medicion": self.origen_medicion,
            "motivo_sin_medicion": self.motivo_sin_medicion,
            "total_llamadas": self.total_llamadas,
            "profundidad_maxima": self.profundidad_maxima,
            "consumo_stack_por_frame_bytes": self.consumo_stack_por_frame_bytes,
            "consumo_pico_stack_bytes": self.consumo_pico_stack_bytes,
            "riesgo_overflow": self.riesgo_overflow,
            "arbol": self.arbol.to_dict() if self.arbol else None,
            "recomendaciones": self.recomendaciones,
        }
