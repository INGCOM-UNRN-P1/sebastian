"""CLI de SEBASTIAN — Analizador de llamadas recursivas y consumo de stack frame en C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from sebastian import __version__
from sebastian.core.analyzer import (
    analizar_estatico_funcion,
    extraer_funciones_c,
    trazar_recursion_dinamica,
)
from sebastian.core.visualizer import construir_rich_tree, generar_mermaid_diagram

console = Console()
err_console = Console(stderr=True)

app = typer.Typer(
    name="sebastian",
    help="🌀 SEBASTIAN — Analizador de llamadas recursivas, consumo de stack frame y riesgos de stack overflow en C.",
    add_completion=True,
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold cyan]SEBASTIAN[/bold cyan] versión [bold]{__version__}[/bold]")
        raise typer.Exit(code=0)


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Muestra la versión de SEBASTIAN.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    pass


@app.command("trace")
def trace_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C con la función recursiva a trazar."),
    funcion: Optional[str] = typer.Option(None, "--function", "-f", help="Nombre de la función recursiva a trazar."),
    args: Optional[List[str]] = typer.Argument(None, help="Argumentos para el programa al ejecutar."),
    stdin: Optional[str] = typer.Option(None, "--stdin", "-i", help="Entrada estándar para el programa."),
    tree_view: bool = typer.Option(True, "--tree/--no-tree", help="Mostrar árbol de llamadas en terminal."),
    mermaid_view: bool = typer.Option(False, "--mermaid", "-m", help="Emitir diagrama en formato Mermaid."),
    json_output: bool = typer.Option(False, "--json", help="Emitir reporte en formato JSON."),
) -> None:
    """Ejecuta el código instrumentado, traza las llamadas recursivas y visualiza el árbol de ejecución."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    diag = trazar_recursion_dinamica(
        archivo_c=fuente,
        funcion_target=funcion or "",
        args_programa=args,
        stdin_data=stdin or "",
    )

    if json_output:
        print(json.dumps(diag.to_dict(), indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

    if mermaid_view and diag.arbol:
        console.print(generar_mermaid_diagram(diag.arbol))
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
        f"• Riesgo de Stack Overflow: [{color_riesgo}][bold]{diag.riesgo_overflow}[/bold][/{color_riesgo}]"
    )
    console.print(Panel(info_text, title=f"📊 Análisis de Recursión: {diag.funcion}()", border_style="cyan"))

    # Árbol visual
    if tree_view and diag.arbol:
        console.print("\n[bold]🌲 Árbol de Ejecución de Llamadas:[/bold]")
        console.print(construir_rich_tree(diag.arbol))

    # Recomendaciones
    if diag.recomendaciones:
        rec_text = "\n".join(f"• {r}" for r in diag.recomendaciones)
        console.print(Panel(rec_text, title="💡 Recomendaciones Pedagógicas", border_style="yellow"))


def generar_seccion_markdown(reportes: list) -> str:
    """Genera sección de análisis de recursión y stack frames para Dredd."""
    lines = [
        "<!-- dredd-section: sebastian v1.0.0 -->\n",
        "## Análisis de Recursión y Consumo de Pila (Sebastian)\n",
    ]
    recursivas = [r for r in reportes if r.es_recursiva]
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
) -> None:
    """Analiza estáticamente todas las funciones del archivo en busca de recursión y riesgos de desbordamiento."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)

    contenido = fuente.read_text(encoding="utf-8")
    funciones = extraer_funciones_c(contenido)

    reportes = []
    for fn_name, cuerpo, l_start, _ in funciones:
        diag = analizar_estatico_funcion(fn_name, cuerpo, fuente, l_start)
        reportes.append(diag)

    if output_md:
        md_text = generar_seccion_markdown(reportes)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(md_text, encoding="utf-8")
        console.print(f"[green]✓ Sección Markdown generada en:[/green] [cyan]{output_md}[/cyan]")
        raise typer.Exit(code=0)

    if json_output:
        print(json.dumps([r.to_dict() for r in reportes], indent=2, ensure_ascii=False))
        raise typer.Exit(code=0)

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


@app.command("report")
def report_cmd(
    fuente: Path = typer.Argument(..., help="Archivo C a analizar."),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Ruta de destino del archivo Markdown."),
) -> None:
    """Genera directamente la sección de reporte Markdown de SEBASTIAN para Dredd."""
    if not fuente.is_file():
        err_console.print(f"[red]Error:[/red] No se encontró el archivo '{fuente}'.")
        raise typer.Exit(code=2)
    contenido = fuente.read_text(encoding="utf-8")
    funciones = extraer_funciones_c(contenido)
    reportes = []
    for fn_name, cuerpo, l_start, _ in funciones:
        diag = analizar_estatico_funcion(fn_name, cuerpo, fuente, l_start)
        reportes.append(diag)
    md_content = generar_seccion_markdown(reportes)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md_content, encoding="utf-8")
        console.print(f"[green]✓ Reporte Markdown generado en:[/green] [cyan]{output}[/cyan]")
    else:
        print(md_content)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
