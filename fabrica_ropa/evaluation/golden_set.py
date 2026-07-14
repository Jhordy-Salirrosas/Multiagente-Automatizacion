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
        salida_esperada="S/ 35.00 + S/ 5.00 de estampado = S/ 40.00 por unidad",
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
        salida_esperada="precio_unit=35+10=45, subtotal=4500, desc=15%=-675, total=3825, adelanto=1912.50",
        categoria="cotizacion",
        requisito="RF-03",
        notas="Cálculo completo con descuento del 15%",
    ),
    GoldenCase(
        case_id="C-08",
        entrada="200 polos sin acabado",
        salida_esperada="precio_unit=35, subtotal=7000, desc=20%=-1400, total=5600, adelanto=2800",
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

    # =========================================================================
    # GOLDEN SET DEL DOCUMENTO §5.1 (GS-01 a GS-10)
    # Cubre ambos procesos: Realizar Pedido + Compra de Materiales
    # =========================================================================

    # --- Proceso 1: Realizar Pedido ---
    GoldenCase(
        case_id="GS-01",
        entrada="Necesito 100 polos de algodón con estampado para mi empresa",
        salida_esperada="Pedido validado, cotización generada con descuento 15%, total S/ 3,400.00",
        categoria="e2e",
        requisito="RF-01, RF-03",
        notas="Flujo completo: validación → recolección → cotización",
    ),
    GoldenCase(
        case_id="GS-02",
        entrada="¿Cuánto costaría 50 camisas con bordado?",
        salida_esperada="50 × (S/ 55 + S/ 10) = S/ 3,250 - 10% = S/ 2,925, adelanto S/ 1,462.50",
        categoria="cotizacion",
        requisito="RF-03",
        notas="Cotización con acabado bordado y descuento por 50+ unidades",
    ),
    GoldenCase(
        case_id="GS-03",
        entrada="Quiero confirmar mi pago por transferencia de S/ 1,462.50",
        salida_esperada="Pago confirmado, comprobante generado",
        categoria="pago",
        requisito="RF-04",
        notas="Procesamiento de pago por el monto exacto del adelanto",
    ),

    # --- Proceso 2: Compra de Materiales ---
    GoldenCase(
        case_id="GS-04",
        entrada="Generar lista de materiales para los pedidos de esta semana",
        salida_esperada="Lista: tela algodón 120m, hilo 6 conos, botones 200, etiquetas 100",
        categoria="materiales",
        requisito="RF-09",
        notas="MaterialPlannerAgent consolida materiales de pedidos pendientes",
    ),
    GoldenCase(
        case_id="GS-05",
        entrada="Estimar presupuesto para la compra de materiales",
        salida_esperada="Presupuesto estimado: S/ 1,850.00 basado en catálogo y historial",
        categoria="presupuesto",
        requisito="RF-10",
        notas="BudgetAgent usa RAG + catálogo para estimar",
    ),
    GoldenCase(
        case_id="GS-06",
        entrada="Aprobar presupuesto de S/ 1,850.00 para compra de materiales",
        salida_esperada="Presupuesto aprobado, procediendo con selección de proveedor",
        categoria="hitl",
        requisito="RF-11",
        notas="HITL: ApprovalAgent espera decisión humana",
    ),
    GoldenCase(
        case_id="GS-07",
        entrada="Seleccionar proveedor para la compra",
        salida_esperada="Proveedor seleccionado: Textiles del Norte SAC (95% cumplimiento)",
        categoria="proveedor",
        requisito="RF-11",
        notas="SupplierAgent selecciona por cumplimiento y ubicación",
    ),
    GoldenCase(
        case_id="GS-08",
        entrada="El proveedor principal no tiene stock de tela algodón",
        salida_esperada="Proveedor alternativo: Distribuidora Textil Sur SA",
        categoria="proveedor",
        requisito="RF-11",
        notas="Fallback a proveedor alternativo con HITL",
    ),
    GoldenCase(
        case_id="GS-09",
        entrada="Confirmar recepción de materiales de la orden OC-20260714-ABC123",
        salida_esperada="Materiales recibidos, producción notificada",
        categoria="produccion",
        requisito="RF-12",
        notas="ProductionAgent notifica tras confirmar recepción",
    ),
    GoldenCase(
        case_id="GS-10",
        entrada="¿Cuál es el historial de compras con Textiles del Norte?",
        salida_esperada="Historial: 12 compras en 6 meses, cumplimiento 95%, precio promedio S/ 12.50/m",
        categoria="rag",
        requisito="RF-10",
        notas="Consulta RAG sobre historial de proveedores",
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
