"""
NotifierAgent — Generación y "envío" de constancia formal por email.

Construye el cuerpo HTML de la constancia con los datos del pedido y la
guarda en disco vía EmailTool (simulando Gmail).
"""
from __future__ import annotations

from agents.base import BaseAgent
from core.mcp_messages import AgentName, NotificationResult
from core.shared_state import SharedState
from tools.email_tool import EmailTool
from config import EMPRESA_NOMBRE


SYSTEM_PROMPT = """Eres un agente de notificación. Genera el CUERPO HTML \
(sin <html>, <head>, ni <body>; solo el contenido interno) de una \
constancia formal de pedido en español, profesional y limpio. Usa <h2>, <p>, \
<ul>, <table> según convenga. Devuelve SOLO el HTML, sin fences markdown."""


class NotifierAgent(BaseAgent):
    """Agente de notificación."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.NOTIFIER,
            system_prompt=SYSTEM_PROMPT,
        )
        self.email_tool = EmailTool()

    def notify(self, state: SharedState) -> NotificationResult:
        """Genera y envía el correo de constancia."""
        order = state.order_data
        quote = state.quote_result
        registry = state.registry_result
        if not all([order.is_complete(), quote, registry]):
            raise ValueError("Faltan datos para notificar.")

        # 1) Construir prompt detallado para el LLM
        prompt = self._build_prompt(state)
        raw = self.run(prompt, state)
        cuerpo_html = self.extract_agent_text(raw).strip()

        # 2) Fallback robusto: si el LLM no produce HTML suficientemente
        #    detallado (o estamos en mock simple), usamos el HTML completo
        #    construido determinísticamente desde el estado.
        if not cuerpo_html or "<" not in cuerpo_html or "<table" not in cuerpo_html.lower():
            cuerpo_html = self._fallback_html(state)

        # 3) "Enviar" (persistir)
        asunto = f"Constancia de pedido {registry.pedido_id} - {EMPRESA_NOMBRE}"
        try:
            ruta = self.email_tool.send(
                destinatario=order.email,
                asunto=asunto,
                cuerpo_html=cuerpo_html,
            )
            result = NotificationResult(
                destinatario=order.email,
                asunto=asunto,
                archivo_html=ruta,
                enviado=True,
            )
        except Exception as e:
            result = NotificationResult(
                destinatario=order.email,
                asunto=asunto,
                archivo_html="",
                enviado=False,
                error=str(e),
            )
        state.notification_result = result
        self.emit_event("notification_sent", destinatario=order.email, ok=result.enviado)
        return result

    @staticmethod
    def _build_prompt(state: SharedState) -> str:
        o = state.order_data
        q = state.quote_result
        r = state.registry_result
        return f"""Genera el HTML del cuerpo de la constancia con estos datos:

Pedido ID: {r.pedido_id}
Cliente: {o.nombre} ({o.email})
Producto: {o.cantidad}x {o.tipo_prenda} {o.color} talla {o.talla}, acabado {o.acabado}
Fecha de entrega: {o.fecha_entrega}
Subtotal: S/ {q.subtotal:.2f}
Descuento: {q.descuento_label} (-S/ {q.descuento_monto:.2f})
Total: S/ {q.total:.2f}
Adelanto requerido (50%): S/ {q.adelanto:.2f}
Estado: {r.estado}

Genera HTML limpio con un título "Constancia de Pedido", una tabla de detalles
y un párrafo final indicando próximos pasos (pagar el adelanto)."""

    @staticmethod
    def _fallback_html(state: SharedState) -> str:
        """HTML construido sin LLM (para mock/fallback)."""
        o = state.order_data
        q = state.quote_result
        r = state.registry_result
        return f"""
        <h2>Constancia de Pedido</h2>
        <p>Estimado(a) <strong>{o.nombre}</strong>,</p>
        <p>Confirmamos la recepción de su pedido <strong>{r.pedido_id}</strong>.</p>
        <table style="border-collapse:collapse;width:100%;margin:16px 0;">
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Producto</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">{o.tipo_prenda} {o.color}</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Cantidad</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">{o.cantidad} unidades (talla {o.talla})</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Acabado</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">{o.acabado}</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Fecha de entrega</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">{o.fecha_entrega}</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Subtotal</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">S/ {q.subtotal:.2f}</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Descuento</strong></td>
              <td style="padding:6px;border:1px solid #ddd;">{q.descuento_label} (-S/ {q.descuento_monto:.2f})</td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Total</strong></td>
              <td style="padding:6px;border:1px solid #ddd;"><strong>S/ {q.total:.2f}</strong></td></tr>
          <tr><td style="padding:6px;border:1px solid #ddd;"><strong>Adelanto (50%)</strong></td>
              <td style="padding:6px;border:1px solid #ddd;"><strong>S/ {q.adelanto:.2f}</strong></td></tr>
        </table>
        <p>Para continuar, por favor abone el adelanto de <strong>S/ {q.adelanto:.2f}</strong>.
        Una vez recibido, iniciaremos la producción.</p>
        <p>¡Gracias por confiar en nosotros!</p>
        """

    def _default_mock_response(self, prompt: str) -> str:
        # En mock devolvemos un HTML mínimo válido
        return "<h2>Constancia (mock)</h2><p>Pedido registrado.</p>"
