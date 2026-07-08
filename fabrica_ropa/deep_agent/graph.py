"""
Grafo LangGraph del Deep Agent — §3.6 de la plantilla.

Implementa el patrón Deep Agent como un grafo LangGraph:
  planificar → investigar → redactar → criticar → (loop o END)

Componentes:
  - Planificador: descompone la tarea en pasos
  - Investigador: recupera info del catálogo (RAG)
  - Redactor: estructura la respuesta formal
  - Crítico: evalúa contra checklist de calidad

Límites operativos:
  - Máx 5 iteraciones
  - Máx 10 invocaciones a sub-agentes
  - Fallback: devuelve mejor borrador si no converge

Uso:
    from deep_agent.graph import create_deep_agent_graph, run_deep_agent

    result = run_deep_agent("Compara precios de polos con y sin estampado")
    print(result["respuesta_final"])
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep_agent.state import EstadoDeepAgent
from deep_agent.planner import nodo_planificar_deep
from deep_agent.sub_agents import (
    agente_investigador,
    agente_redactor,
    agente_critico,
)


def _routing_critico(state: EstadoDeepAgent) -> str:
    """
    Función de routing tras el Crítico.

    Si terminado → END (respuesta aprobada o límite alcanzado)
    Si no → investigar (loop de refinamiento)
    """
    if state.get("terminado", False):
        return "__end__"
    return "investigar"


def create_deep_agent_graph(checkpointer=None):
    """
    Construye el grafo LangGraph del Deep Agent.

    Nodos: planificar → investigar → redactar → criticar
    Loop: criticar → investigar (si no aprobado, hasta max_iteraciones)
    """
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError:
        raise ImportError(
            "langgraph no está instalado. Ejecuta: pip install langgraph"
        )

    builder = StateGraph(EstadoDeepAgent)

    # Nodos
    builder.add_node("planificar", nodo_planificar_deep)
    builder.add_node("investigar", agente_investigador)
    builder.add_node("redactar", agente_redactor)
    builder.add_node("criticar", agente_critico)

    # Aristas fijas
    builder.add_edge(START, "planificar")
    builder.add_edge("planificar", "investigar")
    builder.add_edge("investigar", "redactar")
    builder.add_edge("redactar", "criticar")

    # Arista condicional: criticar → investigar (loop) o → END
    builder.add_conditional_edges(
        "criticar",
        _routing_critico,
        {
            "investigar": "investigar",
            "__end__": END,
        },
    )

    # Compilar
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


def run_deep_agent(
    task: str,
    thread_id: str = "deep_default",
    max_iterations: int = 3,
    graph=None,
) -> dict:
    """
    Ejecuta el Deep Agent sobre una tarea.

    Args:
        task: Tarea a resolver.
        thread_id: ID de sesión para checkpointing.
        max_iterations: Máximo de ciclos plan-invest-redact-critic.
        graph: Grafo precompilado (si None, crea uno nuevo).

    Returns:
        Estado final con respuesta_final.
    """
    if graph is None:
        graph = create_deep_agent_graph()

    initial_state: EstadoDeepAgent = {
        "tarea": task,
        "plan": [],
        "paso_actual": 0,
        "hallazgos": [],
        "borrador": "",
        "critica": {},
        "respuesta_final": "",
        "iteracion": 0,
        "max_iteraciones": max_iterations,
        "terminado": False,
        "artefactos": {},
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state, config=config)
    return result


def get_deep_agent_diagram() -> str:
    """Diagrama textual del Deep Agent."""
    return """
    ┌─────────────┐
    │    START     │
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │ PLANIFICADOR │  Descompone tarea en pasos
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │INVESTIGADOR  │  RAG + búsqueda → hallazgos
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │  REDACTOR    │  hallazgos → borrador formal
    └──────┬──────┘
           │
    ┌──────▼──────┐
    │   CRÍTICO    │  Evalúa contra checklist
    └──────┬──────┘
           │
    ┌──────▼──────────────┐
    │ ¿Aprobado?          │
    │ No → INVESTIGADOR   │ (loop, máx 3-5 iter)
    │ Sí → END            │
    └─────────────────────┘
    """


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import sys as _sys
    task = " ".join(_sys.argv[1:]) or "Compara precios de polos con y sin estampado para 100 unidades"
    print(f"🎯 Tarea: {task}")
    print(get_deep_agent_diagram())
    print("Ejecutando Deep Agent...\n")
    result = run_deep_agent(task)
    print(f"📋 Plan: {result.get('plan', [])}")
    print(f"🔍 Hallazgos: {len(result.get('hallazgos', []))}")
    print(f"📝 Borrador: {result.get('borrador', '')[:200]}...")
    print(f"✅ Crítica: {result.get('critica', {})}")
    print(f"💬 Respuesta final: {result.get('respuesta_final', 'Sin respuesta')}")
    print(f"🔁 Iteraciones: {result.get('iteracion', 0)}")
