"""
ProductionAgent — Notifica al área de producción (§3.5/§3.6).

Confirma la recepción de materiales y envía una notificación formal
al área de producción para que inicie la fabricación.
"""
from __future__ import annotations
import json

from agents.base import BaseAgent
from core.mcp_messages import AgentName
from core.shared_state import SharedState
from tools.production_tool import ProductionTool

try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un asistente de comunicación interna de una fábrica de ropa.

INSTRUCCIONES:
- Genera notificaciones claras para el área de producción.
- Incluye los materiales recibidos, el proveedor y los pedidos asociados.
- El tono debe ser profesional e informativo.
- Responde en texto plano con la notificación.
"""


class ProductionAgent(BaseAgent):
    """Agente de notificación a producción."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.PRODUCTION,
            system_prompt=SYSTEM_PROMPT,
        )
        self._production_tool = ProductionTool()

    @traceable(name="ProductionAgent.notify_production")
    def notify_production(self, state: SharedState) -> dict:
        """
        Notifica a producción que los materiales están listos.

        Returns:
            Dict con confirmación y detalles.
        """
        purchase = state.purchase_result
        material_plan = state.material_plan

        if not purchase or not material_plan:
            return {
                "notificado": False,
                "mensaje": "No hay compra de materiales para notificar.",
            }

        # Generar notificación con LLM
        prompt = (
            f"Genera una notificación para el área de producción:\n"
            f"Orden de compra: {purchase.orden_compra_id}\n"
            f"Proveedor: {purchase.proveedor}\n"
            f"Materiales: {material_plan.materiales}\n"
            f"Fecha de entrega: {purchase.fecha_entrega}\n"
            f"Genera un mensaje profesional e informativo."
        )
        raw = self.run(prompt, state)
        mensaje_llm = self.extract_agent_text(raw).strip()

        # Registrar notificación con la tool
        pedido_ids = ["PLAN-SEMANAL"]  # En producción, serían los IDs reales
        result = self._production_tool.notify(
            pedido_ids=pedido_ids,
            materiales_recibidos=material_plan.materiales,
            orden_compra_id=purchase.orden_compra_id,
        )

        if mensaje_llm and len(mensaje_llm) > 20:
            result["mensaje_detallado"] = mensaje_llm

        self.emit_event(
            "production_notified",
            orden_id=purchase.orden_compra_id,
            materiales_count=len(material_plan.materiales),
        )

        return result

    def _default_mock_response(self, prompt: str) -> str:
        return (
            "📢 NOTIFICACIÓN A PRODUCCIÓN\n\n"
            "Los materiales de la última orden de compra han sido recibidos "
            "y verificados. Se puede iniciar la producción de los pedidos "
            "pendientes. Materiales disponibles: tela, hilo, botones, etiquetas."
        )
