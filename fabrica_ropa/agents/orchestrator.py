"""
OrchestratorAgent — Coordinador central del sistema multiagente.

Implementa una topología jerárquica tipo estrella:
                            ┌─────────────────┐
                            │  Orchestrator   │
                            └────────┬────────┘
            ┌──────────┬─────────────┼─────────────┬──────────┐
            ▼          ▼             ▼             ▼          ▼
        Validator  DataCollector  Pricing      Registry    Notifier

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

from core.mcp_messages import AgentName, MCPMessage, MessageType
from core.shared_state import SharedState, ConversationStage
from core.event_bus import event_bus


class Orchestrator:
    """
    Coordinador. NO hereda de BaseAgent porque no necesita LLM; su
    responsabilidad es ENRUTAR mensajes a los subagentes especializados.
    """

    def __init__(self):
        # Instanciamos los 5 subagentes especializados
        self.validator = ValidatorAgent()
        self.data_collector = DataCollectorAgent()
        self.pricing = PricingAgent()
        self.registry = RegistryAgent()
        self.notifier = NotifierAgent()

        # Suscribirnos a eventos relevantes (event bus)
        event_bus.subscribe("validation_completed", self._on_validation_completed)
        event_bus.subscribe("data_collection_completed", self._on_data_collection_completed)
        event_bus.subscribe("quote_generated", self._on_quote_generated)

    # =========================================================================
    # PUNTO DE ENTRADA: cada mensaje del usuario pasa por aquí
    # =========================================================================
    def handle_user_message(self, user_message: str, state: SharedState) -> str:
        """
        Recibe un mensaje del usuario, decide a qué agente invocar según el
        estado actual y devuelve la respuesta para mostrar al usuario.
        """
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
    # HANDLERS por etapa
    # =========================================================================
    def _handle_validation(self, user_message: str, state: SharedState) -> str:
        """Invoca ValidatorAgent."""
        result = self.validator.validate(user_message, state)
        if not result.is_textile:
            state.transition_to(ConversationStage.REJECTED)
            return (
                "Lo siento, atendemos únicamente pedidos del rubro textil "
                f"(confección de ropa). {result.reason}\n"
                "¡Gracias por contactarnos!"
            )
        # Si pasó la validación, dejamos que DataCollector procese el mismo
        # mensaje (puede traer datos útiles ya)
        state.transition_to(ConversationStage.COLLECTING_DATA)
        return self._handle_data_collection(user_message, state)

    def _handle_data_collection(self, user_message: str, state: SharedState) -> str:
        """Invoca DataCollectorAgent."""
        _, reply, is_complete = self.data_collector.collect(user_message, state)
        if is_complete:
            # Transicionar a cotización y generarla ya
            state.transition_to(ConversationStage.QUOTING)
            quote = self.pricing.quote(state.order_data, state)
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
            # Registrar
            state.transition_to(ConversationStage.REGISTERING)
            reg = self.registry.register(state)
            # Notificar
            state.transition_to(ConversationStage.NOTIFYING)
            notif = self.notifier.notify(state)
            state.transition_to(ConversationStage.COMPLETE)
            assert state.quote_result is not None
            return (
                f"✅ Pedido registrado con ID: **{reg.pedido_id}**\n"
                f"📧 Constancia enviada a {notif.destinatario}\n"
                f"📁 (Demo) Archivo HTML: {notif.archivo_html}\n\n"
                f"Por favor abona el adelanto de S/ {state.quote_result.adelanto:.2f} "
                "para iniciar la producción. ¡Gracias!"
            )

        return "Por favor confirma con un 'sí' para continuar, o 'no' para cancelar."

    # =========================================================================
    # FORMULARIO: procesa los 8 datos de un golpe (sin chat largo)
    # =========================================================================
    def handle_form_submission(self, form_data: dict, state: SharedState) -> str:
        """
        Procesa los 8 datos del pedido enviados desde el formulario interactivo.
        Salta la etapa COLLECTING_DATA y va directo a QUOTING → WAITING_CONFIRMATION.

        Args:
            form_data: Dict con los 8 campos del pedido.
            state: Estado compartido.

        Returns:
            Respuesta con la cotización para mostrar al usuario.
        """
        from core.mcp_messages import MCPMessage, MessageType, AgentName

        # 1) Registrar el envío del formulario como mensaje MCP
        state.append_message(MCPMessage(
            sender=AgentName.USER,
            receiver=AgentName.ORCHESTRATOR,
            message_type=MessageType.USER_INPUT,
            payload={"type": "form_submission", "data": form_data},
        ))

        # 2) Llenar los 8 datos de un golpe en el estado
        state.update_order_data(**form_data)

        # 3) Emitir evento de recolección completada
        from core.event_bus import event_bus
        from core.mcp_messages import AgentName as AN
        event_bus.emit(AN.DATA_COLLECTOR, "data_collection_completed",
                       data=state.order_data.model_dump(), method="form")

        # 4) Transicionar a cotización directamente
        state.transition_to(ConversationStage.QUOTING)
        quote = self.pricing.quote(state.order_data, state)

        # 5) Pasar a espera de confirmación
        state.transition_to(ConversationStage.WAITING_CONFIRMATION)

        # 6) Generar respuesta
        resumen_form = (
            "📋 **Datos del pedido recibidos:**\n"
            f"• **{form_data.get('tipo_prenda', '')}** × {form_data.get('cantidad', 0)} unidades\n"
            f"• Talla: {form_data.get('talla', '')} · Color: {form_data.get('color', '')}\n"
            f"• Acabado: {form_data.get('acabado', 'ninguno')}\n"
            f"• Cliente: {form_data.get('nombre', '')} ({form_data.get('email', '')})\n"
            f"• Entrega: {form_data.get('fecha_entrega', '')}\n\n"
        )

        reply = resumen_form + quote.resumen_texto

        state.append_assistant_message(reply)
        state.append_message(MCPMessage(
            sender=AgentName.ORCHESTRATOR,
            receiver=AgentName.USER,
            message_type=MessageType.USER_OUTPUT,
            payload={"content": reply, "type": "quote_after_form"},
        ))
        return reply

    # =========================================================================
    # Event handlers (suscripciones al event bus)
    # =========================================================================
    @staticmethod
    def _on_validation_completed(event) -> None:
        # Hook de auditoría; podríamos loguear a archivo, métricas, etc.
        pass

    @staticmethod
    def _on_data_collection_completed(event) -> None:
        pass

    @staticmethod
    def _on_quote_generated(event) -> None:
        pass
