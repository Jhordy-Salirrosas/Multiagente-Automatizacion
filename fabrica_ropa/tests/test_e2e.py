"""
Test end-to-end (E2E) — Recorre el flujo completo de venta con el orquestador.
Como estamos en modo mock, validamos transiciones de estado y persistencia.
"""
import os
from pathlib import Path

from agents.orchestrator import Orchestrator
from core.shared_state import SharedState, ConversationStage


def test_flujo_rechazo_por_rubro_no_textil(tmp_path, monkeypatch):
    """Caso adversarial: pedido de comida es rechazado inmediatamente."""
    orchestrator = Orchestrator()
    state = SharedState()
    reply = orchestrator.handle_user_message("Necesito 10 pizzas margarita", state)
    assert state.stage == ConversationStage.REJECTED
    assert "textil" in reply.lower() or "ropa" in reply.lower()


def test_flujo_acepta_textil_y_pasa_a_recoleccion():
    orchestrator = Orchestrator()
    state = SharedState()
    orchestrator.handle_user_message("Necesito 50 polos bordados", state)
    # Después del primer mensaje debe estar recolectando datos
    assert state.stage == ConversationStage.COLLECTING_DATA
    assert state.validation_result is not None
    assert state.validation_result.is_textile is True


def test_historial_mcp_acumula():
    """Cada turno debe generar mensajes MCP en el estado compartido."""
    orchestrator = Orchestrator()
    state = SharedState()
    orchestrator.handle_user_message("Necesito polos", state)
    # Al menos: user_input, request validador, response validador,
    # request data_collector, response data_collector, user_output
    assert len(state.message_history) >= 4


def test_metricas_se_registran():
    """Las invocaciones a agentes deben quedar en métricas."""
    from core.metrics import metrics
    invocaciones_antes = len(metrics._invocations)
    orchestrator = Orchestrator()
    state = SharedState()
    orchestrator.handle_user_message("Necesito 30 camisas", state)
    invocaciones_despues = len(metrics._invocations)
    assert invocaciones_despues > invocaciones_antes


def test_confirmacion_sin_datos_no_avanza():
    """Caso adversarial: usuario dice 'sí' sin haber dado datos."""
    orchestrator = Orchestrator()
    state = SharedState()
    orchestrator.handle_user_message("Quiero polos", state)
    # En etapa COLLECTING_DATA, un 'sí' va al DataCollector, no a confirmación
    orchestrator.handle_user_message("sí", state)
    # Verificamos que NO se haya registrado el pedido (RegistryResult sigue None)
    assert state.stage == ConversationStage.COLLECTING_DATA
    assert state.registry_result is None
    assert state.notification_result is None


def test_cancelacion_explicita_en_confirmacion():
    """Si el usuario cancela en la etapa de confirmación, se rechaza."""
    orchestrator = Orchestrator()
    state = SharedState()
    # Saltamos directo a WAITING_CONFIRMATION simulando el estado
    state.stage = ConversationStage.WAITING_CONFIRMATION
    reply = orchestrator.handle_user_message("no, cancelar", state)
    assert state.stage == ConversationStage.REJECTED
    assert "cancel" in reply.lower()
