# 🌀 SEBASTIAN — Analizador de Recursión y Stack Frame en C

SEBASTIAN es una herramienta pedagógica diseñada para analizar algoritmos recursivos en C, medir el consumo de memoria en la pila de ejecución (Stack), detectar riesgos de `Stack Overflow` y renderizar árboles de ejecución interactivos en terminal y diagramas Mermaid.

## Uso Rápido

```bash
# 1. Trazar ejecución recursiva y renderizar árbol en terminal
sebastian trace factorial.c --function factorial

# 2. Emitir diagrama en sintaxis Mermaid
sebastian trace fibonacci.c --mermaid

# 3. Analizar estáticamente todas las funciones de un archivo
sebastian analyze algoritmo.c

# 4. Salida estructurada JSON para pipelines CI
sebastian trace factorial.c --json
```
