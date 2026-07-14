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

# LangSmith tracing (§5.3)
try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un agente experto en ventas y cotizaciones para una fábrica de ropa. \
Recibes un JSON con los números YA CALCULADOS y las estrategias de venta, debes generar un resumen \
amable, persuasivo y muy claro en formato Markdown (NO HTML).

Reglas:
- Los números YA están calculados; NO los cambies.
- Usa una **tabla Markdown** bien estructurada para mostrar el desglose de precios (Producto, Cantidad, P.Unitario, Subtotal, Descuento, Total).
- Añade las frases de 'upselling' (oferta por volumen) y 'cross_selling' (producto complementario) que vienen en el JSON para incentivar la compra. Hazlas sonar naturales y entusiastas.
- Termina preguntando: "¿Confirmas para registrar el pedido y generar la constancia?"
- Devuelve SOLO el texto del resumen, sin JSON ni fences adicionales.
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

    @traceable(name="PricingAgent.quote")
    def quote(self, order: OrderData, state: SharedState) -> QuoteResult:
        """Calcula la cotización y la almacena en el estado compartido."""
        precio_unit = self._resolve_precio_unitario(order.tipo_prenda or "")
        costo_acabado = self._price_table["acabados"].get(order.acabado or "ninguno", 0.0)
        cantidad = order.cantidad or 0
        subtotal = (precio_unit + costo_acabado) * cantidad
        desc_porc, desc_label, upselling_msg = self._resolve_descuento_and_upsell(cantidad)
        desc_monto = round(subtotal * desc_porc, 2)
        total = round(subtotal - desc_monto, 2)
        adelanto_porc = self._price_table["porcentaje_adelanto"]
        adelanto = round(total * adelanto_porc, 2)
        cross_selling_msg = self._get_cross_selling(order.tipo_prenda or "")

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
            "upselling": upselling_msg,
            "cross_selling": cross_selling_msg
        }

        resumen = self._format_with_llm(quote_data, state)

        pdf_path = None
        try:
            from tools.pdf_tool import PDFTool
            pdf_tool = PDFTool()
            pdf_path = pdf_tool.generate_quote_pdf(order, quote_data)
        except Exception as e:
            pass

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
            pdf_path=pdf_path,
        )
        state.quote_result = result
        self.emit_event("quote_generated", total=total, adelanto=adelanto)
        return result

    def _resolve_precio_unitario(self, tipo_prenda: str) -> float:
        t = tipo_prenda.lower().strip()
        prendas = self._price_table["prendas"]
        if t in prendas:
            return prendas[t]["precio_unitario"]
        for canonical, info in prendas.items():
            if t == canonical or t in info.get("alias", []):
                return info["precio_unitario"]
            if canonical in t or any(a in t for a in info.get("alias", [])):
                return info["precio_unitario"]
        return 40.0

    def _resolve_descuento_and_upsell(self, cantidad: int) -> tuple[float, str, str]:
        """Devuelve (porcentaje, etiqueta, mensaje_upselling)."""
        tramos = sorted(self._price_table["descuentos_volumen"], key=lambda x: x["minimo"], reverse=True)
        porc = 0.0
        label = "Sin descuento"
        
        # Encontrar el descuento actual
        for i, tramo in enumerate(tramos):
            if cantidad >= tramo["minimo"]:
                porc = tramo["porcentaje"]
                label = tramo["label"]
                # Upselling: buscar el siguiente tramo superior si existe
                if i > 0:
                    next_tramo = tramos[i-1]
                    faltan = next_tramo["minimo"] - cantidad
                    upselling = f"¡Estás a solo {faltan} unidades de obtener un {next_tramo['porcentaje']*100:.0f}% de descuento en todo el pedido!"
                    return porc, label, upselling
                return porc, label, "¡Has alcanzado nuestro descuento máximo por volumen! Gracias por tu gran pedido."
        
        # Si no llega a ningún descuento (i.e. cantidad 0 o menor al primer tramo)
        # Esto en realidad depende de cómo estén definidos los tramos (el mínimo es 0).
        # Pero si el mínimo para el primer descuento real es 50:
        for tramo in reversed(tramos):
            if tramo["porcentaje"] > 0:
                faltan = tramo["minimo"] - cantidad
                return porc, label, f"¡Atención! Si añades {faltan} unidades más, obtendrás un {tramo['porcentaje']*100:.0f}% de descuento."
        return porc, label, ""

    def _get_cross_selling(self, tipo_prenda: str) -> str:
        t = tipo_prenda.lower()
        if "polo" in t or "camiseta" in t:
            return "¿Te gustaría añadir unas gorras con el mismo diseño por S/ 15 adicionales c/u?"
        elif "short" in t or "pantalon" in t:
            return "¿Te interesan calcetines o medias deportivas a juego por S/ 10 el par?"
        elif "camisa" in t:
            return "¡Complementa tus camisas con corbatas personalizadas por solo S/ 20 adicionales!"
        return "¿Deseas agregar el logo de tu empresa bordado en gorras adicionales?"

    def _format_with_llm(self, quote_data: dict, state: SharedState) -> str:
        prompt = (
            "Genera el resumen de cotización estructurado y persuasivo con estos números:\n"
            f"{json.dumps(quote_data, ensure_ascii=False, indent=2)}\n"
            "Recuerda: usa una tabla Markdown para los precios y resalta las ofertas (upselling/cross-selling)."
        )
        raw = self.run(prompt, state)
        clean = self.extract_agent_text(raw).strip()
        if not clean or len(clean) < 20:
            return self._format_fallback(quote_data)
        return clean

    @staticmethod
    def _format_fallback(q: dict) -> str:
        return (
            "🧾 **Tu cotización oficial:**\n\n"
            "| Concepto | Detalle | Total |\n"
            "|---|---|---|\n"
            f"| **Producto** | {q['producto']} ({q['cantidad']} unid.) | |\n"
            f"| **P. Unitario base** | S/ {q['precio_unitario']:.2f} | |\n"
            f"| **Costo Acabado** | S/ {q['costo_acabado_unitario']:.2f} | |\n"
            f"| **Subtotal** | | **S/ {q['subtotal']:.2f}** |\n"
            f"| **Descuento** | {q['descuento_label']} | **-S/ {q['descuento_monto']:.2f}** |\n"
            f"| **TOTAL A PAGAR** | | **S/ {q['total']:.2f}** |\n\n"
            f"🔹 **Adelanto requerido (50%):** S/ {q['adelanto']:.2f}\n\n"
            f"💡 **Oferta Especial:** {q['upselling']}\n"
            f"🎁 **Sugerencia:** {q['cross_selling']}\n\n"
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
