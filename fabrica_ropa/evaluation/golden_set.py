"""
Golden Set — §5.1 de la plantilla.

Conjunto de evaluación con pares (entrada, salida esperada)
para medir la calidad del sistema y detectar regresiones.

Cada caso incluye:
  - ID único (C-01, C-02, ...)
  - Entrada (pregunta del usuario)
  - Salida esperada
  - Categoría (validación, RAG, cotización, etc.)
  - Requisito funcional vinculado (RF-01, RF-02, ...)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class GoldenCase:
    """Un caso del golden set."""
    case_id: str
    entrada: str
    salida_esperada: str
    categoria: str
    requisito: str
    notas: Optional[str] = None


# =============================================================================
# GOLDEN SET — 10 CASOS (§5.1)
# =============================================================================

GOLDEN_SET: list[GoldenCase] = [
    # --- Validación de rubro (ValidatorAgent) ---
    GoldenCase(
        case_id="C-01",
        entrada="Necesito 50 polos para mi empresa",
        salida_esperada="is_textile=True",
        categoria="validacion",
        requisito="RF-01",
        notas="Caso estándar de pedido textil",
    ),
    GoldenCase(
        case_id="C-02",
        entrada="Quiero pedir 20 pizzas para un evento",
        salida_esperada="is_textile=False",
        categoria="validacion",
        requisito="RF-01",
        notas="Pedido fuera del rubro (comida)",
    ),
    GoldenCase(
        case_id="C-03",
        entrada="Hola, buenos días",
        salida_esperada="is_textile=True, confidence<=0.5",
        categoria="validacion",
        requisito="RF-01",
        notas="Mensaje ambiguo (saludo), se asume intención textil",
    ),

    # --- RAG (preguntas sobre el catálogo) ---
    GoldenCase(
        case_id="C-04",
        entrada="¿Cuánto cuesta un polo con estampado?",
        salida_esperada="S/ 25.00 + S/ 8.00 de estampado = S/ 33.00 por unidad",
        categoria="rag",
        requisito="RF-02",
        notas="Debe combinar precio base + acabado del catálogo",
    ),
    GoldenCase(
        case_id="C-05",
        entrada="¿Qué descuento hay para 150 unidades?",
        salida_esperada="15% de descuento para pedidos de 100 a 199 unidades",
        categoria="rag",
        requisito="RF-02",
        notas="Debe encontrar el tramo correcto de descuento",
    ),
    GoldenCase(
        case_id="C-06",
        entrada="¿Cuánto tiempo demora hacer 50 camisas?",
        salida_esperada="10-15 días hábiles",
        categoria="rag",
        requisito="RF-02",
        notas="Buscar el tiempo de confección de camisas en el catálogo",
    ),

    # --- Cotización (PricingAgent) ---
    GoldenCase(
        case_id="C-07",
        entrada="100 polos bordados",
        salida_esperada="precio_unit=25+12=37, subtotal=3700, desc=15%=-555, total=3145, adelanto=1572.50",
        categoria="cotizacion",
        requisito="RF-03",
        notas="Cálculo completo con descuento del 15%",
    ),
    GoldenCase(
        case_id="C-08",
        entrada="200 polos sin acabado",
        salida_esperada="precio_unit=25, subtotal=5000, desc=20%=-1000, total=4000, adelanto=2000",
        categoria="cotizacion",
        requisito="RF-03",
        notas="Descuento máximo del 20%",
    ),

    # --- Flujo completo (end-to-end) ---
    GoldenCase(
        case_id="C-09",
        entrada="Quiero comprar una laptop gaming",
        salida_esperada="Rechazado: no es del rubro textil",
        categoria="e2e",
        requisito="RF-01",
        notas="El flujo debe terminar en REJECTED",
    ),
    GoldenCase(
        case_id="C-10",
        entrada="¿Aceptan pedidos urgentes?",
        salida_esperada="Sí, con un recargo del 20% se puede reducir el plazo",
        categoria="rag",
        requisito="RF-02",
        notas="Información de pedidos urgentes en el catálogo",
    ),
]


def get_golden_set(categoria: Optional[str] = None) -> list[GoldenCase]:
    """
    Devuelve el golden set, opcionalmente filtrado por categoría.

    Categorías: validacion, rag, cotizacion, e2e
    """
    if categoria is None:
        return GOLDEN_SET
    return [c for c in GOLDEN_SET if c.categoria == categoria]


def golden_set_as_dicts() -> list[dict]:
    """Devuelve el golden set como lista de dicts (para DataFrames/LangSmith)."""
    return [
        {
            "case_id": c.case_id,
            "entrada": c.entrada,
            "salida_esperada": c.salida_esperada,
            "categoria": c.categoria,
            "requisito": c.requisito,
            "notas": c.notas or "",
        }
        for c in GOLDEN_SET
    ]
