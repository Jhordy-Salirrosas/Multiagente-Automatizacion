"""
OrchestratorAgent — Coordinador central del sistema multiagente.

Implementa una topología jerárquica tipo estrella:

    PROCESO 1: Realizar Pedido
                            ┌─────────────────┐
                            │  Orchestrator   │
                            └────────┬────────┘
            ┌──────────┬─────────────┼─────────────┬──────────┐
            ▼          ▼             ▼             ▼          ▼
        Validator  DataCollector  Pricing      Registry    Notifier

    PROCESO 2: Compra de Materiales
                            ┌─────────────────┐
                            │  Orchestrator   │
                            └────────┬────────┘
            ┌──────────┬─────────────┼──────────────┬──────────┐
            ▼          ▼             ▼              ▼          ▼
      MaterialPlanner  Budget    Approval(HITL)  Supplier  Production

El Orchestrator NO es un LLM por sí mismo: es una máquina de estados
determinística que decide qué subagente invocar en cada turno según el
ConversationStage actual. Esto garantiza un flujo predecible y permite
resolver conflictos de forma explícita.
"""
from __future__ import annotations
from typing import Optional

from agents.base import BaseAgent
from agents.validator import ValidatorAgent
from agents.data_collector import DataCollectorAgent
from agents.pricing import PricingAgent
from agents.registry import RegistryAgent
from agents.notifier import NotifierAgent

# Proceso 2: Compra de Materiales
from agents.material_planner import MaterialPlannerAgent
from agents.budget_agent import BudgetAgent
from agents.approval_agent import ApprovalAgent
from agents.supplier_agent import SupplierAgent
from agents.production_agent import ProductionAgent

from core.mcp_messages import AgentName, MCPMessage, MessageType
from core.shared_state import SharedState, ConversationStage
from core.event_bus import event_bus


class Orchestrator:
    """
    Coordinador. NO hereda de BaseAgent porque no necesita LLM; su
    responsabilidad es ENRUTAR mensajes a los subagentes especializados.
    """
    validator: ValidatorAgent
    data_collector: DataCollectorAgent
    pricing: PricingAgent
    registry: RegistryAgent
    notifier: NotifierAgent
    material_planner: MaterialPlannerAgent
    budget_agent: BudgetAgent
    approval_agent: ApprovalAgent
    supplier_agent: SupplierAgent
    production_agent: ProductionAgent

    def __init__(self):
        # Proceso 1: 5 subagentes de pedidos
        self.validator = ValidatorAgent()
        self.data_collector = DataCollectorAgent()
        self.pricing = PricingAgent()
        self.registry = RegistryAgent()
        self.notifier = NotifierAgent()

        # Proceso 2: 5 subagentes de compra de materiales
        self.material_planner = MaterialPlannerAgent()
        self.budget_agent = BudgetAgent()
        self.approval_agent = ApprovalAgent()
        self.supplier_agent = SupplierAgent()
        self.production_agent = ProductionAgent()

        # Suscribirnos a eventos relevantes (event bus)
        event_bus.subscribe("validation_completed", self._on_validation_completed)
        event_bus.subscribe("data_collection_completed", self._on_data_collection_completed)
        event_bus.subscribe("quote_generated", self._on_quote_generated)
        event_bus.subscribe("materials_planned", self._on_materials_planned)
        event_bus.subscribe("budget_estimated", self._on_budget_estimated)
        event_bus.subscribe("budget_approved", self._on_budget_approved)
        event_bus.subscribe("purchase_completed", self._on_purchase_completed)
        event_bus.subscribe("production_notified", self._on_production_notified)

    # =========================================================================
    # PUNTO DE ENTRADA Proceso 1: cada mensaje del usuario pasa por aquí
    # =========================================================================
    def handle_user_message(self, user_message: str, state: SharedState) -> str:
        """
        Recibe un mensaje del usuario, decide a qué agente invocar según el
        estado actual y devuelve la respuesta para mostrar al usuario.
        """
        # 1) Interceptar intento de rastreo de pedidos
        import re
        if re.search(r"PED-\d{8}-\d{6}", user_message, re.IGNORECASE) or "estado de mi pedido" in user_message.lower():
            from agents.tracking_agent import TrackingAgent
            tracker = TrackingAgent()
            reply = tracker.track(user_message, state)
            state.append_user_message(user_message)
            state.append_assistant_message(reply)
            return reply

        state.append_user_message(user_message)
        # Registrar mensaje USER → ORCHESTRATOR
        state.append_message(MCPMessage(
            sender=AgentName.USER,
            receiver=AgentName.ORCHESTRATOR,
            message_type=MessageType.USER_INPUT,
            payload={"content": user_message},
        ))

        # Si está en INITIAL, transicionar a VALIDATING
        if state.stage == ConversationStage.INITIAL:
            state.transition_to(ConversationStage.VALIDATING)

        # Enrutar según etapa
        if state.stage == ConversationStage.VALIDATING:
            reply = self._handle_validation(user_message, state)
        elif state.stage == ConversationStage.COLLECTING_DATA:
            reply = self._handle_data_collection(user_message, state)
        elif state.stage == ConversationStage.WAITING_CONFIRMATION:
            reply = self._handle_confirmation(user_message, state)
        elif state.stage == ConversationStage.COMPLETE:
            reply = "[OK] Tu pedido ya fue procesado. ¡Gracias!"
        elif state.stage == ConversationStage.REJECTED:
            reply = "Lo siento, no podemos atender ese tipo de pedido. ¡Gracias por contactarnos!"
        else:
            reply = "Procesando…"

        state.append_assistant_message(reply)
        state.append_message(MCPMessage(
            sender=AgentName.ORCHESTRATOR,
            receiver=AgentName.USER,
            message_type=MessageType.USER_OUTPUT,
            payload={"content": reply},
        ))
        return reply

    # =========================================================================
    # HANDLERS Proceso 1: Realizar Pedido
    # =========================================================================
    def _handle_validation(self, user_message: str, state: SharedState) -> str:
        """Invoca ValidatorAgent."""
        result = self.validator.validate(user_message, state)  # type: ignore
        if not result.is_textile:
            state.transition_to(ConversationStage.REJECTED)
            return (
                "Lo siento, atendemos únicamente pedidos del rubro textil "
                f"(confección de ropa). {result.reason}\n"
                "¡Gracias por contactarnos!"
            )
        # Si pasó la validación, dejamos que DataCollector procese el mensaje
        self.data_collector.collect(user_message, state)  # type: ignore
        state.transition_to(ConversationStage.COLLECTING_DATA)
        return (
            "¡Hola! Qué gusto saludarte. Has llegado al lugar indicado, "
            "nos encantará ayudarte con tu pedido textil. Para poder brindarte "
            "una cotización exacta al instante, he habilitado un breve formulario "
            "aquí abajo. Por favor, complétalo 👇"
        )

    def _handle_data_collection(self, user_message: str, state: SharedState) -> str:
        """Invoca DataCollectorAgent."""
        _, reply, is_complete = self.data_collector.collect(user_message, state)  # type: ignore
        if is_complete:
            state.transition_to(ConversationStage.QUOTING)
            quote = self.pricing.quote(state.order_data, state)  # type: ignore
            state.transition_to(ConversationStage.WAITING_CONFIRMATION)
            return f"{reply}\n\n{quote.resumen_texto}"
        return reply

    def _handle_confirmation(self, user_message: str, state: SharedState) -> str:
        """Espera 'sí/confirmo' para registrar y notificar."""
        msg = user_message.lower().strip()
        afirmaciones = {"si", "sí", "confirmo", "ok", "dale", "acepto", "de acuerdo",
                        "está bien", "esta bien", "yes", "confirmar", "perfecto"}
        negaciones = {"no", "cancelar", "no quiero", "rechazar"}

        if any(neg in msg for neg in negaciones):
            state.transition_to(ConversationStage.REJECTED)
            return "Entendido, hemos cancelado el pedido. ¡Gracias por tu tiempo!"

        if any(afir in msg for afir in afirmaciones) or "confirm" in msg:
            state.transition_to(ConversationStage.REGISTERING)
            reg = self.registry.register(state)  # type: ignore
            state.transition_to(ConversationStage.NOTIFYING)
            notif = self.notifier.notify(state)  # type: ignore
            state.transition_to(ConversationStage.COMPLETE)
            assert state.quote_result is not None
            return (
                f"### ¡Felicidades! Tu pedido ha sido confirmado 🎉\n\n"
                f"**Detalles de tu orden:**\n"
                f"- **🆔 ID de Pedido:** `{reg.pedido_id}`\n"
                f"- **📧 Constancia:** Enviada exitosamente a `{notif.destinatario}`\n"
                f"- **💰 Adelanto Requerido:** **S/ {state.quote_result.adelanto:.2f}**\n\n"
                f"---\n"
                f"💡 *Para iniciar la producción inmediatamente, por favor realiza el abono del adelanto. ¡Gracias por confiar en nosotros!*"
            )

        return "Por favor confirma con un 'sí' para continuar, o 'no' para cancelar."

    # =========================================================================
    # FORMULARIO: procesa los 8 datos de un golpe (sin chat largo)
    # =========================================================================
    def handle_form_submission(self, form_data: dict, state: SharedState) -> str:
        """
        Procesa los 8 datos del pedido enviados desde el formulario interactivo.
        Salta la etapa COLLECTING_DATA y va directo a QUOTING → WAITING_CONFIRMATION.
        """
        from core.mcp_messages import MCPMessage, MessageType, AgentName

        state.append_message(MCPMessage(
            sender=AgentName.USER,
            receiver=AgentName.ORCHESTRATOR,
            message_type=MessageType.USER_INPUT,
            payload={"type": "form_submission", "data": form_data},
        ))
        state.update_order_data(**form_data)

        from core.event_bus import event_bus
        from core.mcp_messages import AgentName as AN
        event_bus.emit(AN.DATA_COLLECTOR, "data_collection_completed",
                       data=state.order_data.model_dump(), method="form")

        state.transition_to(ConversationStage.QUOTING)
        quote = self.pricing.quote(state.order_data, state)  # type: ignore
        state.transition_to(ConversationStage.WAITING_CONFIRMATION)

        nombre_cliente = form_data.get('nombre', '').split()[0] if form_data.get('nombre') else 'Cliente'
        
        reply = (
            f"¡Perfecto **{nombre_cliente}**! Hemos recibido tus datos correctamente.\n\n"
            f"{quote.resumen_texto}"
        )
        
        state.append_assistant_message(reply)
        state.append_message(MCPMessage(
            sender=AgentName.ORCHESTRATOR,
            receiver=AgentName.USER,
            message_type=MessageType.USER_OUTPUT,
            payload={"content": reply, "type": "quote_after_form"},
        ))
        return reply

    # =========================================================================
    # PROCESO 2: Compra de Materiales
    # =========================================================================
    def handle_materials_purchase(self, state: SharedState) -> dict:
        """
        Ejecuta el flujo de compra de materiales hasta la aprobación HITL:
        1. MaterialPlannerAgent → lista de materiales
        2. BudgetAgent → presupuesto estimado
        3. ApprovalAgent → preparar para aprobación humana

        Retorna dict con resultados para que la UI muestre info de aprobación.
        """
        results = {"etapas": []}

        # Paso 1: Planificar materiales
        state.transition_to(ConversationStage.PLANNING_MATERIALS)
        material_plan = self.material_planner.plan(state)  # type: ignore
        results["etapas"].append("✅ Materiales planificados y verificados contra almacén")
        results["material_plan"] = {
            "materiales": material_plan.materiales,
            "cantidades": material_plan.cantidades,
            "en_stock": material_plan.en_stock,
            "a_comprar": material_plan.a_comprar,
        }

        # Paso 2: Estimar presupuesto
        state.transition_to(ConversationStage.ESTIMATING_BUDGET)
        budget = self.budget_agent.estimate(state)  # type: ignore
        results["etapas"].append("✅ Presupuesto estimado")
        results["budget"] = {
            "presupuesto_estimado": budget.presupuesto_estimado,
            "proveedor_recomendado": budget.proveedor_recomendado,
            "justificacion": budget.justificacion,
            "razonamiento": budget.razonamiento,
        }

        # Paso 3: Preparar aprobación HITL
        state.transition_to(ConversationStage.WAITING_BUDGET_APPROVAL)
        explanation = self.approval_agent.prepare_approval(state)  # type: ignore
        results["etapas"].append("⏳ Esperando aprobación del presupuesto")
        results["approval_explanation"] = explanation

        return results

    def handle_budget_approval(self, approved: bool, state: SharedState) -> dict:
        """
        Procesa la decisión de aprobación/rechazo del presupuesto.
        Si aprobado → comprar → notificar producción.
        Si rechazado → cancelar.
        """
        results = {"etapas": []}

        self.approval_agent.process_decision(approved, state)  # type: ignore

        if not approved:
            state.transition_to(ConversationStage.PURCHASE_COMPLETE)
            results["etapas"].append("❌ Presupuesto rechazado")
            results["estado"] = "cancelado"
            return results

        results["etapas"].append("✅ Presupuesto aprobado")

        # Paso 4: Seleccionar proveedor y comprar
        state.transition_to(ConversationStage.PURCHASING)
        purchase = self.supplier_agent.select_and_purchase(state)  # type: ignore
        
        # Como emitimos eventos globalmente pero aquí queremos capturarlos síncronamente,
        # lo más fácil es pasarlos si purchase fue por alternativo:
        if purchase.proveedor == "Textiles del Norte SAC" or "Alternativo" in purchase.proveedor:
            results["etapas"].append("⚠️ **ALERTA:** Proveedor principal sin stock o no responde.")
            results["etapas"].append("🔄 **Ruta Alternativa:** Redirigiendo compra a proveedor de respaldo...")
            
        results["etapas"].append(f"✅ Compra registrada con: **{purchase.proveedor}**")
        results["purchase"] = {
            "orden_compra_id": purchase.orden_compra_id,
            "proveedor": purchase.proveedor,
            "fecha_entrega": purchase.fecha_entrega,
            "monto_total": purchase.monto_total,
        }

        # Paso 5: Notificar producción
        state.transition_to(ConversationStage.NOTIFYING_PRODUCTION)
        notif = self.production_agent.notify_production(state)  # type: ignore
        results["etapas"].append("✅ Producción notificada")
        results["notificacion"] = notif

        state.transition_to(ConversationStage.PURCHASE_COMPLETE)
        results["estado"] = "completado"
        return results

    # =========================================================================
    # Event handlers (suscripciones al event bus)
    # =========================================================================
    @staticmethod
    def _on_validation_completed(event) -> None:
        pass

    @staticmethod
    def _on_data_collection_completed(event) -> None:
        pass

    @staticmethod
    def _on_quote_generated(event) -> None:
        pass

    @staticmethod
    def _on_materials_planned(event) -> None:
        pass

    @staticmethod
    def _on_budget_estimated(event) -> None:
        pass

    @staticmethod
    def _on_budget_approved(event) -> None:
        pass

    @staticmethod
    def _on_purchase_completed(event) -> None:
        pass

    @staticmethod
    def _on_production_notified(event) -> None:
        pass
