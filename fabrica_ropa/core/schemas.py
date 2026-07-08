"""
Esquemas de salida estructurada — §3.7 de la plantilla.

Define modelos Pydantic con Field() que el LLM está obligado a respetar.
Estos son los contratos de datos entre el LLM y el resto del sistema.
"""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


class ResumenPedido(BaseModel):
    """Resumen estructurado de un pedido textil."""
    titulo: str = Field(
        description="Tema del pedido en <= 8 palabras",
        max_length=60,
    )
    puntos: list[str] = Field(
        description="Puntos clave del pedido (3-5 items)",
        min_length=3,
        max_length=5,
    )
    nivel: str = Field(
        description="Complejidad del pedido",
        pattern=r"^(basico|intermedio|avanzado)$",
    )


class RespuestaAgente(BaseModel):
    """Respuesta estructurada de un agente al usuario."""
    respuesta: str = Field(
        description="Respuesta en lenguaje natural al usuario",
    )
    confianza: float = Field(
        ge=0.0,
        le=1.0,
        description="Nivel de confianza en la respuesta (0.0 a 1.0)",
    )
    fuentes: list[str] = Field(
        default_factory=list,
        description="Fragmentos del catálogo usados como contexto (RAG)",
    )
    requiere_human_review: bool = Field(
        default=False,
        description="True si la respuesta necesita revisión humana antes de enviar",
    )


class PlanDeepAgent(BaseModel):
    """Plan de ejecución generado por el Deep Agent planificador."""
    objetivo: str = Field(
        description="Descripción breve del objetivo a resolver",
    )
    pasos: list[str] = Field(
        description="Lista ordenada de pasos a ejecutar",
        min_length=1,
        max_length=10,
    )
    sub_agentes_requeridos: list[str] = Field(
        description="Sub-agentes que se necesitan invocar",
    )
    complejidad_estimada: str = Field(
        description="Nivel de complejidad estimado",
        pattern=r"^(baja|media|alta)$",
    )


class CriticaResult(BaseModel):
    """Resultado de la evaluación del Agente Crítico."""
    aprobado: bool = Field(
        description="True si el borrador pasa el checklist de calidad",
    )
    puntuacion: float = Field(
        ge=0.0,
        le=10.0,
        description="Puntuación de calidad (0 a 10)",
    )
    observaciones: list[str] = Field(
        default_factory=list,
        description="Observaciones y sugerencias de mejora",
    )
    criterios_evaluados: dict[str, bool] = Field(
        default_factory=dict,
        description="Criterios y si se cumplieron (ej. {'completitud': true})",
    )


class ResultadoRAG(BaseModel):
    """Resultado de una consulta al subsistema RAG."""
    consulta: str = Field(description="Pregunta original del usuario")
    fragmentos: list[str] = Field(
        description="Fragmentos recuperados del catálogo",
    )
    scores: list[float] = Field(
        description="Scores de relevancia de cada fragmento",
    )
    respuesta_generada: Optional[str] = Field(
        default=None,
        description="Respuesta generada con los fragmentos como contexto",
    )


class MetricaEvaluacion(BaseModel):
    """Resultado de evaluación de un caso del golden set."""
    caso_id: str = Field(description="Identificador del caso (C-01, C-02, ...)")
    entrada: str = Field(description="Input del caso de prueba")
    salida_esperada: str = Field(description="Output esperado")
    salida_obtenida: str = Field(description="Output real del sistema")
    exactitud: float = Field(
        ge=0.0, le=1.0,
        description="Score de exactitud (0.0 a 1.0)",
    )
    groundedness: float = Field(
        ge=0.0, le=1.0,
        description="Score de fidelidad al contexto (0.0 a 1.0)",
    )
    latencia_ms: float = Field(
        ge=0.0,
        description="Tiempo de respuesta en milisegundos",
    )
    aprobado: bool = Field(
        description="True si supera todos los umbrales",
    )
