"""
Grafo LangGraph — §3.5 de la plantilla.

Construye el StateGraph con:
  - 4 nodos: planificar, recuperar, responder, validar
  - Aristas fijas: START → planificar → recuperar → responder → validar
  - Arista condicional desde validar:
      - Si necesita_mas → recuperar (loop de refinamiento)
      - Si completa → END
  - Checkpointing con MemorySaver (SQLite en producción)

Uso:
    from langgraph_flow.graph import create_graph, run_query

    graph = create_graph()
    result = run_query("¿Cuánto cuestan los polos?")
    print(result["respuesta"])
"""
from __future__ import annotations
import sys
from pathlib import Path

# Asegurar imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph_flow.state import EstadoPedido
from langgraph_flow.nodes import (
    nodo_planificar,
    nodo_recuperar,
    nodo_responder,
    nodo_validar,
)


def _routing_validar(state: EstadoPedido) -> str:
    """
    Función de routing para la arista condicional desde 'validar'.

    Si necesita_mas == True → vuelve a 'recuperar' (loop de refinamiento)
    Si necesita_mas == False → END
    """
    if state.get("necesita_mas", False):
        return "recuperar"
    return "__end__"


def create_graph(checkpointer=None):
    """
    Construye y compila el StateGraph de LangGraph.

    Args:
        checkpointer: Checkpointer para persistencia del estado.
                      Si None, usa MemorySaver (in-memory).

    Returns:
        Grafo compilado listo para ejecutar.
    """
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError:
        raise ImportError(
            "langgraph no está instalado. Ejecuta: pip install langgraph"
        )

    # Crear el grafo con el tipo de estado
    builder = StateGraph(EstadoPedido)

    # Agregar nodos
    builder.add_node("planificar", nodo_planificar)
    builder.add_node("recuperar", nodo_recuperar)
    builder.add_node("responder", nodo_responder)
    builder.add_node("validar", nodo_validar)

    # Aristas fijas
    builder.add_edge(START, "planificar")
    builder.add_edge("planificar", "recuperar")
    builder.add_edge("recuperar", "responder")
    builder.add_edge("responder", "validar")

    # Arista condicional: validar → recuperar (loop) o → END
    builder.add_conditional_edges(
        "validar",
        _routing_validar,
        {
            "recuperar": "recuperar",
            "__end__": END,
        },
    )

    # Compilar con checkpointer
    if checkpointer is None:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        except ImportError:
            checkpointer = None

    if checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
    else:
        graph = builder.compile()

    return graph


def run_query(
    question: str,
    thread_id: str = "default",
    graph=None,
) -> dict:
    """
    Ejecuta una consulta a través del grafo completo.

    Args:
        question: Pregunta del usuario.
        thread_id: Identificador de sesión (para checkpointing multiusuario).
        graph: Grafo precompilado (si None, crea uno nuevo).

    Returns:
        Estado final con la respuesta en state["respuesta"].
    """
    if graph is None:
        graph = create_graph()

    initial_state: EstadoPedido = {
        "pregunta": question,
        "contexto": [],
        "plan": [],
        "respuesta": "",
        "iteraciones": 0,
        "datos_pedido": {},
        "etapa": "inicio",
        "historial": [],
        "necesita_mas": False,
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Ejecutar el grafo
    result = graph.invoke(initial_state, config=config)
    return result


def get_graph_diagram() -> str:
    """
    Genera una representación textual del grafo para visualización.

    Returns:
        String con el diagrama del grafo.
    """
    return """
    ┌─────────┐
    │  START   │
    └────┬────┘
         │
    ┌────▼────┐
    │planificar│  Lee: pregunta → Escribe: plan
    └────┬────┘
         │
    ┌────▼────┐
    │recuperar │  Lee: pregunta → Escribe: contexto (RAG)
    └────┬────┘
         │
    ┌────▼────┐
    │responder │  Lee: pregunta, contexto → Escribe: respuesta
    └────┬────┘
         │
    ┌────▼────┐
    │ validar  │  Lee: respuesta, iteraciones
    └────┬────┘
         │
    ┌────▼────────────────┐
    │  ¿necesita_mas?     │
    │  Sí → recuperar     │ (loop de refinamiento, máx 3)
    │  No → END           │
    └─────────────────────┘
    """


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import sys as _sys
    query = " ".join(_sys.argv[1:]) or "¿Cuánto cuestan los polos con estampado?"
    print(f"🔍 Consulta: {query}")
    print(f"\n{get_graph_diagram()}")
    print("Ejecutando grafo...\n")
    result = run_query(query)
    print(f"📋 Plan: {result.get('plan', [])}")
    print(f"📄 Contexto: {len(result.get('contexto', []))} fragmentos")
    print(f"💬 Respuesta: {result.get('respuesta', 'Sin respuesta')}")
    print(f"🔁 Iteraciones: {result.get('iteraciones', 0)}")
