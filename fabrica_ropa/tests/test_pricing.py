"""Tests del PricingAgent — verifica cálculos determinísticos."""
import pytest
from agents.pricing import PricingAgent
from core.mcp_messages import OrderData
from core.shared_state import SharedState


def _build_order(**kwargs) -> OrderData:
    defaults = dict(
        nombre="Test", email="test@example.com", tipo_prenda="polo",
        cantidad=10, talla="M", color="azul",
        acabado="ninguno", fecha_entrega="2026-12-31",
    )
    defaults.update(kwargs)
    return OrderData(**defaults)


def test_precio_unitario_polo():
    """Polo unitario S/ 35."""
    p = PricingAgent()
    state = SharedState()
    order = _build_order(cantidad=1, acabado="ninguno")
    result = p.quote(order, state)
    assert result.precio_unitario == 35.0
    assert result.subtotal == 35.0
    assert result.descuento_porcentaje == 0.0
    assert result.total == 35.0
    assert result.adelanto == 17.5


def test_descuento_50_unidades():
    """50+ unidades → 10% descuento."""
    p = PricingAgent()
    state = SharedState()
    order = _build_order(cantidad=50, acabado="bordado")  # 35 + 10 = 45 por unidad
    result = p.quote(order, state)
    assert result.descuento_porcentaje == 0.10
    assert result.subtotal == 50 * 45.0
    assert result.descuento_monto == round(result.subtotal * 0.10, 2)
    assert result.total == round(result.subtotal * 0.90, 2)


def test_descuento_100_unidades():
    """100+ unidades → 15% descuento."""
    p = PricingAgent()
    state = SharedState()
    order = _build_order(cantidad=100, acabado="ninguno")
    result = p.quote(order, state)
    assert result.descuento_porcentaje == 0.15


def test_descuento_200_unidades():
    """200+ unidades → 20% descuento (caso adversarial: cantidad muy alta)."""
    p = PricingAgent()
    state = SharedState()
    order = _build_order(cantidad=500, acabado="estampado")
    result = p.quote(order, state)
    assert result.descuento_porcentaje == 0.20


def test_adelanto_siempre_50_porciento():
    p = PricingAgent()
    state = SharedState()
    order = _build_order(cantidad=25)
    result = p.quote(order, state)
    assert result.adelanto == round(result.total * 0.5, 2)


def test_acabado_bordado_suma_10():
    """El bordado agrega S/ 10 por prenda."""
    p = PricingAgent()
    state = SharedState()
    order_sin = _build_order(cantidad=1, acabado="ninguno")
    order_con = _build_order(cantidad=1, acabado="bordado")
    r1 = p.quote(order_sin, state)
    state2 = SharedState()
    r2 = p.quote(order_con, state2)
    assert r2.subtotal - r1.subtotal == 10.0


def test_alias_de_prendas():
    """'polera' debe resolverse al precio de polo."""
    p = PricingAgent()
    state = SharedState()
    order = _build_order(tipo_prenda="polera", cantidad=1, acabado="ninguno")
    result = p.quote(order, state)
    assert result.precio_unitario == 35.0
