"""Tests del SharedState — conflicto, transiciones y trazabilidad."""
from core.shared_state import SharedState, ConversationStage
from core.mcp_messages import MCPMessage, AgentName, MessageType


def test_transicion_de_estados():
    state = SharedState()
    assert state.stage == ConversationStage.INITIAL
    state.transition_to(ConversationStage.COLLECTING_DATA)
    assert state.stage == ConversationStage.COLLECTING_DATA


def test_actualizacion_sin_conflicto():
    state = SharedState()
    conflicts = state.update_order_data(nombre="Juan", cantidad=50)
    assert conflicts == []
    assert state.order_data.nombre == "Juan"
    assert state.order_data.cantidad == 50


def test_deteccion_de_conflicto():
    """Si actualizo un campo con un valor distinto, se reporta conflicto."""
    state = SharedState()
    state.update_order_data(cantidad=50)
    conflicts = state.update_order_data(cantidad=100)
    assert "cantidad" in conflicts
    # Estrategia: last-write-wins
    assert state.order_data.cantidad == 100


def test_historial_de_mensajes():
    state = SharedState()
    msg = MCPMessage(
        sender=AgentName.USER, receiver=AgentName.ORCHESTRATOR,
        message_type=MessageType.USER_INPUT, payload={"content": "hola"}
    )
    state.append_message(msg)
    assert len(state.message_history) == 1
    assert state.get_messages_by_agent(AgentName.USER) == [msg]


def test_conversacion_se_serializa():
    state = SharedState()
    state.append_user_message("hola")
    state.append_assistant_message("hola, ¿en qué te ayudo?")
    text = state.conversation_as_text()
    assert "Cliente: hola" in text
    assert "Sistema:" in text


def test_snapshot_serializable():
    state = SharedState()
    state.update_order_data(nombre="Juan")
    snap = state.snapshot()
    assert snap["order_data"]["nombre"] == "Juan"
    assert snap["stage"] == "initial"
