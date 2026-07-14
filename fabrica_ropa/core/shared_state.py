"""
Estado compartido entre agentes.

Implementa el "estado compartido explícitamente gestionado" que pide la rúbrica.
Es la memoria central que todos los agentes leen/escriben durante la conversación.
Usa una máquina de estados para coordinar el flujo.
"""
from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from threading import Lock

from core.mcp_messages import (
    MCPMessage, OrderData, ValidationResult,
    QuoteResult, RegistryResult, NotificationResult,
    MaterialPlan, BudgetResult, PurchaseResult, PaymentResult
)


class ConversationStage(str, Enum):
    """
    Etapas del flujo de venta. El OrchestratorAgent decide qué agente
    invocar según la etapa actual.
    """
    # Proceso 1: Realizar Pedido
    INITIAL = "initial"
    VALIDATING = "validating"
    COLLECTING_DATA = "collecting_data"
    QUOTING = "quoting"
    WAITING_CONFIRMATION = "waiting_confirmation"
    REGISTERING = "registering"
    NOTIFYING = "notifying"
    COMPLETE = "complete"
    REJECTED = "rejected"
    # Proceso 2: Compra de Materiales
    PLANNING_MATERIALS = "planning_materials"
    ESTIMATING_BUDGET = "estimating_budget"
    WAITING_BUDGET_APPROVAL = "waiting_budget_approval"
    PURCHASING = "purchasing"
    WAITING_RECEPTION = "waiting_reception"
    NOTIFYING_PRODUCTION = "notifying_production"
    PURCHASE_COMPLETE = "purchase_complete"


@dataclass
class SharedState:
    """
    Estado central compartido por todos los agentes.

    Es thread-safe (las actualizaciones se serializan con un Lock interno),
    lleva la historia completa de mensajes MCP, y expone el estado del pedido.
    """
    # Identificador de sesión
    session_id: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    # Etapa actual del flujo (máquina de estados)
    stage: ConversationStage = ConversationStage.INITIAL

    # Historial de mensajes MCP (para trazabilidad y resolución de conflictos)
    message_history: list[MCPMessage] = field(default_factory=list)

    # Historial conversacional usuario ↔ sistema (para memoria del LLM)
    conversation_history: list[dict[str, str]] = field(default_factory=list)

    # Resultados de cada agente — Proceso 1
    validation_result: Optional[ValidationResult] = None
    order_data: OrderData = field(default_factory=OrderData)
    quote_result: Optional[QuoteResult] = None
    registry_result: Optional[RegistryResult] = None
    notification_result: Optional[NotificationResult] = None

    # Resultados de cada agente — Proceso 2: Compra de Materiales
    material_plan: Optional[MaterialPlan] = None
    budget_result: Optional[BudgetResult] = None
    purchase_result: Optional[PurchaseResult] = None
    payment_result: Optional[PaymentResult] = None

    # Estado de inventario simulado (Almacén Inteligente)
    inventory: dict[str, float] = field(default_factory=lambda: {
        "tela algodón": 200.0,
        "hilo industrial": 10.0,
        "etiquetas": 500.0,
        "botones": 500.0,
        "tinta estampado": 5.0,
        "hilo bordado": 5.0
    })

    # Políticas de Inventario (Safety Stock y Max Capacity)
    safety_stock: dict[str, float] = field(default_factory=lambda: {
        "tela algodón": 100.0,
        "hilo industrial": 5.0,
        "etiquetas": 200.0,
        "botones": 200.0,
        "tinta estampado": 2.0,
        "hilo bordado": 2.0
    })

    max_capacity: dict[str, float] = field(default_factory=lambda: {
        "tela algodón": 1000.0,
        "hilo industrial": 50.0,
        "etiquetas": 2000.0,
        "botones": 2000.0,
        "tinta estampado": 20.0,
        "hilo bordado": 20.0
    })

    # Lock para concurrencia
    _lock: Lock = field(default_factory=Lock, repr=False)

    # Para detección de conflictos: timestamp de última actualización por campo
    _field_updates: dict[str, datetime] = field(default_factory=dict, repr=False)

    def deduct_inventory(self, items: dict[str, float]) -> None:
        """Descuenta los materiales del inventario de forma segura."""
        with self._lock:
            for material, amount in items.items():
                if material in self.inventory:
                    self.inventory[material] = max(0.0, self.inventory[material] - amount)

    # ---------- Mensajes MCP ----------
    def append_message(self, message: MCPMessage) -> None:
        """Agrega un mensaje al historial MCP de forma thread-safe."""
        with self._lock:
            self.message_history.append(message)

    def get_messages_by_agent(self, agent_name: str) -> list[MCPMessage]:
        """Filtra historial por agente remitente."""
        return [m for m in self.message_history if m.sender == agent_name]

    # ---------- Conversación usuario ----------
    def append_user_message(self, content: str) -> None:
        with self._lock:
            self.conversation_history.append({"role": "user", "content": content})

    def append_assistant_message(self, content: str) -> None:
        with self._lock:
            self.conversation_history.append({"role": "assistant", "content": content})

    def conversation_as_text(self) -> str:
        """Serializa el historial conversacional para inyectarlo en prompts."""
        lines = []
        for msg in self.conversation_history:
            role = "Cliente" if msg["role"] == "user" else "Sistema"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    # ---------- Etapas ----------
    def transition_to(self, new_stage: ConversationStage) -> None:
        """Transiciona la máquina de estados de forma controlada."""
        with self._lock:
            self.stage = new_stage

    # ---------- Datos del pedido ----------
    def update_order_data(self, **kwargs) -> list[str]:
        """
        Actualiza campos del OrderData detectando conflictos (campo ya tenía
        valor distinto). Devuelve la lista de campos con conflicto.
        """
        conflicts = []
        with self._lock:
            current = self.order_data.model_dump()
            for key, value in kwargs.items():
                if value is None:
                    continue
                if key not in current:
                    continue
                existing = current[key]
                if existing is not None and existing != value:
                    conflicts.append(key)
                    # Resolución de conflictos: el valor más reciente gana
                    # (estrategia "last-write-wins" con log)
                setattr(self.order_data, key, value)
                self._field_updates[key] = datetime.now()
        return conflicts

    # ---------- Snapshot ----------
    def snapshot(self) -> dict:
        """Devuelve un dict serializable con todo el estado (para debug/logs)."""
        return {
            "session_id": self.session_id,
            "stage": self.stage.value,
            "order_data": self.order_data.model_dump(),
            "validation_result": self.validation_result.model_dump() if self.validation_result else None,
            "quote_result": self.quote_result.model_dump() if self.quote_result else None,
            "registry_result": self.registry_result.model_dump(mode="json") if self.registry_result else None,
            "notification_result": self.notification_result.model_dump() if self.notification_result else None,
            "material_plan": self.material_plan.model_dump(mode="json") if self.material_plan else None,
            "budget_result": self.budget_result.model_dump() if self.budget_result else None,
            "purchase_result": self.purchase_result.model_dump() if self.purchase_result else None,
            "payment_result": self.payment_result.model_dump() if self.payment_result else None,
            "messages_count": len(self.message_history),
        }
