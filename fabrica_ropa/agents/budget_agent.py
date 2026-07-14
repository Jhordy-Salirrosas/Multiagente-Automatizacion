"""
BudgetAgent — Estima presupuesto de compra de materiales (§3.5/§3.6).

Analiza el historial de compras y los materiales requeridos para
calcular un presupuesto estimado. Usa RAG para consultar historial.
"""
import json

from agents.base import BaseAgent
from core.mcp_messages import AgentName, BudgetResult
from core.shared_state import SharedState
from tools.budget_tool import BudgetTool


SYSTEM_PROMPT = """Eres un asistente encargado de estimar el presupuesto para la compra de materiales
de una fábrica de ropa.

INSTRUCCIONES:
- Analiza el historial de compras recuperado mediante RAG.
- Calcula un presupuesto estimado considerando: precios históricos, variación de costos,
  cantidad requerida y proveedor habitual.
- Genera una explicación clara que justifique la estimación.
- Responde con JSON: {"presupuesto": 1234.56, "justificacion": "...", "proveedor_recomendado": "..."}
"""


class BudgetAgent(BaseAgent):
    """Agente de estimación de presupuesto."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.BUDGET,
            system_prompt=SYSTEM_PROMPT,
        )
        self._budget_tool = BudgetTool()

    def estimate(self, state: SharedState) -> BudgetResult:
        """
        Estima el presupuesto basado en el plan de materiales.

        Returns:
            BudgetResult con presupuesto estimado y proveedor recomendado.
        """
        material_plan = state.material_plan
        if not material_plan:
            result = BudgetResult(
                presupuesto_estimado=0.0,
                proveedor_recomendado="N/A",
                estado="Pendiente",
                justificacion="No hay plan de materiales disponible.",
            )
            state.budget_result = result
            return result

        # Construir lista de materiales para la tool (solo lo que falta comprar)
        items = []
        for mat, a_comprar in zip(material_plan.materiales, getattr(material_plan, 'a_comprar', material_plan.cantidades)):
            if a_comprar > 0:
                items.append({"material": mat, "cantidad": a_comprar})

        # Calcular presupuesto determinísticamente
        tool_result = self._budget_tool.estimate(items)

        # Usar RAG para enriquecer con historial
        contexto_rag = []
        try:
            from rag.retriever import retriever
            contexto_rag = retriever.query(
                "historial de compras materiales presupuesto proveedores", k=3
            )
        except Exception:
            pass

        contexto_text = "\n".join(contexto_rag[:3]) if contexto_rag else "Sin historial disponible."

        # Pedir justificación y razonamiento al LLM
        prompt = (
            f"Genera una justificación detallada del presupuesto estimado y explica paso a paso tu razonamiento.\n"
            f"Presupuesto: S/ {tool_result['presupuesto_estimado']:.2f}\n"
            f"Desglose: {json.dumps(tool_result['desglose'], ensure_ascii=False)}\n"
            f"Proveedor recomendado: {tool_result['proveedor_recomendado']}\n"
            f"Historial (RAG): {contexto_text[:500]}\n"
            f'Responde estrictamente con JSON: {{"justificacion": "resumen breve", "razonamiento": "Explicación detallada de cómo evaluaste los datos y el historial para elegir este proveedor..."}}'
        )
        raw = self.run(prompt, state)

        justificacion = f"Presupuesto estimado de S/ {tool_result['presupuesto_estimado']:.2f} basado en el catálogo de materiales."
        razonamiento = "Análisis del catálogo y selección del proveedor con mejor historial de cumplimiento."
        
        try:
            data = json.loads(self.extract_agent_text(raw))
            if "justificacion" in data:
                justificacion = data["justificacion"]
            if "razonamiento" in data:
                razonamiento = data["razonamiento"]
        except (json.JSONDecodeError, TypeError):
            clean = self.extract_agent_text(raw).strip()
            if len(clean) > 20:
                justificacion = clean

        result = BudgetResult(
            presupuesto_estimado=tool_result["presupuesto_estimado"],
            proveedor_recomendado=tool_result["proveedor_recomendado"],
            estado="Pendiente",
            justificacion=justificacion,
            razonamiento=razonamiento,
        )
        state.budget_result = result
        self.emit_event(
            "budget_estimated",
            presupuesto=result.presupuesto_estimado,
            proveedor=result.proveedor_recomendado,
        )
        return result

    def _default_mock_response(self, prompt: str) -> str:
        return json.dumps({
            "justificacion": (
                "Presupuesto calculado mediante el modelo predictivo de reposición. "
                "Se ha detectado una ruptura en el Stock de Seguridad (Safety Stock), "
                "por lo que se ha activado el Punto de Reorden para llenar la Capacidad Máxima del almacén."
            ),
            "razonamiento": (
                "【1】 Análisis de Demanda y Stock: Evalué el inventario proyectado tras la asignación al pedido.\n"
                "【2】 Dynamic Reorder Point: Detecté que el inventario proyectado cae por debajo del nivel de 'Stock de Seguridad' (Safety Stock) preestablecido.\n"
                "【3】 Optimización de Compra (Max Capacity): En lugar de comprar solo el déficit del pedido, el algoritmo determinó "
                "que es logísticamente más económico hacer una compra en volumen para reabastecer el almacén hasta su capacidad máxima.\n"
                "【4】 Selección de Proveedor: Crucé la cantidad masiva con los precios históricos en RAG y seleccioné a 'Textiles del Norte SAC' "
                "por su 95% de cumplimiento, minimizando riesgos en esta orden de gran volumen."
            )
        }, ensure_ascii=False)
