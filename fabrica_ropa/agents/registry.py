"""
RegistryAgent — Persiste el pedido confirmado.

Encapsula la herramienta SheetsTool y genera un mensaje de confirmación
conciso para el cliente. La persistencia es determinística (SQL), el LLM
solo se usa para el mensaje al usuario.
"""
from __future__ import annotations
from datetime import datetime

from agents.base import BaseAgent
from core.mcp_messages import AgentName, RegistryResult
from core.shared_state import SharedState
from tools.sheets_tool import SheetsTool

# LangSmith tracing (§5.3)
try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un agente de registro. Recibes el ID de un pedido \
recién registrado y produces un mensaje BREVE (1-2 líneas) en español que \
confirma el registro al cliente. No incluyas JSON, solo texto."""


class RegistryAgent(BaseAgent):
    """Agente de persistencia."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.REGISTRY,
            system_prompt=SYSTEM_PROMPT,
        )
        self.sheets = SheetsTool()

    @traceable(name="RegistryAgent.register")
    def register(self, state: SharedState) -> RegistryResult:
        """Persiste el pedido en la base. Requiere order_data y quote_result completos."""
        order = state.order_data
        quote = state.quote_result
        if not order.is_complete() or quote is None:
            raise ValueError("No se puede registrar: faltan datos del pedido o cotización.")

        assert order.nombre and order.email and order.tipo_prenda and order.cantidad and order.talla and order.color and order.acabado and order.fecha_entrega
        pedido_id = self.sheets.append_row(
            session_id=state.session_id,
            nombre=order.nombre,
            email=order.email,
            tipo_prenda=order.tipo_prenda,
            cantidad=order.cantidad,
            talla=order.talla,
            color=order.color,
            acabado=order.acabado,
            fecha_entrega=order.fecha_entrega,
            subtotal=quote.subtotal,
            descuento_porc=quote.descuento_porcentaje,
            descuento_monto=quote.descuento_monto,
            total=quote.total,
            adelanto=quote.adelanto,
            estado="Pendiente de pago",
        )

        pdf_path = None
        try:
            from tools.pdf_tool import PDFTool
            pdf_tool = PDFTool()
            pdf_path = pdf_tool.generate_receipt_pdf(pedido_id, quote, order.nombre)
        except Exception as e:
            pass

        result = RegistryResult(
            pedido_id=pedido_id,
            timestamp_registro=datetime.now(),
            estado="Pendiente de pago",
            db_path=str(self.sheets.db_path),
            pdf_path=pdf_path,
        )
        state.registry_result = result
        self.emit_event("order_registered", pedido_id=pedido_id)
        return result

    def confirmation_message(self, pedido_id: str, state: SharedState) -> str:
        """Mensaje breve de confirmación al cliente (vía LLM, con fallback)."""
        prompt = f"Pedido registrado con ID: {pedido_id}. Genera mensaje de confirmación al cliente."
        raw = self.run(prompt, state)
        clean = self.extract_agent_text(raw).strip()
        if clean and len(clean) > 5:
            return clean
        return f"[OK] Pedido registrado. Tu ID es: {pedido_id}. Estado: Pendiente de pago."

    def _default_mock_response(self, prompt: str) -> str:
        return "Pedido registrado correctamente."
