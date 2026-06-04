"""
Nodos del grafo LangGraph — §3.5 de la plantilla.

Cada nodo es una función pura: recibe el estado y devuelve un parche
con los campos a actualizar.

Nodos:
  - planificar: Descompone la pregunta en pasos
  - recuperar: Trae contexto del vector store (RAG)
  - responder: Genera respuesta final con contexto
  - validar: Decide si la respuesta basta o reitera
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

# Asegurar imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph_flow.state import EstadoPedido
from config import LLM_API_KEY, LLM_MODEL, LLM_API_BASE, EXECUTION_MODE


def _call_llm(prompt: str) -> str:
    """
    Llama al LLM configurado vía litellm.
    Reutiliza la misma config del proyecto (config.py).
    """
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return _mock_llm(prompt)

    try:
        import litellm
        response = litellm.completion(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            api_key=LLM_API_KEY,
            api_base=LLM_API_BASE,
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"⚠️  LLM error en nodo LangGraph: {e}")
        return _mock_llm(prompt)


def _mock_llm(prompt: str) -> str:
    """Respuesta mock para desarrollo sin API key."""
    if "planifica" in prompt.lower() or "descompone" in prompt.lower():
        return json.dumps({
            "pasos": [
                "Recuperar información del catálogo",
                "Analizar la consulta del usuario",
                "Generar respuesta con datos del catálogo"
            ]
        })
    if "responde" in prompt.lower() or "genera" in prompt.lower():
        return "Basándome en nuestro catálogo, puedo ayudarte con tu consulta sobre nuestros productos textiles."
    if "valida" in prompt.lower() or "evalúa" in prompt.lower():
        return json.dumps({"suficiente": True, "razon": "Respuesta completa"})
    return "Procesado correctamente (mock)."


# =============================================================================
# NODOS DEL GRAFO
# =============================================================================

def nodo_planificar(state: EstadoPedido) -> dict:
    """
    Nodo PLANIFICAR: descompone la pregunta del usuario en pasos.

    Lee: pregunta
    Escribe: plan
    """
    pregunta = state["pregunta"]

    prompt = f"""Descompone la siguiente consulta de un cliente de una fábrica de ropa
en pasos concretos para resolverla. Responde con JSON:
{{"pasos": ["paso 1", "paso 2", ...]}}

Consulta del cliente: "{pregunta}"
"""
    raw = _call_llm(prompt)

    # Extraer pasos del JSON
    pasos = ["Recuperar información", "Generar respuesta"]
    try:
        data = json.loads(raw)
        if "pasos" in data:
            pasos = data["pasos"]
    except (json.JSONDecodeError, TypeError):
        # Intentar extraer JSON embebido
        import re
        match = re.search(r'\{[^}]+\}', raw)
        if match:
            try:
                data = json.loads(match.group())
                pasos = data.get("pasos", pasos)
            except json.JSONDecodeError:
                pass

    return {
        "plan": pasos,
        "etapa": "planificado",
    }


def nodo_recuperar(state: EstadoPedido) -> dict:
    """
    Nodo RECUPERAR: trae contexto del vector store (RAG).

    Lee: pregunta
    Escribe: contexto
    """
    pregunta = state["pregunta"]

    try:
        from rag.retriever import retriever
        fragmentos = retriever.query(pregunta, k=4)
    except Exception as e:
        print(f"⚠️  Error en RAG retriever: {e}")
        fragmentos = ["No se pudo recuperar información del catálogo."]

    return {
        "contexto": fragmentos,
        "etapa": "contexto_recuperado",
    }


def nodo_responder(state: EstadoPedido) -> dict:
    """
    Nodo RESPONDER: genera respuesta final usando el contexto recuperado.

    Lee: pregunta, contexto
    Escribe: respuesta
    """
    pregunta = state["pregunta"]
    contexto = state.get("contexto", [])
    contexto_text = "\n\n---\n\n".join(contexto) if contexto else "Sin contexto disponible."

    prompt = f"""Eres un asistente de ventas de una fábrica de ropa.
Responde la pregunta del cliente usando EXCLUSIVAMENTE la información del contexto.

REGLAS:
- Responde en español, de forma amable y concisa.
- Si el contexto no contiene la respuesta, di "No tengo esa información en nuestro catálogo".
- NUNCA inventes datos que no estén en el contexto.
- Cita datos relevantes del catálogo (precios, plazos, etc.).

CONTEXTO:
{contexto_text}

PREGUNTA: {pregunta}

RESPUESTA:"""

    respuesta = _call_llm(prompt)

    return {
        "respuesta": respuesta.strip(),
        "etapa": "respuesta_generada",
    }


def nodo_validar(state: EstadoPedido) -> dict:
    """
    Nodo VALIDAR: decide si la respuesta es suficiente o necesita más iteraciones.

    Lee: respuesta, iteraciones
    Escribe: necesita_mas, iteraciones

    Arista condicional:
      - Si necesita_mas == True → vuelve a nodo_recuperar
      - Si necesita_mas == False → END
    """
    respuesta = state.get("respuesta", "")
    iteraciones = state.get("iteraciones", 0)

    # Límite duro de iteraciones para evitar loops infinitos
    MAX_ITERACIONES = 3
    if iteraciones >= MAX_ITERACIONES:
        return {
            "necesita_mas": False,
            "iteraciones": iteraciones,
            "etapa": "validado_limite",
        }

    # Criterios de suficiencia:
    # 1) La respuesta tiene contenido sustancial (> 50 chars)
    # 2) No contiene "no tengo" o "no encontré" (señal de contexto insuficiente)
    es_vacia = len(respuesta.strip()) < 50
    sin_info = any(frase in respuesta.lower() for frase in [
        "no tengo esa información",
        "no encontré",
        "no dispongo",
        "sin contexto",
    ])

    necesita_mas = es_vacia or (sin_info and iteraciones < MAX_ITERACIONES)

    return {
        "necesita_mas": necesita_mas,
        "iteraciones": iteraciones + 1,
        "etapa": "validado",
    }
