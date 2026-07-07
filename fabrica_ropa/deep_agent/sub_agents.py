"""
Sub-agentes especializados del Deep Agent — §3.6 de la plantilla.

Implementa los 3 sub-agentes usando cadenas LangChain LCEL:
  - Investigador: Recupera y sintetiza fuentes (RAG + búsqueda)
  - Redactor: Estructura la respuesta formal
  - Crítico: Evalúa contra checklist de calidad

Cada sub-agente tiene un propósito único y tools asignadas.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep_agent.state import EstadoDeepAgent
from config import EXECUTION_MODE, LLM_API_KEY, get_langchain_llm


def _call_llm(prompt: str, max_tokens: int = 1024) -> str:
    """Llama al LLM configurado vía cadena LangChain LCEL."""
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return _mock_response(prompt)
    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = get_langchain_llm(temperature=0.3, max_tokens=max_tokens)
        if llm is None:
            return _mock_response(prompt)

        chain = ChatPromptTemplate.from_messages([
            ("human", "{input}"),
        ]) | llm | StrOutputParser()

        return chain.invoke({"input": prompt})
    except Exception as e:
        print(f"[WARN] LLM error en sub-agente: {e}")
        return _mock_response(prompt)


def _mock_response(prompt: str) -> str:
    """Respuesta mock según el contexto del prompt."""
    p = prompt.lower()
    if "investig" in p or "recuper" in p:
        return json.dumps({
            "hallazgos": [
                "El catálogo incluye polos desde S/ 25, camisas desde S/ 45",
                "Descuentos por volumen: 10% (50+), 15% (100+), 20% (200+)",
                "Acabados: sin acabado, estampado (+S/8), bordado (+S/12)",
                "Entrega: 7-20 días hábiles según prenda y cantidad",
            ],
            "fuentes_consultadas": ["catalogo.txt"],
        }, ensure_ascii=False)
    if "redact" in p or "estructura" in p:
        return (
            "Basándome en la investigación realizada, le presento un resumen "
            "de nuestros productos y servicios textiles. Contamos con una amplia "
            "variedad de prendas con precios competitivos y descuentos por volumen."
        )
    if "evalú" in p or "critic" in p or "calidad" in p:
        return json.dumps({
            "aprobado": True,
            "puntuacion": 8.5,
            "observaciones": ["Buena cobertura de precios", "Falta mención de garantía"],
            "criterios": {"completitud": True, "exactitud": True, "claridad": True},
        }, ensure_ascii=False)
    return "Procesado correctamente (mock)."


# =============================================================================
# SUB-AGENTE: INVESTIGADOR
# =============================================================================

def agente_investigador(state: EstadoDeepAgent) -> dict:
    """
    Sub-agente Investigador — recupera y sintetiza información.

    Tools/recursos: RAG retriever, catálogo
    Propósito: Buscar información relevante para la tarea.

    Lee: tarea, plan, paso_actual
    Escribe: hallazgos
    """
    tarea = state["tarea"]
    plan = state.get("plan", [])
    paso = plan[state.get("paso_actual", 0)] if plan else tarea

    # Usar RAG para recuperar contexto
    contexto_rag = []
    try:
        from rag.retriever import retriever
        contexto_rag = retriever.query(tarea, k=4)
    except Exception as e:
        print(f"[WARN] RAG no disponible para Investigador: {e}")

    contexto_text = "\n".join(f"- {c[:200]}" for c in contexto_rag)

    prompt = f"""Eres un sub-agente INVESTIGADOR de una fábrica de ropa.
Tu tarea es recuperar y sintetizar información relevante.

TAREA PRINCIPAL: {tarea}
PASO ACTUAL: {paso}

INFORMACIÓN RECUPERADA DEL CATÁLOGO:
{contexto_text if contexto_text else "(sin información del catálogo)"}

Sintetiza los hallazgos relevantes en un JSON:
{{
  "hallazgos": ["hallazgo 1", "hallazgo 2", ...],
  "fuentes_consultadas": ["catalogo.txt"]
}}
"""
    raw = _call_llm(prompt)

    hallazgos = state.get("hallazgos", [])
    try:
        data = json.loads(raw)
        nuevos = data.get("hallazgos", [])
        hallazgos = hallazgos + nuevos
    except (json.JSONDecodeError, TypeError):
        hallazgos.append(raw.strip()[:500])

    return {
        "hallazgos": hallazgos,
        "artefactos": {
            **state.get("artefactos", {}),
            "ultima_investigacion": raw[:500],
        },
    }


# =============================================================================
# SUB-AGENTE: REDACTOR
# =============================================================================

def agente_redactor(state: EstadoDeepAgent) -> dict:
    """
    Sub-agente Redactor — estructura la respuesta formal.

    Tools/recursos: write_file (mock), plantillas
    Propósito: Crear un borrador de respuesta bien estructurado.

    Lee: tarea, hallazgos
    Escribe: borrador
    """
    tarea = state["tarea"]
    hallazgos = state.get("hallazgos", [])
    hallazgos_text = "\n".join(f"- {h}" for h in hallazgos)

    critica_previa = state.get("critica", {})
    feedback = ""
    if critica_previa and not critica_previa.get("aprobado", True):
        obs = critica_previa.get("observaciones", [])
        feedback = f"\n\nFEEDBACK DEL CRÍTICO (incorporar mejoras):\n" + "\n".join(f"- {o}" for o in obs)

    prompt = f"""Eres un sub-agente REDACTOR de una fábrica de ropa.
Tu tarea es estructurar una respuesta formal y completa.

TAREA: {tarea}

HALLAZGOS DEL INVESTIGADOR:
{hallazgos_text if hallazgos_text else "(sin hallazgos)"}
{feedback}

Genera una respuesta clara, profesional y completa en español.
Incluye todos los datos relevantes (precios, plazos, condiciones).
Organiza la información con viñetas o secciones cuando sea útil.
"""
    borrador = _call_llm(prompt)

    return {
        "borrador": borrador.strip(),
        "artefactos": {
            **state.get("artefactos", {}),
            "ultimo_borrador": borrador.strip()[:500],
        },
    }


# =============================================================================
# SUB-AGENTE: CRÍTICO
# =============================================================================

def agente_critico(state: EstadoDeepAgent) -> dict:
    """
    Sub-agente Crítico — evalúa el borrador contra checklist de calidad.

    Tools/recursos: checklist, rúbrica
    Propósito: Asegurar que la respuesta cumple criterios de calidad.

    Lee: tarea, borrador, hallazgos
    Escribe: critica, terminado
    """
    tarea = state["tarea"]
    borrador = state.get("borrador", "")
    hallazgos = state.get("hallazgos", [])
    iteracion = state.get("iteracion", 0)
    max_iter = state.get("max_iteraciones", 3)

    prompt = f"""Eres un sub-agente CRÍTICO de una fábrica de ropa.
Evalúa el siguiente borrador contra estos CRITERIOS DE CALIDAD:

1. COMPLETITUD: ¿Responde todos los aspectos de la tarea?
2. EXACTITUD: ¿Los datos (precios, plazos) coinciden con los hallazgos?
3. CLARIDAD: ¿Es fácil de entender para el cliente?
4. PROFESIONALISMO: ¿El tono es adecuado?

TAREA ORIGINAL: {tarea}

HALLAZGOS DISPONIBLES:
{chr(10).join(f'- {h}' for h in hallazgos)}

BORRADOR A EVALUAR:
{borrador}

Responde con JSON:
{{
  "aprobado": true/false,
  "puntuacion": 0.0 a 10.0,
  "observaciones": ["observación 1", ...],
  "criterios": {{"completitud": true/false, "exactitud": true/false, "claridad": true/false, "profesionalismo": true/false}}
}}
"""
    raw = _call_llm(prompt)

    critica = {"aprobado": True, "puntuacion": 7.0, "observaciones": [], "criterios": {}}
    try:
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw, re.DOTALL)
        if match:
            critica = json.loads(match.group())
    except (json.JSONDecodeError, TypeError):
        pass

    aprobado = critica.get("aprobado", True)
    terminado = aprobado or (iteracion + 1 >= max_iter)

    respuesta_final = ""
    if terminado:
        respuesta_final = borrador

    return {
        "critica": critica,
        "terminado": terminado,
        "iteracion": iteracion + 1,
        "respuesta_final": respuesta_final,
    }
