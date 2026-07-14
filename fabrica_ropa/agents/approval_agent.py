"""
ApprovalAgent — Genera explicación para aprobación humana del presupuesto (§3.5 HITL).

Este agente prepara la información del presupuesto de forma clara para que
un responsable humano pueda aprobar o rechazar la compra de materiales.
Implementa el patrón Human-in-the-Loop (HITL).
"""
import json
from typing import Optional

from agents.base import BaseAgent
from core.mcp_messages import AgentName, BudgetResult, MaterialPlan
from core.shared_state import SharedState


SYSTEM_PROMPT = """Eres un asistente especializado en validar presupuestos de compra de materiales
para una fábrica de ropa.

INSTRUCCIONES:
- Genera una explicación clara y concisa del presupuesto estimado.
- Incluye el desglose de materiales, costos y proveedor recomendado.
- Destaca cualquier variación significativa respecto a compras anteriores.
- Facilita la toma de decisión del responsable.
- Responde en texto plano, sin JSON.
"""


class ApprovalAgent(BaseAgent):
    """
    Agente de aprobación de presupuesto.
    Genera la explicación para HITL y procesa la decisión.
    """

    def __init__(self):
        super().__init__(
            agent_name=AgentName.APPROVAL,
            system_prompt=SYSTEM_PROMPT,
        )

    def prepare_approval(self, state: SharedState) -> str:
        """
        Prepara el resumen del presupuesto para aprobación humana.

        Returns:
            Texto explicativo para el responsable.
        """
        budget = state.budget_result
        material_plan = state.material_plan

        if not budget:
            return "No hay presupuesto para aprobar."

        # Generar explicación con LLM
        prompt = (
            f"Genera una explicación clara del presupuesto para aprobación:\n"
            f"Presupuesto total: S/ {budget.presupuesto_estimado:.2f}\n"
            f"Proveedor recomendado: {budget.proveedor_recomendado}\n"
            f"Justificación: {budget.justificacion}\n"
            f"Materiales: {material_plan.materiales if material_plan else 'N/A'}\n"
            f"Cantidades: {material_plan.cantidades if material_plan else 'N/A'}\n\n"
            f"Genera un resumen ejecutivo para que el responsable apruebe o rechace."
        )
        raw = self.run(prompt, state)
        explanation = self.extract_agent_text(raw).strip()

        if not explanation or len(explanation) < 20:
            explanation = self._format_fallback(budget, material_plan)

        return explanation

    def process_decision(self, approved: bool, state: SharedState) -> Optional[BudgetResult]:
        """
        Procesa la decisión de aprobación/rechazo del presupuesto.

        Args:
            approved: True si el responsable aprobó, False si rechazó.
            state: Estado compartido.

        Returns:
            BudgetResult actualizado.
        """
        if state.budget_result:
            state.budget_result.estado = "Aprobado" if approved else "Rechazado"
            event_name = "budget_approved" if approved else "budget_rejected"
            self.emit_event(
                event_name,
                presupuesto=state.budget_result.presupuesto_estimado,
            )
        return state.budget_result

    @staticmethod
    def _format_fallback(budget: BudgetResult, material_plan: Optional[MaterialPlan]) -> str:
        """Resumen sin LLM."""
        mats = ""
        if material_plan:
            for m, c in zip(material_plan.materiales, material_plan.cantidades):
                mats += f"  • {m}: {c} unidades\n"

        return (
            f"📋 **Resumen de presupuesto para aprobación**\n\n"
            f"💰 **Presupuesto total:** S/ {budget.presupuesto_estimado:.2f}\n"
            f"🏭 **Proveedor recomendado:** {budget.proveedor_recomendado}\n\n"
            f"📦 **Materiales requeridos:**\n{mats}\n"
            f"📝 **Justificación:** {budget.justificacion}\n\n"
            f"¿Aprueba este presupuesto para proceder con la compra?"
        )

    def _default_mock_response(self, prompt: str) -> str:
        import re
        monto = "0.00"
        match = re.search(r"S/\s*([0-9.,]+)", prompt)
        if match:
            monto = match.group(1)
        
        return (
            f"El presupuesto de S/ {monto} ha sido analizado por el sistema basándose "
            f"en el cruce de datos con el Almacén Inteligente. Las cantidades solicitadas "
            f"se han ajustado para priorizar el stock existente, maximizando el ahorro de la empresa. "
            f"El proveedor recomendado tiene un historial de cumplimiento sobresaliente. ¿Desea aprobar esta operación?"
        )
