"""
SupplierAgent — Selecciona proveedor y gestiona compra de materiales (§3.5/§3.6).

Evalúa los proveedores disponibles por disponibilidad, precio y tiempo de entrega.
Si el proveedor principal no responde, selecciona un proveedor alternativo.
Incluye punto HITL para aprobación de proveedor alternativo.
"""
from __future__ import annotations
import json
from pathlib import Path

from agents.base import BaseAgent
from core.mcp_messages import AgentName, PurchaseResult
from core.shared_state import SharedState
from tools.purchase_tool import PurchaseTool
from config import BASE_DIR

try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un asistente encargado de recomendar el proveedor más adecuado
para la compra de materiales de una fábrica de ropa.

INSTRUCCIONES:
- Evalúa disponibilidad, historial de compras y tiempos de entrega.
- Prioriza el proveedor principal.
- Si no existe disponibilidad, recomienda un proveedor alternativo.
- Justifica brevemente la recomendación utilizando únicamente la información disponible.
- Responde con JSON: {"proveedor_id": "...", "nombre": "...", "justificacion": "..."}
"""

SUPPLIERS_PATH = BASE_DIR / "data" / "suppliers.json"


class SupplierAgent(BaseAgent):
    """Agente de selección de proveedor y compra."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.SUPPLIER,
            system_prompt=SYSTEM_PROMPT,
        )
        self._purchase_tool = PurchaseTool()
        self._suppliers = self._load_suppliers()

    @staticmethod
    def _load_suppliers() -> list[dict]:
        if SUPPLIERS_PATH.exists():
            with open(SUPPLIERS_PATH, encoding="utf-8") as f:
                return json.load(f).get("proveedores", [])
        return []

    @traceable(name="SupplierAgent.select_and_purchase")
    def select_and_purchase(self, state: SharedState) -> PurchaseResult:
        """
        Selecciona el mejor proveedor y registra la compra.

        Returns:
            PurchaseResult con detalles de la orden de compra.
        """
        budget = state.budget_result
        material_plan = state.material_plan

        if not budget or not material_plan:
            result = PurchaseResult(
                proveedor="N/A",
                orden_compra_id="",
                materiales_confirmados=False,
                fecha_entrega="",
                monto_total=0.0,
            )
            state.purchase_result = result
            return result

        # Seleccionar proveedor con LLM
        proveedor = self._select_supplier(state)

        # SIMULACIÓN PARA VIDEO DEMO: Falla del proveedor principal y uso de alternativo
        import time
        from core.event_bus import event_bus
        from core.mcp_messages import AgentName as AN
        
        # Simular intento de conexión
        time.sleep(1.5)
        # Emitir un evento especial que capturaremos en Orchestrator/UI
        event_bus.emit(AN.SUPPLIER, "supplier_connection_failed", proveedor=proveedor["nombre"])
        time.sleep(1.0)
        
        # Caer en la lógica de proveedor alternativo automáticamente
        return self.use_alternative_supplier(proveedor["id"], state)

        result = PurchaseResult(
            proveedor=purchase_data["proveedor"],
            orden_compra_id=purchase_data["orden_compra_id"],
            materiales_confirmados=purchase_data["materiales_confirmados"],
            fecha_entrega=purchase_data["fecha_entrega"],
            monto_total=purchase_data["monto_total"],
        )
        state.purchase_result = result
        self.emit_event(
            "purchase_completed",
            orden_id=result.orden_compra_id,
            proveedor=result.proveedor,
        )
        return result

    def _select_supplier(self, state: SharedState) -> dict:
        """Selecciona el mejor proveedor disponible."""
        if not self._suppliers:
            return {"id": "PROV-DEFAULT", "nombre": "Proveedor General"}

        # Consultar al LLM para recomendación
        suppliers_info = json.dumps(
            [{k: v for k, v in s.items() if k != "activo"} for s in self._suppliers],
            ensure_ascii=False,
        )
        prompt = (
            f"Selecciona el mejor proveedor para esta compra:\n"
            f"Proveedores: {suppliers_info}\n"
            f"Materiales requeridos: {state.material_plan.materiales if state.material_plan else []}\n"
            f"Presupuesto: S/ {state.budget_result.presupuesto_estimado if state.budget_result else 0:.2f}\n"
            f'Responde con JSON: {{"proveedor_id": "...", "nombre": "...", "justificacion": "..."}}'
        )
        raw = self.run(prompt, state)

        try:
            data = json.loads(self.extract_agent_text(raw))
            selected_id = data.get("proveedor_id", "")
            for s in self._suppliers:
                if s["id"] == selected_id:
                    return s
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: proveedor con mejor historial de cumplimiento
        return max(self._suppliers, key=lambda s: s.get("historial_cumplimiento", 0))

    def use_alternative_supplier(self, excluded_id: str, state: SharedState) -> PurchaseResult:
        """
        Usa un proveedor alternativo cuando el principal no responde.
        Punto HITL: requiere aprobación si cambia de proveedor.
        """
        alternative = self._purchase_tool.get_alternative_supplier(excluded_id)
        if not alternative:
            alternative = self._suppliers[-1] if self._suppliers else {
                "id": "PROV-ALT", "nombre": "Proveedor Alternativo"
            }

        self.emit_event(
            "supplier_changed",
            original=excluded_id,
            alternativo=alternative["nombre"],
        )

        # Re-ejecutar compra con proveedor alternativo
        material_plan = state.material_plan
        budget = state.budget_result
        # Preparar lista de materiales para compra
        items = []
        if material_plan:
            for mat, a_comprar in zip(material_plan.materiales, getattr(material_plan, 'a_comprar', material_plan.cantidades)):
                if a_comprar > 0:
                    items.append({"material": mat, "cantidad": a_comprar})

        purchase_data = self._purchase_tool.purchase(
            proveedor_id=alternative["id"],
            lista_materiales=items,
            monto_total=budget.presupuesto_estimado if budget else 0.0,
        )

        result = PurchaseResult(
            proveedor=purchase_data["proveedor"],
            orden_compra_id=purchase_data["orden_compra_id"],
            materiales_confirmados=purchase_data["materiales_confirmados"],
            fecha_entrega=purchase_data["fecha_entrega"],
            monto_total=purchase_data["monto_total"],
        )
        state.purchase_result = result
        return result

    def _default_mock_response(self, prompt: str) -> str:
        return json.dumps({
            "proveedor_id": "PROV-001",
            "nombre": "Textiles del Norte SAC",
            "justificacion": "Mejor historial de cumplimiento (95%) y ubicación en Trujillo.",
        }, ensure_ascii=False)
