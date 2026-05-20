"""
PricingAgent — Cálculo de cotización.

Combina lógica determinística (cálculo de precios, descuentos por volumen) con
una capa LLM que genera el resumen presentable al cliente. La parte numérica
NUNCA se delega al LLM (sería inexacto); el LLM solo formatea texto.
"""
from __future__ import annotations
import json
from pathlib import Path

from agents.base import BaseAgent
from core.mcp_messages import AgentName, OrderData, QuoteResult
from core.shared_state import SharedState
from config import PRICE_TABLE_PATH


SYSTEM_PROMPT = """Eres un agente de cotización para una fábrica de ropa. \
Recibes un JSON con los números YA CALCULADOS y debes generar un resumen \
amable y claro en texto plano (NO HTML) en español.

Reglas:
- Solo formateas el texto. Los números YA están calculados; NO los cambies.
- Incluye: producto, cantidad, precio unitario, subtotal, descuento aplicado, total y adelanto.
- Termina preguntando: "¿Confirmas para registrar el pedido y generar la constancia?"
- Devuelve SOLO el texto del resumen, sin JSON ni fences.
"""


class PricingAgent(BaseAgent):
    """Agente de cotización."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.PRICING,
            system_prompt=SYSTEM_PROMPT,
        )
        self._price_table = self._load_price_table()

    @staticmethod
    def _load_price_table() -> dict:
        with open(PRICE_TABLE_PATH, encoding="utf-8") as f:
            return json.load(f)

    def quote(self, order: OrderData, state: SharedState) -> QuoteResult:
        """Calcula la cotización y la almacena en el estado compartido."""
        # 1) Resolver precio unitario por tipo de prenda
        precio_unit = self._resolve_precio_unitario(order.tipo_prenda or "")
        # 2) Costo del acabado
        costo_acabado = self._price_table["acabados"].get(order.acabado or "ninguno", 0.0)
        # 3) Subtotal
        cantidad = order.cantidad or 0
        subtotal = (precio_unit + costo_acabado) * cantidad
        # 4) Descuento por volumen
        desc_porc, desc_label = self._resolve_descuento(cantidad)
        desc_monto = round(subtotal * desc_porc, 2)
        # 5) Total y adelanto
        total = round(subtotal - desc_monto, 2)
        adelanto_porc = self._price_table["porcentaje_adelanto"]
        adelanto = round(total * adelanto_porc, 2)

        # 6) Construir QuoteResult preliminar SIN resumen LLM
        quote_data = {
            "producto": f"{order.tipo_prenda} {order.color} - {order.acabado}",
            "cantidad": cantidad,
            "precio_unitario": precio_unit,
            "costo_acabado_unitario": costo_acabado,
            "subtotal": round(subtotal, 2),
            "descuento_porcentaje": desc_porc,
            "descuento_monto": desc_monto,
            "total": total,
            "adelanto": adelanto,
            "descuento_label": desc_label,
        }

        # 7) Pedir al LLM que genere el resumen amable
        resumen = self._format_with_llm(quote_data, state)

        result = QuoteResult(
            cantidad=cantidad,
            precio_unitario=precio_unit,
            costo_acabado_unitario=costo_acabado,
            subtotal=round(subtotal, 2),
            descuento_porcentaje=desc_porc,
            descuento_monto=desc_monto,
            total=total,
            adelanto=adelanto,
            descuento_label=desc_label,
            resumen_texto=resumen,
        )
        state.quote_result = result
        self.emit_event("quote_generated", total=total, adelanto=adelanto)
        return result

    def _resolve_precio_unitario(self, tipo_prenda: str) -> float:
        """Busca el precio en la tabla, considerando aliases."""
        t = tipo_prenda.lower().strip()
        prendas = self._price_table["prendas"]
        if t in prendas:
            return prendas[t]["precio_unitario"]
        for canonical, info in prendas.items():
            if t == canonical or t in info.get("alias", []):
                return info["precio_unitario"]
            # Buscar coincidencia parcial (ej. "polos deportivos" → polo)
            if canonical in t or any(a in t for a in info.get("alias", [])):
                return info["precio_unitario"]
        # Default si no se encuentra
        return 40.0

    def _resolve_descuento(self, cantidad: int) -> tuple[float, str]:
        """Devuelve (porcentaje, etiqueta) del descuento aplicable."""
        for tramo in self._price_table["descuentos_volumen"]:
            if cantidad >= tramo["minimo"]:
                return tramo["porcentaje"], tramo["label"]
        return 0.0, "Sin descuento"

    def _format_with_llm(self, quote_data: dict, state: SharedState) -> str:
        """Pide al LLM que genere el resumen presentable."""
        prompt = (
            "Genera el resumen amable de cotización con estos números:\n"
            f"{json.dumps(quote_data, ensure_ascii=False, indent=2)}\n"
            "Recuerda: solo formateas, no cambies los números."
        )
        raw = self.run(prompt, state)
        # Limpiar el ruido que Swarms agrega ([timestamp] System:, Human:, etc.)
        clean = self.extract_agent_text(raw).strip()
        if not clean or len(clean) < 20:
            # Fallback: formateamos nosotros si el LLM falla
            return self._format_fallback(quote_data)
        return clean

    @staticmethod
    def _format_fallback(q: dict) -> str:
        """Resumen textual sin LLM (determinístico)."""
        return (
            "🧾 Tu cotización:\n"
            f"• Producto: {q['producto']}\n"
            f"• Cantidad: {q['cantidad']} unidades\n"
            f"• Precio unitario: S/ {q['precio_unitario']:.2f}"
            f" (+ acabado S/ {q['costo_acabado_unitario']:.2f})\n"
            f"• Subtotal: S/ {q['subtotal']:.2f}\n"
            f"• Descuento: {q['descuento_label']} = -S/ {q['descuento_monto']:.2f}\n"
            f"• TOTAL: S/ {q['total']:.2f}\n"
            f"• Adelanto requerido (50%): S/ {q['adelanto']:.2f}\n\n"
            "¿Confirmas para registrar el pedido y generar la constancia?"
        )

    def _default_mock_response(self, prompt: str) -> str:
        """Mock: extraemos los datos del prompt y devolvemos formato fallback."""
        try:
            # Heurística: el prompt contiene un JSON con quote_data
            start = prompt.find("{")
            end = prompt.rfind("}") + 1
            q = json.loads(prompt[start:end])
            return self._format_fallback(q)
        except Exception:
            return "Cotización generada (mock)."
