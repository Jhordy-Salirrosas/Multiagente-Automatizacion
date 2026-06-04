"""
Estado compartido del grafo LangGraph — §3.5 de la plantilla.

Define el TypedDict que fluye entre nodos. Cada nodo recibe el estado
completo y devuelve un parche con los campos a actualizar.
"""
from __future__ import annotations
from typing import TypedDict, Annotated
from operator import add


class EstadoPedido(TypedDict):
    """
    Estado que fluye entre nodos del grafo LangGraph.

    Campos:
        pregunta: Consulta/mensaje actual del usuario.
        contexto: Fragmentos recuperados del vector store (RAG).
        plan: Pasos descompuestos de la tarea.
        respuesta: Respuesta generada para el usuario.
        iteraciones: Contador de ciclos de refinamiento.
        datos_pedido: Datos del pedido recolectados.
        etapa: Etapa actual del flujo.
        historial: Historial de mensajes previos.
        necesita_mas: Flag de la arista condicional validar.
    """
    pregunta: str
    contexto: list[str]
    plan: list[str]
    respuesta: str
    iteraciones: int
    datos_pedido: dict
    etapa: str
    historial: list[str]
    necesita_mas: bool
