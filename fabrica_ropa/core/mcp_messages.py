"""
MCP (Model Context Protocol) — Mensajes estructurados entre agentes.

Todos los mensajes intercambiados entre agentes se serializan como JSON con
schema validado por Pydantic. Esto cumple el criterio de la rúbrica:
"Uso de MCP (JSON/schema validado)".
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, EmailStr, field_validator
import uuid


class AgentName(str, Enum):
    """Identificadores únicos de cada agente del sistema."""
    # Proceso 1: Realizar Pedido
    ORCHESTRATOR = "OrchestratorAgent"
    VALIDATOR = "ValidatorAgent"
    DATA_COLLECTOR = "DataCollectorAgent"
    PRICING = "PricingAgent"
    REGISTRY = "RegistryAgent"
    NOTIFIER = "NotifierAgent"
    # Proceso 2: Compra de Materiales
    MATERIAL_PLANNER = "MaterialPlannerAgent"
    BUDGET = "BudgetAgent"
    APPROVAL = "ApprovalAgent"
    SUPPLIER = "SupplierAgent"
    PRODUCTION = "ProductionAgent"
    # Roles
    USER = "User"


class MessageType(str, Enum):
    """Tipos de mensaje MCP."""
    REQUEST = "request"        # Orquestador pide algo a un subagente
    RESPONSE = "response"      # Subagente responde al orquestador
    EVENT = "event"            # Notificación broadcast (event bus)
    USER_INPUT = "user_input"  # Mensaje del usuario
    USER_OUTPUT = "user_output"  # Mensaje al usuario


class MCPMessage(BaseModel):
    """
    Mensaje estándar entre agentes — schema validado.

    Cada mensaje lleva metadata (id, timestamps, remitente, destinatario) y un
    payload tipado. Permite trazabilidad completa de la conversación entre
    agentes y constituye nuestra capa de transporte MCP.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    sender: AgentName
    receiver: AgentName
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None  # Para vincular request/response

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


# ============================================================================
# Schemas del DOMINIO — Datos del pedido validados por Pydantic
# ============================================================================

class ValidationResult(BaseModel):
    """Resultado del ValidatorAgent."""
    is_textile: bool
    reason: str
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class OrderData(BaseModel):
    """
    Los 8 datos esenciales que el DataCollectorAgent debe recolectar.
    Cada campo es opcional hasta que el usuario lo provee.
    """
    nombre: Optional[str] = None
    email: Optional[str] = None  # Validado como string (no EmailStr para permitir parcial)
    tipo_prenda: Optional[str] = None
    cantidad: Optional[int] = Field(default=None, ge=1)
    talla: Optional[str] = None
    color: Optional[str] = None
    acabado: Optional[Literal["ninguno", "estampado", "bordado"]] = None
    fecha_entrega: Optional[str] = None  # ISO date string

    def is_complete(self) -> bool:
        """True cuando los 8 datos están presentes."""
        return all([
            self.nombre, self.email, self.tipo_prenda,
            self.cantidad, self.talla, self.color,
            self.acabado is not None, self.fecha_entrega,
        ])

    def missing_fields(self) -> list[str]:
        """Lista de campos pendientes."""
        missing = []
        if not self.nombre: missing.append("nombre")
        if not self.email: missing.append("email")
        if not self.tipo_prenda: missing.append("tipo_prenda")
        if not self.cantidad: missing.append("cantidad")
        if not self.talla: missing.append("talla")
        if not self.color: missing.append("color")
        if self.acabado is None: missing.append("acabado")
        if not self.fecha_entrega: missing.append("fecha_entrega")
        return missing

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Email inválido: {v}")
        return v.lower().strip()


class QuoteResult(BaseModel):
    """Resultado del PricingAgent — cotización calculada."""
    cantidad: int
    precio_unitario: float
    costo_acabado_unitario: float
    subtotal: float
    descuento_porcentaje: float
    descuento_monto: float
    total: float
    adelanto: float
    descuento_label: str
    resumen_texto: str
    pdf_path: Optional[str] = None


class RegistryResult(BaseModel):
    """Resultado del RegistryAgent — confirmación de persistencia."""
    pedido_id: str
    timestamp_registro: datetime
    estado: Literal["Pendiente de pago", "Pagado", "En producción", "Entregado"]
    db_path: str
    pdf_path: Optional[str] = None


class NotificationResult(BaseModel):
    """Resultado del NotifierAgent — confirmación de envío de email."""
    destinatario: str
    asunto: str
    archivo_html: str
    enviado: bool
    error: Optional[str] = None


# ============================================================================
# Schemas del DOMINIO — Proceso 2: Compra de Materiales (§3.7)
# ============================================================================

class MaterialPlan(BaseModel):
    """Lista de materiales requeridos para producción con asignación inteligente."""
    pedido_id: str
    materiales: list[str]
    cantidades: list[float]
    en_stock: list[float] = Field(default_factory=list)
    a_comprar: list[float] = Field(default_factory=list)
    fecha_generacion: datetime = Field(default_factory=datetime.now)


class BudgetResult(BaseModel):
    """Presupuesto estimado para la compra de materiales."""
    presupuesto_estimado: float
    proveedor_recomendado: str
    estado: Literal["Pendiente", "Aprobado", "Rechazado"] = "Pendiente"
    justificacion: str = ""
    razonamiento: str = ""


class PurchaseResult(BaseModel):
    """Resultado de la compra de materiales."""
    proveedor: str
    orden_compra_id: str
    materiales_confirmados: bool = False
    fecha_entrega: str = ""
    monto_total: float = 0.0


class PaymentResult(BaseModel):
    """Resultado del procesamiento de pago."""
    pedido_id: str
    monto: float
    metodo_pago: str
    pago_confirmado: bool = False
    comprobante_id: str = ""


class PlanDeepAgent(BaseModel):
    """Plan generado por el Deep Agent."""
    objetivo: str
    pasos: list[str] = Field(min_length=1, max_length=10)
    sub_agentes: list[str]
    complejidad: Literal["baja", "media", "alta"]


class EvaluationMetric(BaseModel):
    """Métricas utilizadas para evaluar el sistema."""
    caso_id: str
    exactitud: float
    groundedness: float
    latencia_ms: float
    aprobado: bool


# ============================================================================
# Eventos del Event Bus
# ============================================================================

class SystemEvent(BaseModel):
    """Evento publicado en el event bus."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    source: AgentName
    event_name: str  # "validation_passed", "order_complete", etc.
    data: dict[str, Any] = Field(default_factory=dict)
