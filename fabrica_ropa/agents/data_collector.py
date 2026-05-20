"""
DataCollectorAgent — Recolección conversacional de datos.

Recolecta los 8 datos esenciales del cliente de forma natural y los emite
como JSON estructurado validado por Pydantic (OrderData).
"""
from __future__ import annotations
import json
import re
from datetime import datetime

from agents.base import BaseAgent
from core.mcp_messages import AgentName, OrderData
from core.shared_state import SharedState


SYSTEM_PROMPT = """Eres un agente conversacional especializado en recolectar \
datos para un pedido de confección textil. Debes recoger 8 datos:

1. nombre           (texto)
2. email            (texto con @)
3. tipo_prenda      (polo, camisa, pantalón, casaca, vestido, uniforme, falda, short)
4. cantidad         (entero ≥ 1)
5. talla            (XS/S/M/L/XL/XXL o múltiples ej. "25 S y 25 M")
6. color            (texto)
7. acabado          ("ninguno" | "estampado" | "bordado")
8. fecha_entrega    (formato ISO YYYY-MM-DD)

REGLAS ESTRICTAS:
- Responde SIEMPRE con un JSON estricto con dos claves: "extracted_data" y "reply".
- "extracted_data" contiene los campos que pudiste extraer del mensaje actual (solo esos, los demás omítelos).
- "reply" es tu próxima pregunta al cliente en español, amable y concreta (1-3 líneas máx).
- Si ya tienes todos los datos, "reply" debe ser un resumen amable + "¿Confirmas estos datos para cotizar?".
- NUNCA inventes datos. Si el cliente no provee un dato, no lo incluyas en extracted_data.
- NUNCA uses ```json fences. Solo el JSON puro.

Formato exacto de respuesta:
{
  "extracted_data": { "nombre": "Juan Pérez", "cantidad": 50 },
  "reply": "Gracias Juan. ¿Cuál es tu correo electrónico?"
}
"""


class DataCollectorAgent(BaseAgent):
    """Agente de recolección de datos."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.DATA_COLLECTOR,
            system_prompt=SYSTEM_PROMPT,
        )

    def collect(self, user_message: str, state: SharedState) -> tuple[OrderData, str, bool]:
        """
        Procesa un mensaje del cliente, extrae datos, actualiza el estado y
        devuelve (order_data, reply_para_el_cliente, datos_completos).
        """
        # Construir el prompt con historial e info actual
        current_data = state.order_data.model_dump(exclude_none=True)
        missing = state.order_data.missing_fields()

        prompt = f"""Datos ya recolectados hasta ahora:
{json.dumps(current_data, ensure_ascii=False, indent=2)}

Datos pendientes: {missing if missing else 'NINGUNO (todos los datos completos)'}

Historial de la conversación:
{state.conversation_as_text()}

Último mensaje del cliente: "{user_message}"

Responde el JSON con extracted_data y reply."""

        raw = self.run(prompt, state)
        data = self.extract_json(raw)

        extracted: dict = {}
        reply = ""
        if data:
            extracted = data.get("extracted_data", {}) or {}
            reply = data.get("reply", "") or ""
        else:
            # El LLM no devolvió JSON parseable (puede pasar en rate limit,
            # errores transitorios, o respuestas malformadas). Aplicamos
            # extracción heurística con regex sobre el último mensaje para
            # no perder datos del usuario.
            heuristic_raw = self._default_mock_response(prompt)
            heuristic = self.extract_json(heuristic_raw) or {}
            extracted = heuristic.get("extracted_data", {}) or {}
            # No usamos el reply heurístico aquí; preferimos pedir el
            # siguiente campo faltante con un mensaje natural
            self.emit_event("llm_response_unparseable", fallback="heuristic")

        # Limpiar y validar campos extraídos antes de pasarlos al estado
        clean_extracted = self._sanitize(extracted)
        conflicts = state.update_order_data(**clean_extracted)
        if conflicts:
            self.emit_event(
                "data_conflict_detected",
                fields=conflicts,
                resolution="last_write_wins",
            )

        if not reply:
            reply = self._fallback_reply(state.order_data)

        is_complete = state.order_data.is_complete()
        if is_complete:
            self.emit_event("data_collection_completed", data=state.order_data.model_dump())
        return state.order_data, reply, is_complete

    @staticmethod
    def _sanitize(extracted: dict) -> dict:
        """Limpia y normaliza los campos antes de pasarlos al modelo."""
        clean = {}
        for key, value in extracted.items():
            if value is None or value == "":
                continue
            if key == "cantidad":
                # Aceptar string o int
                try:
                    clean[key] = int(re.sub(r"[^\d]", "", str(value)))
                except (ValueError, TypeError):
                    continue
            elif key == "acabado":
                v = str(value).lower().strip()
                if v in ("ninguno", "estampado", "bordado", "ninguna", "sin"):
                    clean[key] = "ninguno" if v in ("ninguna", "sin") else v
            elif key == "email":
                v = str(value).strip().lower()
                if "@" in v and "." in v.split("@")[-1]:
                    clean[key] = v
            elif key == "fecha_entrega":
                clean[key] = DataCollectorAgent._normalize_date(str(value))
            elif key in {"nombre", "tipo_prenda", "talla", "color"}:
                clean[key] = str(value).strip()
        return clean

    @staticmethod
    def _normalize_date(text: str) -> str:
        """Intenta normalizar varios formatos de fecha a ISO YYYY-MM-DD."""
        text = text.strip()
        # Si ya es ISO, devolverlo
        if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
            return text
        # Intentar dd/mm/yyyy o dd-mm-yyyy
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", text)
        if m:
            d, mo, y = m.groups()
            try:
                return datetime(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
            except ValueError:
                pass
        # Texto como "27 de junio del 2026"
        meses = {
            "enero":1,"febrero":2,"marzo":3,"abril":4,"mayo":5,"junio":6,
            "julio":7,"agosto":8,"septiembre":9,"setiembre":9,"octubre":10,
            "noviembre":11,"diciembre":12
        }
        m = re.match(r"(\d{1,2})\s*(?:de)?\s*([a-záéíóúñ]+)\s*(?:del?)?\s*(\d{4})", text.lower())
        if m:
            d, mes, y = m.groups()
            mo = meses.get(mes)
            if mo:
                try:
                    return datetime(int(y), mo, int(d)).strftime("%Y-%m-%d")
                except ValueError:
                    pass
        return text  # Devolver tal cual; el validador downstream lo rechazará si es inválido

    @staticmethod
    def _fallback_reply(order: OrderData) -> str:
        """Reply manual si el LLM no respondió correctamente."""
        missing = order.missing_fields()
        if not missing:
            return ("Tengo todos los datos. ¿Confirmas para generar la cotización?")
        prompts_por_campo = {
            "nombre": "¿Cuál es tu nombre completo?",
            "email": "¿Cuál es tu correo electrónico?",
            "tipo_prenda": "¿Qué tipo de prenda necesitas? (polo, camisa, pantalón, etc.)",
            "cantidad": "¿Cuántas unidades necesitas?",
            "talla": "¿Qué tallas necesitas? (ej. 25 S y 25 M)",
            "color": "¿Qué color deseas?",
            "acabado": "¿Qué acabado prefieres? (ninguno, estampado o bordado)",
            "fecha_entrega": "¿Para qué fecha necesitas el pedido? (formato YYYY-MM-DD)",
        }
        return prompts_por_campo[missing[0]]

    def _default_mock_response(self, prompt: str) -> str:
        """
        Mock con extracción heurística (regex) — permite que la demo
        funcione sin API key, aunque con menos calidad que el LLM real.
        """
        # El prompt termina con: Último mensaje del cliente: "..."
        m = re.search(r'Último mensaje del cliente:\s*"([^"]*)"', prompt)
        user_msg = m.group(1) if m else ""

        # Detectar qué falta para decidir qué extraer
        missing_match = re.search(r"Datos pendientes:\s*(\[.*?\])", prompt, re.DOTALL)
        missing_str = missing_match.group(1) if missing_match else ""

        extracted = {}
        # Email (siempre intentar)
        em = re.search(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", user_msg, re.IGNORECASE)
        if em and "email" in missing_str:
            extracted["email"] = em.group(0).lower()
        # Cantidad
        cm = re.search(r"\b(\d{1,4})\s*(?:polos?|camisas?|pantalon|uniform|prend|unid)", user_msg.lower())
        if cm and "cantidad" in missing_str:
            extracted["cantidad"] = int(cm.group(1))
        # Tipo de prenda
        for prenda in ["polo", "camisa", "pantalon", "casaca", "vestido", "uniforme", "falda", "short"]:
            if prenda in user_msg.lower() and "tipo_prenda" in missing_str:
                extracted["tipo_prenda"] = prenda
                break
        # Acabado
        for ac in ["bordado", "estampado", "ninguno"]:
            if ac in user_msg.lower() and "acabado" in missing_str:
                extracted["acabado"] = ac
                break
        # Nombre ("mi nombre es X" / "soy X")
        nm = re.search(r"(?:mi nombre es|soy|me llamo)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)", user_msg, re.IGNORECASE)
        if nm and "nombre" in missing_str:
            extracted["nombre"] = nm.group(1).strip()
        # Fecha YYYY-MM-DD
        fm = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", user_msg)
        if fm and "fecha_entrega" in missing_str:
            extracted["fecha_entrega"] = fm.group(1)
        # Color (palabras simples)
        if "color" in missing_str:
            colores = ["rojo", "azul", "verde", "negro", "blanco", "amarillo", "gris", "rosa", "naranja", "morado", "celeste"]
            for c in colores:
                if c in user_msg.lower():
                    extracted["color"] = c
                    break
        # Talla
        if "talla" in missing_str:
            tm = re.search(r"talla[s]?\s+([\w\s,yY]+?)(?:[.,]|$)", user_msg, re.IGNORECASE)
            if tm:
                extracted["talla"] = tm.group(1).strip()
            elif re.search(r"\b[smlx]+\b", user_msg.lower()):
                # Detección simple de S, M, L, XL
                extracted["talla"] = user_msg.strip()

        # Reply genérico
        reply = "Datos registrados. ¿Algún otro detalle?"
        return json.dumps({"extracted_data": extracted, "reply": reply}, ensure_ascii=False)
