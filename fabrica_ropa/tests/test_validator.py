"""Tests del ValidatorAgent — incluye casos adversariales."""
from agents.validator import ValidatorAgent
from core.shared_state import SharedState


def test_validador_acepta_polos():
    v = ValidatorAgent()
    state = SharedState()
    result = v.validate("Necesito 50 polos con bordado", state)
    assert result.is_textile is True


def test_validador_acepta_uniformes():
    v = ValidatorAgent()
    state = SharedState()
    result = v.validate("Cotizar uniformes escolares", state)
    assert result.is_textile is True


def test_validador_rechaza_comida():
    """Caso adversarial: pedido de comida debe ser rechazado."""
    v = ValidatorAgent()
    state = SharedState()
    result = v.validate("Quisiera 10 pizzas para una fiesta", state)
    assert result.is_textile is False


def test_validador_rechaza_electronica():
    """Caso adversarial: electrónica."""
    v = ValidatorAgent()
    state = SharedState()
    result = v.validate("Necesito una laptop y un celular", state)
    assert result.is_textile is False


def test_validador_acepta_saludo_ambiguo():
    """Saludos ambiguos se asumen como intención textil (confidence baja)."""
    v = ValidatorAgent()
    state = SharedState()
    result = v.validate("hola", state)
    assert result.is_textile is True
    assert result.confidence <= 0.6


def test_validador_actualiza_estado():
    """El resultado debe quedar persistido en el SharedState."""
    v = ValidatorAgent()
    state = SharedState()
    v.validate("camisas blancas", state)
    assert state.validation_result is not None
    assert state.validation_result.is_textile is True
