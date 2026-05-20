"""Tests del schema MCP y validación Pydantic."""
import pytest
from pydantic import ValidationError

from core.mcp_messages import (
    MCPMessage, AgentName, MessageType,
    OrderData, ValidationResult, QuoteResult,
)


def test_mcp_message_serializa_json():
    msg = MCPMessage(
        sender=AgentName.ORCHESTRATOR,
        receiver=AgentName.VALIDATOR,
        message_type=MessageType.REQUEST,
        payload={"x": 1},
    )
    j = msg.to_json()
    assert "ORCHESTRATOR".lower() in j.lower() or "Orchestrator" in j


def test_order_data_email_invalido_falla():
    """Schema valida formato de email."""
    with pytest.raises(ValidationError):
        OrderData(email="esto-no-es-email")


def test_order_data_cantidad_minima():
    """Cantidad debe ser >= 1."""
    with pytest.raises(ValidationError):
        OrderData(cantidad=0)


def test_order_data_acabado_enum():
    """Acabado solo acepta valores válidos."""
    with pytest.raises(ValidationError):
        OrderData(acabado="invalido")


def test_order_data_complete():
    order = OrderData(
        nombre="Juan", email="juan@x.com", tipo_prenda="polo",
        cantidad=10, talla="M", color="azul",
        acabado="bordado", fecha_entrega="2026-12-31",
    )
    assert order.is_complete() is True
    assert order.missing_fields() == []


def test_order_data_incomplete():
    order = OrderData(nombre="Juan")
    assert order.is_complete() is False
    assert "email" in order.missing_fields()


def test_validation_result_confidence_rango():
    """Confidence debe estar entre 0 y 1."""
    with pytest.raises(ValidationError):
        ValidationResult(is_textile=True, reason="x", confidence=2.0)
