"""
Estado del Deep Agent — §3.6 de la plantilla.

Define el TypedDict para el grafo del Deep Agent.
"""
from __future__ import annotations
from typing import TypedDict


class EstadoDeepAgent(TypedDict):
    """
    Estado compartido del Deep Agent.

    Campos:
        tarea: Tarea original del usuario.
        plan: Lista de pasos generados por el planificador.
        paso_actual: Índice del paso en ejecución.
        hallazgos: Información recopilada por el Investigador.
        borrador: Borrador de respuesta del Redactor.
        critica: Resultado de evaluación del Crítico.
        respuesta_final: Respuesta aprobada para el usuario.
        iteracion: Contador de iteraciones del ciclo plan-invest-redact-critic.
        max_iteraciones: Límite duro de iteraciones.
        terminado: Flag de terminación.
        artefactos: Artefactos persistidos entre pasos.
    """
    tarea: str
    plan: list[str]
    paso_actual: int
    hallazgos: list[str]
    borrador: str
    critica: dict
    respuesta_final: str
    iteracion: int
    max_iteraciones: int
    terminado: bool
    artefactos: dict
