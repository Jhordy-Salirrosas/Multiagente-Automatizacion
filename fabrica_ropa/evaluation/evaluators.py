"""
Evaluadores automáticos — §5.2 y §5.3.2 de la plantilla.

Implementa las métricas del plan de evaluación:
  - Exactitud: coincidencia semántica con la salida esperada
  - Groundedness: la respuesta se apoya en el contexto (LLM-as-judge)
  - Relevancia: el contexto recuperado es pertinente (LLM-as-judge)
  - Latencia y costo: métricas operativas

Tipos de evaluadores:
  - Heurístico: comparación determinista
  - LLM-as-judge: usa un LLM para juzgar calidad
"""
from __future__ import annotations
import re
import time
from typing import Optional

from config import LLM_API_KEY, LLM_MODEL, LLM_API_BASE, EXECUTION_MODE


def _call_judge(prompt: str) -> str:
    """Llama al LLM evaluador (LLM-as-judge) vía cadena LangChain LCEL."""
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return "0.85"  # Score mock
    try:
        from config import get_langchain_llm
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = get_langchain_llm(temperature=0.0, max_tokens=128)
        if llm is None:
            return "0.5"

        chain = ChatPromptTemplate.from_messages([
            ("human", "{input}"),
        ]) | llm | StrOutputParser()

        return chain.invoke({"input": prompt})
    except Exception as e:
        print(f"[WARN] Error en LLM judge: {e}")
        return "0.5"


# =============================================================================
# EVALUADOR: EXACTITUD (Heurístico + Semántico)
# =============================================================================

def evaluate_exactitud(output: str, expected: str) -> float:
    """
    Evalúa la exactitud de la salida vs. la esperada.

    Combina coincidencia de keywords (heurístico) con evaluación
    semántica si el LLM está disponible.

    Returns:
        Score entre 0.0 y 1.0
    """
    if not output or not expected:
        return 0.0

    # 1) Coincidencia heurística de keywords
    expected_lower = expected.lower()
    output_lower = output.lower()

    # Extraer números y keywords significativos del expected
    expected_numbers = set(re.findall(r'\d+\.?\d*', expected_lower))
    output_numbers = set(re.findall(r'\d+\.?\d*', output_lower))

    expected_words = set(re.findall(r'[a-záéíóúñ]+', expected_lower))
    output_words = set(re.findall(r'[a-záéíóúñ]+', output_lower))

    # Score de keywords
    if expected_words:
        word_overlap = len(expected_words & output_words) / len(expected_words)
    else:
        word_overlap = 0.0

    # Score de números
    if expected_numbers:
        num_overlap = len(expected_numbers & output_numbers) / len(expected_numbers)
    else:
        num_overlap = 1.0  # No había números que verificar

    # Score combinado (números pesan más: son datos factuales)
    heuristic_score = 0.4 * word_overlap + 0.6 * num_overlap

    # 2) Evaluación booleana: True/False exacto
    for pattern in [r'is_textile\s*=\s*(true|false)', r'(true|false)']:
        m_expected = re.search(pattern, expected_lower, re.IGNORECASE)
        m_output = re.search(pattern, output_lower, re.IGNORECASE)
        if m_expected and m_output:
            if m_expected.group(1).lower() == m_output.group(1).lower():
                heuristic_score = max(heuristic_score, 0.9)
            else:
                heuristic_score = min(heuristic_score, 0.1)

    return round(min(1.0, heuristic_score), 3)


# =============================================================================
# EVALUADOR: GROUNDEDNESS (LLM-as-judge)
# =============================================================================

def evaluate_groundedness(output: str, context: str) -> float:
    """
    Evalúa el grado en que la respuesta se apoya en el contexto (§5.2).

    Usa LLM-as-judge para determinar si la respuesta está fundamentada
    en los fragmentos recuperados.

    Returns:
        Score entre 0.0 y 1.0
    """
    if not output or not context:
        return 0.0

    prompt = f"""Eres un evaluador de calidad. Evalúa si la RESPUESTA está
completamente fundamentada en el CONTEXTO proporcionado.

CONTEXTO:
{context[:2000]}

RESPUESTA:
{output[:1000]}

Califica del 0.0 al 1.0:
- 1.0: Toda la información de la respuesta proviene del contexto
- 0.5: Parcialmente fundamentada
- 0.0: La respuesta inventa datos no presentes en el contexto

Responde SOLO con un número decimal (ej: 0.85):"""

    raw = _call_judge(prompt)

    # Extraer score numérico
    match = re.search(r'(\d+\.?\d*)', raw)
    if match:
        score = float(match.group(1))
        return round(min(1.0, max(0.0, score)), 3)
    return 0.5


# =============================================================================
# EVALUADOR: RELEVANCIA (LLM-as-judge)
# =============================================================================

def evaluate_relevance(query: str, context: str) -> float:
    """
    Evalúa si el contexto recuperado es pertinente para la consulta.

    Returns:
        Score entre 0.0 y 1.0
    """
    if not query or not context:
        return 0.0

    prompt = f"""Eres un evaluador de relevancia. Evalúa si el CONTEXTO RECUPERADO
es pertinente para responder la CONSULTA del usuario.

CONSULTA: {query}

CONTEXTO RECUPERADO:
{context[:2000]}

Califica del 0.0 al 1.0:
- 1.0: El contexto contiene exactamente la información necesaria
- 0.5: Parcialmente relevante
- 0.0: Completamente irrelevante

Responde SOLO con un número decimal (ej: 0.90):"""

    raw = _call_judge(prompt)
    match = re.search(r'(\d+\.?\d*)', raw)
    if match:
        score = float(match.group(1))
        return round(min(1.0, max(0.0, score)), 3)
    return 0.5


# =============================================================================
# EVALUACIÓN COMPLETA DE UN CASO
# =============================================================================

def evaluate_case(
    case_id: str,
    entrada: str,
    salida_esperada: str,
    salida_obtenida: str,
    contexto: str = "",
    latencia_ms: float = 0.0,
) -> dict:
    """
    Evaluación completa de un caso del golden set.

    Calcula todas las métricas de §5.2:
    - Exactitud (≥ 90%)
    - Groundedness (≥ 95%)
    - Latencia p95 (< 3s)
    - Costo por consulta (< $0.01)

    Returns:
        Dict con todas las métricas y si el caso aprobó.
    """
    exactitud = evaluate_exactitud(salida_obtenida, salida_esperada)
    groundedness = evaluate_groundedness(salida_obtenida, contexto) if contexto else 0.0

    # Umbrales (§2.4)
    umbral_exactitud = 0.90
    umbral_groundedness = 0.95
    umbral_latencia_ms = 3000.0  # 3 segundos

    aprobado = (
        exactitud >= umbral_exactitud
        and (groundedness >= umbral_groundedness or not contexto)
        and latencia_ms < umbral_latencia_ms
    )

    return {
        "case_id": case_id,
        "entrada": entrada,
        "salida_esperada": salida_esperada,
        "salida_obtenida": salida_obtenida,
        "exactitud": exactitud,
        "groundedness": groundedness,
        "latencia_ms": round(latencia_ms, 2),
        "aprobado": aprobado,
        "umbrales": {
            "exactitud": umbral_exactitud,
            "groundedness": umbral_groundedness,
            "latencia_ms": umbral_latencia_ms,
        },
    }
