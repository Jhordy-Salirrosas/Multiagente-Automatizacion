"""
Grafo LangGraph para Compra de Materiales — §3.5 Proceso 2.

Construye el StateGraph con:
  - 5 nodos: planificar_materiales → estimar_presupuesto →
             aprobar_presupuesto (HITL) → seleccionar_proveedor → notificar_produccion
  - HITL con interrupt_before en aprobar_presupuesto
  - Arista condicional: si presupuesto rechazado → END

Uso:
    from langgraph_flow.materials_graph import create_materials_graph, run_materials_flow

    result = run_materials_flow()
    print(result["estado_proceso"])
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph_flow.state import EstadoPedido
from langgraph_flow.materials_nodes import (
    nodo_planificar_materiales,
    nodo_estimar_presupuesto,
    nodo_aprobar_presupuesto,
    nodo_seleccionar_proveedor,
    nodo_notificar_produccion,
)


def _routing_aprobacion(state: EstadoPedido) -> str:
    """
    Routing tras aprobación de presupuesto.

    Si aprobado → seleccionar_proveedor
    Si rechazado → END
    """
    if state.get("presupuesto_aprobado", False):
        return "seleccionar_proveedor"
    return "__end__"


def create_materials_graph(checkpointer=None, enable_hitl: bool = True):
    """
    Construye el grafo LangGraph para el Proceso 2: Compra de Materiales.

    Args:
        checkpointer: Checkpointer para persistencia.
        enable_hitl: Si True, agrega interrupt_before en aprobar_presupuesto.

    Returns:
        Grafo compilado.
    """
    try:
        from langgraph.graph import StateGraph, START, END
    except ImportError:
        raise ImportError(
            "langgraph no está instalado. Ejecuta: pip install langgraph"
        )

    builder = StateGraph(EstadoPedido)

    # Nodos
    builder.add_node("planificar_materiales", nodo_planificar_materiales)
    builder.add_node("estimar_presupuesto", nodo_estimar_presupuesto)
    builder.add_node("aprobar_presupuesto", nodo_aprobar_presupuesto)
    builder.add_node("seleccionar_proveedor", nodo_seleccionar_proveedor)
    builder.add_node("notificar_produccion", nodo_notificar_produccion)

    # Aristas fijas
    builder.add_edge(START, "planificar_materiales")
    builder.add_edge("planificar_materiales", "estimar_presupuesto")
    builder.add_edge("estimar_presupuesto", "aprobar_presupuesto")

    # Arista condicional: aprobar → proveedor o → END
    builder.add_conditional_edges(
        "aprobar_presupuesto",
        _routing_aprobacion,
        {
            "seleccionar_proveedor": "seleccionar_proveedor",
            "__end__": END,
        },
    )

    builder.add_edge("seleccionar_proveedor", "notificar_produccion")
    builder.add_edge("notificar_produccion", END)

    # Checkpointer
    if checkpointer is None:
        try:
            from langgraph.checkpoint.memory import MemorySaver
            checkpointer = MemorySaver()
        except ImportError:
            checkpointer = None

    # Compilar con HITL (interrupt_before en aprobar_presupuesto)
    compile_kwargs = {}
    if checkpointer:
        compile_kwargs["checkpointer"] = checkpointer
    if enable_hitl:
        compile_kwargs["interrupt_before"] = ["aprobar_presupuesto"]

    graph = builder.compile(**compile_kwargs)
    return graph


def run_materials_flow(
    thread_id: str = "materials_default",
    graph=None,
    approved: bool = True,
) -> dict:
    """
    Ejecuta el flujo completo de compra de materiales.

    Args:
        thread_id: ID de sesión para checkpointing.
        graph: Grafo precompilado.
        approved: Si el presupuesto es aprobado (simula HITL).

    Returns:
        Estado final con resultados del proceso.
    """
    if graph is None:
        graph = create_materials_graph(enable_hitl=False)

    initial_state: EstadoPedido = {
        # Campos Proceso 1 (requeridos por TypedDict)
        "pregunta": "",
        "contexto": [],
        "plan": [],
        "respuesta": "",
        "iteraciones": 0,
        "datos_pedido": {},
        "etapa": "inicio_materiales",
        "historial": [],
        "necesita_mas": False,
        # Campos Proceso 2
        "pedido_validado": True,
        "cotizacion": {},
        "pago_confirmado": True,
        "lista_materiales": [],
        "presupuesto": 0.0,
        "presupuesto_aprobado": approved,
        "proveedor": "",
        "materiales_recibidos": False,
        "notificaciones": [],
        "estado_proceso": "iniciado",
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(initial_state, config=config)
    return result


def get_materials_graph_diagram() -> str:
    """Diagrama textual del grafo de materiales."""
    return """
    ┌──────────────────┐
    │      START        │
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ PLANIFICAR        │  Genera lista de materiales
    │ MATERIALES        │  desde pedidos pendientes
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ ESTIMAR           │  Calcula presupuesto con
    │ PRESUPUESTO       │  RAG + catálogo
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ APROBAR           │  ⚠️ HITL: interrupt_before
    │ PRESUPUESTO       │  Espera aprobación humana
    └────────┬─────────┘
             │
    ┌────────▼──────────────────┐
    │  ¿Aprobado?               │
    │  Sí → SELECCIONAR PROV.   │
    │  No → END (cancelado)     │
    └────────┬──────────────────┘
             │ (Sí)
    ┌────────▼─────────┐
    │ SELECCIONAR       │  Elige proveedor y
    │ PROVEEDOR         │  registra compra
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │ NOTIFICAR         │  Avisa a producción
    │ PRODUCCIÓN        │  que materiales llegaron
    └────────┬─────────┘
             │
    ┌────────▼─────────┐
    │       END         │
    └──────────────────┘
    """


# =============================================================================
# CLI
# =============================================================================
if __name__ == "__main__":
    import sys as _sys
    print("🏭 Proceso 2: Compra de Materiales")
    print(get_materials_graph_diagram())
    print("Ejecutando flujo...\n")
    result = run_materials_flow()
    print(f"📦 Materiales: {result.get('lista_materiales', [])}")
    print(f"💰 Presupuesto: S/ {result.get('presupuesto', 0):.2f}")
    print(f"✅ Aprobado: {result.get('presupuesto_aprobado', False)}")
    print(f"🏭 Proveedor: {result.get('proveedor', 'N/A')}")
    print(f"📢 Notificado: {result.get('materiales_recibidos', False)}")
    print(f"🔄 Estado: {result.get('estado_proceso', 'N/A')}")
