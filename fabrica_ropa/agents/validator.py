"""
ValidatorAgent — Filtro de seguridad.

Determina si el mensaje del cliente corresponde al rubro textil. Si no
(p.ej. pide comida, electrónica, etc.), el flujo se rechaza amablemente.
"""
from __future__ import annotations
import json
import re

from agents.base import BaseAgent
from core.mcp_messages import AgentName, ValidationResult
from core.shared_state import SharedState
from config import VALID_GARMENTS_PATH

# LangSmith tracing (§5.3)
try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un agente especializado EXCLUSIVAMENTE en validar si un \
mensaje de un cliente corresponde al rubro TEXTIL (confección de ropa: polos, \
camisas, pantalones, casacas, vestidos, uniformes, faldas, shorts, etc.).

Tu ÚNICA función es responder con un JSON estricto, sin texto adicional:

{
  "is_textile": true | false,
  "reason": "explicación breve en español (máx 1 línea)",
  "confidence": 0.0 a 1.0
}

Reglas:
- Si el cliente pide prendas de vestir, accesorios textiles, uniformes, etc. → is_textile=true
- Si pide comida, electrónica, vehículos, muebles, servicios no textiles → is_textile=false
- Si el mensaje es ambiguo (saludo "hola") → is_textile=true con confidence=0.5 (asumimos intención)
- NUNCA respondas con texto fuera del JSON. NUNCA uses ```json fences.
"""


class ValidatorAgent(BaseAgent):
    """Agente de validación del rubro."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.VALIDATOR,
            system_prompt=SYSTEM_PROMPT,
            mock_response=None,
        )
        # Cargar lista de palabras clave para validación fallback
        with open(VALID_GARMENTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        self._textile_keywords = set(k.lower() for k in data["palabras_clave_textil"])
        self._non_textile_examples = set(k.lower() for k in data["rubros_no_textil_ejemplos"])

    @traceable(name="ValidatorAgent.validate")
    def validate(self, user_message: str, state: SharedState) -> ValidationResult:
        """Valida el mensaje y devuelve un ValidationResult tipado."""
        prompt = f"Mensaje del cliente: \"{user_message}\"\n\nResponde el JSON de validación."
        raw = self.run(prompt, state)
        data = self.extract_json(raw)

        if data and "is_textile" in data:
            try:
                result = ValidationResult(
                    is_textile=bool(data["is_textile"]),
                    reason=str(data.get("reason", "")),
                    confidence=float(data.get("confidence", 1.0)),
                )
            except Exception:
                result = self._fallback_validation(user_message)
        else:
            # Si el LLM falló al devolver JSON, hacemos validación por palabras clave
            result = self._fallback_validation(user_message)

        state.validation_result = result
        self.emit_event(
            "validation_completed",
            is_textile=result.is_textile,
            reason=result.reason,
        )
        return result

    def _fallback_validation(self, message: str) -> ValidationResult:
        """Validación por palabras clave si el LLM no responde JSON válido."""
        msg = message.lower()
        # Substring matching (más robusto que token-exact: detecta plurales,
        # derivados, "pizzas", "celulares", etc.)
        textile_hits = {k for k in self._textile_keywords if k in msg}
        non_textile_hits = {k for k in self._non_textile_examples if k in msg}

        if non_textile_hits and not textile_hits:
            return ValidationResult(
                is_textile=False,
                reason=f"El pedido parece ser de otro rubro: {', '.join(non_textile_hits)}",
                confidence=0.85,
            )
        if textile_hits:
            return ValidationResult(
                is_textile=True,
                reason=f"Detectadas palabras del rubro textil: {', '.join(textile_hits)}",
                confidence=0.9,
            )
        # Mensaje ambiguo (saludo, etc.) → asumimos intención textil
        return ValidationResult(
            is_textile=True,
            reason="Mensaje ambiguo, se asume intención textil (saludo o consulta inicial)",
            confidence=0.5,
        )

    def _default_mock_response(self, prompt: str) -> str:
        """Mock determinístico basado en palabras clave."""
        result = self._fallback_validation(prompt)
        return json.dumps(result.model_dump(), ensure_ascii=False)
