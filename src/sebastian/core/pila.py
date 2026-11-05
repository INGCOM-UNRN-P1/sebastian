"""Profundidad máxima de recursión antes del Stack Overflow (QoL #870).

El tamaño de cada marco sale de `gcc -fstack-usage` (lo que el compilador reserva de verdad para la
función, más la dirección de retorno), y el límite de la pila del proceso de `RLIMIT_STACK` (8 MiB
por defecto en Linux; en Windows el ejecutable trae 1 MiB). Si no se puede compilar, queda la
estimación por el código de la función.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

PILA_WINDOWS = 1024 * 1024
PILA_POR_DEFECTO = 8 * 1024 * 1024
DIRECCION_DE_RETORNO = 8


def limite_de_pila() -> Tuple[int, str]:
    """(bytes, de dónde sale el dato)."""
    if os.name == "nt":
        return PILA_WINDOWS, "1 MiB, el tamaño de pila por defecto de un ejecutable en Windows"
    try:
        import resource

        blando, _ = resource.getrlimit(resource.RLIMIT_STACK)
        if blando not in (resource.RLIM_INFINITY, -1) and blando > 0:
            return int(blando), "el límite de pila del sistema (ulimit -s)"
    except (ImportError, ValueError, OSError):
        pass
    return PILA_POR_DEFECTO, "8 MiB, el límite de pila habitual en Linux"


def directorios_include(fuente: Path, extra: Sequence[Path] = ()) -> List[Path]:
    """Dónde buscar los headers de `fuente`: los pedidos con -I y el `include/` de la carpeta del
    archivo o de la de arriba (src/ + include/ es la forma de los proyectos de la cátedra)."""
    carpeta = Path(fuente).resolve().parent
    candidatos = [Path(d).resolve() for d in extra]
    candidatos += [d for d in (carpeta / "include", carpeta.parent / "include") if d.is_dir()]
    return list(dict.fromkeys(candidatos))


@lru_cache(maxsize=32)
def _marcos_compilados(fuente: str, _mtime: float, includes: Tuple[str, ...] = ()) -> Dict[str, int]:
    gcc = shutil.which("gcc")
    if not gcc:
        return {}
    with tempfile.TemporaryDirectory(prefix="sebastian-pila-") as tmp:
        objeto = Path(tmp) / "f.o"
        res = subprocess.run([gcc, "-O0", "-std=c11", "-fstack-usage", *(f"-I{d}" for d in includes), "-c", fuente,
                              "-o", str(objeto)],
                             capture_output=True, text=True, check=False)
        su = objeto.with_suffix(".su")
        if res.returncode != 0 or not su.is_file():
            return {}
        marcos = {}
        for linea in su.read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r".*:(?P<fn>[A-Za-z_]\w*)\t(?P<bytes>\d+)\t", linea)
            if m:
                marcos[m.group("fn")] = int(m.group("bytes")) + DIRECCION_DE_RETORNO
        return marcos


def marco_compilado(fuente: Path, funcion: str, includes: Sequence[Path] = ()) -> Optional[int]:
    """Bytes de pila de cada llamada a `funcion` según gcc, o None si no se pudo compilar."""
    fuente = Path(fuente)
    if not fuente.is_file():
        return None
    carpetas = tuple(str(d) for d in directorios_include(fuente, includes))
    return _marcos_compilados(str(fuente.resolve()), fuente.stat().st_mtime, carpetas).get(funcion)


def profundidad_maxima(marco_bytes: int, limite_bytes: int) -> int:
    return limite_bytes // max(1, marco_bytes)
