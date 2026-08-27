"""Visualizador del árbol de llamadas recursivas en formato Rich Tree y Mermaid."""

from __future__ import annotations

from rich.tree import Tree
from sebastian.core.models import NodoLlamada


def construir_rich_tree(nodo: NodoLlamada) -> Tree:
    """Construye un árbol visual de Rich a partir del nodo raíz de llamadas."""
    texto_ret = f" -> [bold green]{nodo.retorno}[/bold green]" if nodo.retorno is not None else ""
    texto_stack = f" [dim]({nodo.stack_bytes} bytes stack)[/dim]" if nodo.stack_bytes > 0 else ""
    label = f"[cyan]{nodo.funcion}[/cyan]({nodo.argumentos}){texto_ret}{texto_stack}"

    tree = Tree(label)
    for hijo in nodo.hijos:
        _agregar_hijos_rich(tree, hijo)
    return tree


def _agregar_hijos_rich(padre_tree: Tree, nodo: NodoLlamada) -> None:
    texto_ret = f" -> [bold green]{nodo.retorno}[/bold green]" if nodo.retorno is not None else ""
    texto_stack = f" [dim]({nodo.stack_bytes} B)[/dim]" if nodo.stack_bytes > 0 else ""
    label = f"[cyan]{nodo.funcion}[/cyan]({nodo.argumentos}){texto_ret}{texto_stack}"

    sub_tree = padre_tree.add(label)
    for hijo in nodo.hijos:
        _agregar_hijos_rich(sub_tree, hijo)


def generar_mermaid_diagram(nodo: NodoLlamada) -> str:
    """Genera un diagrama de flujo en sintaxis Mermaid (graph TD)."""
    lineas = ["graph TD"]

    def _recorrer(padre: NodoLlamada):
        label_padre = f'"{padre.funcion}({padre.argumentos})' + (f' ➜ {padre.retorno}"' if padre.retorno else '"')
        for hijo in padre.hijos:
            label_hijo = f'"{hijo.funcion}({hijo.argumentos})' + (f' ➜ {hijo.retorno}"' if hijo.retorno else '"')
            lineas.append(f'    node{padre.id}[{label_padre}] --> node{hijo.id}[{label_hijo}]')
            _recorrer(hijo)

    _recorrer(nodo)
    return "\n".join(lineas)
