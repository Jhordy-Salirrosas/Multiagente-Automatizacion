"""
Planificador del Deep Agent — §3.6 de la plantilla.

El planificador descompone la tarea en pasos y coordina los sub-agentes.
Incluye:
  - Límites operativos (máx iteraciones, presupuesto)
  - Mecanismo de fallback si no converge
  - Política de terminación
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep_agent.state import EstadoDeepAgent
from config import LLM_API_KEY, LLM_MODEL, LLM_API_BASE, EXECUTION_MODE


def _call_llm(prompt: str) -> str:
    """Llama al LLM configurado."""
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return _mock_plan(prompt)
    try:
        import litellm
        response = litellm.completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            max_tokens=512,
            temperature=0.2,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"⚠️  LLM error en planificador: {e}")
        return _mock_plan(prompt)


def _mock_plan(prompt: str) -> str:
    """Plan mock."""
    return json.dumps({
        "objetivo": "Responder la consulta del cliente sobre productos textiles",
        "pasos": [
            "Investigar información relevante del catálogo",
            "Redactar una respuesta completa y profesional",
            "Validar la calidad de la respuesta",
        ],
        "sub_agentes_requeridos": ["Investigador", "Redactor", "Crítico"],
        "complejidad_estimada": "media",
    }, ensure_ascii=False)


def nodo_planificar_deep(state: EstadoDeepAgent) -> dict:
    """
    Nodo del planificador: descompone la tarea en pasos y asigna sub-agentes.

    Lee: tarea
    Escribe: plan, paso_actual, max_iteraciones
    """
    tarea = state["tarea"]

    prompt = f"""Eres un agente planificador experto de una fábrica de ropa.
Tu rol es descomponer tareas complejas en pasos concretos y asignarlos
a sub-agentes especializados.

Sub-agentes disponibles:
- Investigador: busca y sintetiza información del catálogo
- Redactor: estructura respuestas formales y documentos
- Crítico: evalúa calidad contra criterios de completitud y exactitud

Responde con JSON:
{{
  "objetivo": "descripción breve",
  "pasos": ["paso 1", "paso 2", ...],
  "sub_agentes_requeridos": ["Investigador", "Redactor", ...],
  "complejidad_estimada": "baja|media|alta"
}}

TAREA: {tarea}
"""
    raw = _call_llm(prompt)

    plan = ["Investigar", "Redactar", "Validar"]
    try:
        import re
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            plan = data.get("pasos", plan)
    except (json.JSONDecodeError, TypeError):
        pass

    return {
        "plan": plan,
        "paso_actual": 0,
        "max_iteraciones": min(5, len(plan) + 2),
        "artefactos": {"plan_original": plan},
    }
