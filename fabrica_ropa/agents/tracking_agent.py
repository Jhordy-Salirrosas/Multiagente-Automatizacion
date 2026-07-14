"""
TrackingAgent — Consulta el estado de un pedido en la base de datos.
"""
from __future__ import annotations
import sqlite3
import re

from agents.base import BaseAgent
from core.mcp_messages import AgentName
from core.shared_state import SharedState
from config import DB_PATH

SYSTEM_PROMPT = """Eres el agente de rastreo de pedidos.
Se te proporciona el ID de un pedido extraído del mensaje del usuario y tú consultas la base de datos.
Debes responder de manera muy servicial, indicando el estado del pedido y dando tranquilidad al cliente.
"""

class TrackingAgent(BaseAgent):
    """Agente para rastrear pedidos."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.VALIDATOR, # Bypass enum
            system_prompt=SYSTEM_PROMPT,
        )
        self.agent_name = "TrackingAgent"

    def track(self, user_message: str, state: SharedState) -> str:
        """Extrae el ID del pedido y consulta su estado en SQLite."""
        match = re.search(r"PED-\d{8}-\d{6}", user_message, re.IGNORECASE)
        if not match:
            return "No pude encontrar un número de pedido en tu mensaje. Asegúrate de incluir el código completo (ej. PED-2026...). ¿Te ayudo con algo más?"
        
        pedido_id = match.group(0).upper()
        
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM pedidos WHERE pedido_id = ?", (pedido_id,)).fetchone()
                
                if not row:
                    return f"Lo siento, he buscado en nuestro sistema y no encuentro ningún pedido con el código **{pedido_id}**. ¿Podrías verificar si está bien escrito?"
                
                estado = row["estado"]
                timestamp = row["timestamp_registro"]
                
                if estado == "Pendiente de pago":
                    msg = f"📦 Tu pedido **{pedido_id}** (registrado el {timestamp[:10]}) se encuentra **Pendiente de Pago**. \n\nRecuerda abonar el 50% de adelanto para iniciar la producción lo antes posible."
                elif estado == "Pagado":
                    msg = f"✅ ¡Buenas noticias! Tu pedido **{pedido_id}** ya está **Pagado** y se encuentra actualmente en la fila de producción. Nuestro equipo de abastecimiento está preparando todo."
                else:
                    msg = f"El estado de tu pedido **{pedido_id}** es: **{estado}**."
                
                return msg
                
        except Exception as e:
            return "Lo siento, en este momento tenemos problemas para conectar con la base de datos de rastreo. Intenta en unos minutos."
