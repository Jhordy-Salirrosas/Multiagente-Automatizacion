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

    Campos (Proceso 1 - RAG):
        pregunta: Consulta/mensaje actual del usuario.
        contexto: Fragmentos recuperados del vector store (RAG).
        plan: Pasos descompuestos de la tarea.
        respuesta: Respuesta generada para el usuario.
        iteraciones: Contador de ciclos de refinamiento.
        datos_pedido: Datos del pedido recolectados.
        etapa: Etapa actual del flujo.
        historial: Historial de mensajes previos.
        necesita_mas: Flag de la arista condicional validar.

    Campos (Proceso 2 - Compra de Materiales, §3.5 del documento):
        pedido_validado: Si el pedido fue validado.
        cotizacion: Datos de la cotización generada.
        pago_confirmado: Si el pago fue confirmado.
        lista_materiales: Materiales requeridos para producción.
        presupuesto: Presupuesto estimado.
        presupuesto_aprobado: Si el presupuesto fue aprobado (HITL).
        proveedor: Proveedor seleccionado.
        materiales_recibidos: Si los materiales fueron recibidos.
        notificaciones: Log de notificaciones enviadas.
        estado_proceso: Estado general del proceso.
    """
    # Proceso 1 — RAG
    pregunta: str
    contexto: list[str]
    plan: list[str]
    respuesta: str
    iteraciones: int
    datos_pedido: dict
    etapa: str
    historial: list[str]
    necesita_mas: bool
    # Proceso 2 — Compra de Materiales (§3.5)
    pedido_validado: bool
    cotizacion: dict
    pago_confirmado: bool
    lista_materiales: list
    presupuesto: float
    presupuesto_aprobado: bool
    proveedor: str
    materiales_recibidos: bool
    notificaciones: list
    estado_proceso: str
