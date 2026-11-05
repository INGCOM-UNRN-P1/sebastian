"""CLI de SEBASTIAN — Analizador de llamadas recursivas y consumo de stack frame en C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from yutani.cli import crear_app
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from sebastian import __version__
from sebastian.core.analyzer import (
    NODOS_ARBOL,
    PROFUNDIDAD_ARBOL,
    analizar_archivo,
    errores_de_compilacion,
    trazar_recursion_dinamica,
)
from sebastian.core.models import DiagnosticoRecursion
from sebastian.core.visualizer import construir_rich_tree, generar_mermaid_diagram

console = Console()
err_console = Console(stderr=True)
AYUDA_INCLUDE = "Carpeta de headers (se puede repetir). El include/ del proyecto se detecta solo."

# Contrato de línea de comandos del ecosistema (-h/--help, --version/-v, errores de datos como
# mensajes) y textos de Typer en español, desde yutani (N-ECO-14).
app = crear_app(
    "sebastian",
    __version__,
    "🌀 SEBASTIAN — Analizador de llamadas recursivas, consumo de stack frame y riesgos de desborde de pila en C.",
    add_completion=True,
)


def _avisar_si_no_compila(fuente: Path, includes: List[Path]) -> Optional[List[str]]:
    """El análisis estático lee el texto sin compilarlo: sin este aviso, un archivo roto da un
    resultado que parece bueno. Devuelve los errores."""
    errores = errores_de_compilacion(fuente, includes)
    if errores is None:
        err_console.print("[yellow]⚠ Falta gcc: no se pudo comprobar si el archivo compila.[/yellow]")
    elif errores:
        detalle = "\n".join(f"• {escape(error)}" for error in errores)
        err_console.print(Panel(f"{escape(fuente.name)} no compila: este análisis puede no ser confiable.\n\n{detalle}",
                                title="❌ El código no compila", border_style="red"))
    return errores


def _informar_sin_traza(diag: DiagnosticoRecursion) -> None:
    """Por qué no hay árbol: sin esto, una traza fallida se ve como un programa sin llamadas."""
    detalle = "\n".join(f"• {escape(error)}" for error in diag.errores_compilacion)
    texto = escape(diag.motivo_sin_medicion or "No se pudo trazar la función.") + (f"\n\n{detalle}" if detalle else "")
    titulo = "❌ El código no compila" if diag.errores_compilacion else "⚠️ No se pudo obtener la traza"
    err_console.print(Panel(texto, title=titulo, border_style="red"))


def _avisar_traza_incompleta(diag: DiagnosticoRecursion) -> None:
    if diag.ejecucion_cortada:
        err_console.print(f"[yellow]⚠ El programa {escape(diag.ejecucion_cortada)}. La traza llega hasta ahí.[/yellow]")
    if diag.arbol_recortado:
        err_console.print(f"[yellow]⚠ El árbol muestra hasta {PROFUNDIDAD_ARBOL} niveles y {NODOS_ARBOL} llamadas; "
                          "los totales cuentan todas.[/yellow]")


@app.command("trace")
def trace_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C con la función recursiva a trazar."),
    funcion: Optional[str] = typer.Option(None, "--function", "-f", help="Nombre de la función recursiva a trazar."),
    args: Optional[List[str]] = typer.Argument(None, help="Argumentos para el programa al ejecutar."),
    include: Optional[List[Path]] = typer.Option(None, "--include", "-I", help=AYUDA_INCLUDE),
    source: Optional[List[Path]] = typer.Option(None, "--source", "-s", help="Otro .c del programa, como el que tiene main (se puede repetir)."),
    stdin: Optional[str] = typer.Option(None, "--stdin", "-i", help="Entrada estándar para el programa."),
    tree_view: bool = typer.Option(True, "--tree/--no-tree", help="Mostrar árbol de llamadas en terminal."),
    mermaid_view: bool = typer.Option(False, "--mermaid", "-m", help="Emitir diagrama en formato Mermaid."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en formato JSON."),
) -> None:
    """Ejecuta el código instrumentado, traza las llamadas recursivas y visualiza el árbol de ejecución.

    Códigos de salida: 0 hay traza, 1 no se pudo obtener (se explica por qué) y 2 archivo inexistente.
    """
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    for otra in source or []:
        if not otra.is_file():
            err_console.print(f"[red]Error:[/red] No se encontró el archivo '{otra}'.")
            raise typer.Exit(code=2)

    diag = trazar_recursion_dinamica(
        archivo_c=fuente,
        funcion_target=funcion or "",
        args_programa=args,
        stdin_data=stdin or "",
        includes=include or [],
        otras_fuentes=source or [],
    )

    codigo = 0 if diag.arbol else 1

    if json_output:
        print(json.dumps(diag.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=codigo)

    if not diag.arbol:
        _informar_sin_traza(diag)
        raise typer.Exit(code=codigo)

    if mermaid_view:
        console.print(generar_mermaid_diagram(diag.arbol))
        _avisar_traza_incompleta(diag)
        raise typer.Exit(code=0)

    # Panel de Resumen
    color_riesgo = "green" if diag.riesgo_overflow == "BAJO" else "yellow" if diag.riesgo_overflow == "MEDIO" else "red"
    info_text = (
        f"• Función: [bold cyan]{diag.funcion}[/bold cyan] ({fuente.name}:{diag.linea_inicio})\n"
        f"• Tipo de recursión: [bold]{diag.tipo_recursion.capitalize()}[/bold]\n"
        f"• Caso base detectado: {'[green]✓ Sí[/green]' if diag.tiene_caso_base else '[bold red]✗ No detectado[/bold red]'}\n"
        f"• Total de llamadas registradas: [bold]{diag.total_llamadas}[/bold]\n"
        f"• Profundidad máxima alcanzada: [bold]{diag.profundidad_maxima}[/bold] frames\n"
        f"• Consumo de Stack estimado: ~[bold]{diag.consumo_stack_por_frame_bytes} bytes/frame[/bold] (Pico: ~[bold]{diag.consumo_pico_stack_bytes} B[/bold])\n"
        f"• Riesgo de desborde de pila: [{color_riesgo}][bold]{diag.riesgo_overflow}[/bold][/{color_riesgo}]"
    )
    console.print(Panel(info_text, title=f"📊 Análisis de Recursión: {diag.funcion}()", border_style="cyan"))

    # Árbol visual
    if tree_view and diag.arbol:
        console.print("\n[bold]🌲 Árbol de Ejecución de Llamadas:[/bold]")
        console.print(construir_rich_tree(diag.arbol))
    _avisar_traza_incompleta(diag)

    # Recomendaciones
    if diag.recomendaciones:
        rec_text = "\n".join(f"• {r}" for r in diag.recomendaciones)
        console.print(Panel(rec_text, title="💡 Recomendaciones Pedagógicas", border_style="yellow"))


def generar_seccion_markdown(reportes: list, errores: Optional[List[str]] = None) -> str:
    """Genera sección de análisis de recursión y stack frames para Dredd."""
    recursivas = [r for r in reportes if r.es_recursiva]
    riesgo = any(not r.tiene_caso_base or r.riesgo_overflow == "ALTO" for r in recursivas)
    status = "fail" if errores or riesgo else "ok"
    lines = [
        f"<!-- dredd-section: sebastian, tool=sebastian, version=1.0.0, status={status} -->\n",
        "## Análisis de Recursión y Consumo de Pila (Sebastian)\n",
    ]
    if errores:
        lines.append("> [!WARNING]\n> **El código no compila:** este análisis puede no ser confiable.")
        lines.extend(f"> - {error}" for error in errores)
        lines.append("")
    lines.append(f"- **Funciones analizadas:** {len(reportes)}")
    lines.append(f"- **Funciones recursivas:** {len(recursivas)}\n")
    if not recursivas:
        lines.append("> [!TIP]\n> **Flujo Iterativo:** No se detectaron funciones recursivas en el módulo analizado.\n")
    else:
        lines.append("| Función | Línea | Tipo Recursión | Caso Base | Bytes/Frame | Riesgo Overflow |")
        lines.append("| :--- | :---: | :---: | :---: | :---: | :---: |")
        for r in recursivas:
            cb_str = "✓ Sí" if r.tiene_caso_base else "❌ No"
            fn_limpia = r.funcion.replace("|", "&#124;")
            lines.append(f"| `{fn_limpia}()` | {r.linea_inicio} | {r.tipo_recursion} | {cb_str} | ~{r.consumo_stack_por_frame_bytes} B | **{r.riesgo_overflow}** |")
        lines.append("")
    return "\n".join(lines)


@app.command("analyze")
@app.command("check")
def analyze_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a analizar estáticamente."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en JSON."),
    output_md: Optional[Path] = typer.Option(None, "--md", "--output-md", "-o", help="Generar sección de reporte en formato Markdown para fusión en Dredd."),
    fail_on_high_risk: bool = typer.Option(False, "--fail-on-high-risk", help="Salir con código 1 si alguna función tiene riesgo de overflow ALTO (por defecto siempre 0)."),
    include: Optional[List[Path]] = typer.Option(None, "--include", "-I", help=AYUDA_INCLUDE),
) -> None:
    """Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento.

    El análisis lee el fuente sin compilarlo: si el archivo no compila lo avisa, porque el resultado
    puede no ser confiable.

    Códigos de salida: 0 análisis correcto, 2 archivo inexistente y, solo con
    --fail-on-high-risk, 1 si hay riesgo ALTO.
    """
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    errores = _avisar_si_no_compila(fuente, include or [])
    reportes = analizar_archivo(fuente.read_text(encoding="utf-8"), fuente, include or [])

    codigo = 1 if fail_on_high_risk and any(r.es_recursiva and r.riesgo_overflow == "ALTO" for r in reportes) else 0

    if output_md:
        md_text = generar_seccion_markdown(reportes, errores)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[green]✓ Sección Markdown generada en:[/green] [cyan]{output_md}[/cyan]")
        raise typer.Exit(code=codigo)

    if json_output:
        print(json.dumps([r.to_dict() for r in reportes], indent=2, ensure_ascii=False))
        raise typer.Exit(code=codigo)

    tabla = Table(title=f"Análisis de Recursión en {fuente.name} ({len(reportes)} funciones)")
    tabla.add_column("Función", style="cyan")
    tabla.add_column("Línea", justify="center")
    tabla.add_column("Recursiva", justify="center")
    tabla.add_column("Tipo", justify="center")
    tabla.add_column("Caso Base", justify="center")
    tabla.add_column("Bytes/Frame", justify="right")
    tabla.add_column("Riesgo", justify="center")

    recursivas_count = 0
    for r in reportes:
        if r.es_recursiva:
            recursivas_count += 1
            rec_str = "[bold green]Sí[/bold green]"
            cb_str = "[green]✓[/green]" if r.tiene_caso_base else "[red]✗[/red]"
            color_r = "green" if r.riesgo_overflow == "BAJO" else "yellow" if r.riesgo_overflow == "MEDIO" else "red"
            riesgo_str = f"[{color_r}]{r.riesgo_overflow}[/{color_r}]"
        else:
            rec_str = "[dim]No[/dim]"
            cb_str = "—"
            riesgo_str = "[dim]—[/dim]"

        tabla.add_row(
            r.funcion,
            str(r.linea_inicio),
            rec_str,
            r.tipo_recursion if r.es_recursiva else "—",
            cb_str,
            f"{r.consumo_stack_por_frame_bytes} B" if r.es_recursiva else "—",
            riesgo_str,
        )

    console.print(tabla)
    console.print(f"[dim]Total funciones: {len(reportes)} · Recursivas detectadas: {recursivas_count}[/dim]")
    if codigo:
        raise typer.Exit(code=codigo)


@app.command("report")
def report_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a analizar."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
    include: Optional[List[Path]] = typer.Option(None, "--include", "-I", help=AYUDA_INCLUDE),
) -> None:
    """Genera directamente la sección de reporte Markdown de SEBASTIAN para Dredd."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)
    errores = _avisar_si_no_compila(fuente, include or [])
    reportes = analizar_archivo(fuente.read_text(encoding="utf-8"), fuente, include or [])
    md_content = generar_seccion_markdown(reportes, errores)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[green]✓ Reporte Markdown generado en:[/green] [cyan]{output}[/cyan]")
    else:
        print(md_content)


@app.command("doctor")
def doctor_cmd(
    json_output: bool = typer.Option(False, "--json", help="Emitir diagnóstico en formato JSON estructurado."),
) -> None:
    """Verifica el estado del entorno de análisis de recursión y stack SEBASTIAN (Python, GCC)."""
    import shutil
    import sys
    diagnostico = []

    py_ok = sys.version_info >= (3, 10)
    diagnostico.append({
        "componente": "Python Runtime",
        "estado": "OK" if py_ok else "ERROR",
        "requerido": True,
        "detalle": f"Python {sys.version.split()[0]}",
    })

    gcc_path = shutil.which("gcc")
    diagnostico.append({
        "componente": "Compilador GCC",
        "estado": "OK" if gcc_path else "ADVERTENCIA",
        "requerido": False,
        "detalle": gcc_path or "No encontrado (requerido para modo trace dinámico)",
    })

    todo_ok = py_ok

    if json_output:
        payload = {
            "schema_version": "1.0.0",
            "herramienta": "sebastian",
            "ok": todo_ok,
            "componentes": diagnostico,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        raise typer.Exit(code=0 if todo_ok else 1)

    tabla = Table(title="🏥 Diagnóstico del Entorno SEBASTIAN (doctor)", border_style="cyan")
    tabla.add_column("Componente", style="bold white")
    tabla.add_column("Estado", justify="center")
    tabla.add_column("Detalle")

    for c in diagnostico:
        color = "bold green" if c["estado"] == "OK" else ("bold yellow" if c["estado"] == "ADVERTENCIA" else "bold red")
        simbolo = "✓" if c["estado"] == "OK" else ("⚠️" if c["estado"] == "ADVERTENCIA" else "✗")
        tabla.add_row(str(c["componente"]), f"[{color}]{simbolo} {c['estado']}[/{color}]", str(c["detalle"]))

    console.print(tabla)
    if not todo_ok:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
