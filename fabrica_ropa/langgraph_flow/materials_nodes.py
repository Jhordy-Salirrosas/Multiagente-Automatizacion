"""
Nodos del grafo LangGraph para Compra de Materiales — §3.5 Proceso 2.

Cada nodo es una función pura que recibe el estado y devuelve un parche.
Nodos:
  - nodo_planificar_materiales: Genera lista de materiales requeridos
  - nodo_estimar_presupuesto: Calcula presupuesto con RAG + catálogo
  - nodo_aprobar_presupuesto: HITL — prepara info para aprobación humana
  - nodo_seleccionar_proveedor: Selecciona proveedor y registra compra
  - nodo_notificar_produccion: Notifica a producción
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph_flow.state import EstadoPedido
from config import EXECUTION_MODE, LLM_API_KEY, get_langchain_llm, BASE_DIR


def _call_llm(prompt: str) -> str:
    """Llama al LLM configurado vía cadena LangChain LCEL."""
    if EXECUTION_MODE != "real" or not LLM_API_KEY:
        return _mock_llm(prompt)

    try:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        llm = get_langchain_llm(temperature=0.3, max_tokens=1024)
        if llm is None:
            return _mock_llm(prompt)

        chain = ChatPromptTemplate.from_messages([
            ("human", "{input}"),
        ]) | llm | StrOutputParser()

        return chain.invoke({"input": prompt})
    except Exception as e:
        print(f"[WARN] LLM error en nodo materiales: {e}")
        return _mock_llm(prompt)


def _mock_llm(prompt: str) -> str:
    """Respuesta mock para nodos de materiales."""
    p = prompt.lower()
    if "material" in p and "lista" in p:
        return json.dumps({
            "materiales": ["tela algodón", "hilo industrial", "botones", "etiquetas"],
            "cantidades": [120, 6, 200, 100],
        }, ensure_ascii=False)
    if "presupuesto" in p or "estimac" in p:
        return json.dumps({
            "presupuesto": 1850.00,
            "justificacion": "Basado en precios del catálogo y consumo por prenda.",
        }, ensure_ascii=False)
    if "proveedor" in p:
        return json.dumps({
            "proveedor_id": "PROV-001",
            "nombre": "Textiles del Norte SAC",
            "justificacion": "Mejor cumplimiento (95%) y ubicación local.",
        }, ensure_ascii=False)
    if "producción" in p or "notific" in p:
        return "Materiales recibidos. Se puede iniciar la producción."
    return "Procesado correctamente (mock)."


# =============================================================================
# NODO 1: PLANIFICAR MATERIALES
# =============================================================================

def nodo_planificar_materiales(state: EstadoPedido) -> dict:
    """
    Genera la lista de materiales requeridos para los pedidos pendientes.

    Lee: datos_pedido (o usa pedidos de la DB)
    Escribe: lista_materiales, etapa
    """
    # Cargar catálogo de materiales
    catalog_path = BASE_DIR / "data" / "materials_catalog.json"
    catalog = {}
    if catalog_path.exists():
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f).get("materiales", {})

    # Obtener pedidos pendientes
    import sqlite3
    from config import DB_PATH
    pedidos = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pedidos WHERE estado IN ('Pagado', 'Pendiente de pago')"
            ).fetchall()
            pedidos = [dict(r) for r in rows]
    except Exception:
        pass

    # Calcular materiales necesarios
    consolidated = {}
    for pedido in pedidos:
        tipo = pedido.get("tipo_prenda", "polo").lower()
        cantidad = pedido.get("cantidad", 0)
        for mat_name, mat_info in catalog.items():
            consumo = mat_info.get("consumo_por_prenda", {})
            if tipo in consumo and consumo[tipo] > 0:
                uso = consumo[tipo] * cantidad
                consolidated[mat_name] = consolidated.get(mat_name, 0) + uso

    # Si no hay pedidos, usar mock
    if not consolidated:
        consolidated = {
            "tela algodón": 120.0, "hilo industrial": 6.0,
            "botones": 200.0, "etiquetas": 100.0,
        }

    materiales = list(consolidated.keys())
    cantidades = [round(v, 2) for v in consolidated.values()]

    return {
        "lista_materiales": [
            {"material": m, "cantidad": c}
            for m, c in zip(materiales, cantidades)
        ],
        "etapa": "materiales_planificados",
        "estado_proceso": "planificado",
    }


# =============================================================================
# NODO 2: ESTIMAR PRESUPUESTO
# =============================================================================

def nodo_estimar_presupuesto(state: EstadoPedido) -> dict:
    """
    Calcula el presupuesto estimado para los materiales.

    Lee: lista_materiales
    Escribe: presupuesto, etapa
    """
    materiales = state.get("lista_materiales", [])

    # Cargar catálogo para precios
    catalog_path = BASE_DIR / "data" / "materials_catalog.json"
    catalog = {}
    if catalog_path.exists():
        with open(catalog_path, encoding="utf-8") as f:
            catalog = json.load(f).get("materiales", {})

    # Calcular presupuesto
    total = 0.0
    desglose = []
    for item in materiales:
        mat = item.get("material", "") if isinstance(item, dict) else str(item)
        cant = item.get("cantidad", 0) if isinstance(item, dict) else 0
        precio = catalog.get(mat, {}).get("precio_unitario", 15.0)
        subtotal = round(precio * cant, 2)
        total += subtotal
        desglose.append({"material": mat, "cantidad": cant, "precio": precio, "subtotal": subtotal})

    # Consultar RAG para historial
    contexto = ""
    try:
        from rag.retriever import retriever
        fragmentos = retriever.query("historial compras materiales presupuesto", k=2)
        contexto = "\n".join(fragmentos)
    except Exception:
        contexto = "Sin historial disponible."

    prompt = (
        f"Justifica este presupuesto de S/ {total:.2f} para compra de materiales.\n"
        f"Desglose: {json.dumps(desglose, ensure_ascii=False)}\n"
        f"Historial: {contexto[:300]}"
    )
    _call_llm(prompt)  # Para tracing/registro

    return {
        "presupuesto": round(total, 2),
        "etapa": "presupuesto_estimado",
        "estado_proceso": "presupuesto_calculado",
    }


# =============================================================================
# NODO 3: APROBAR PRESUPUESTO (HITL)
# =============================================================================

def nodo_aprobar_presupuesto(state: EstadoPedido) -> dict:
    """
    Nodo HITL: Prepara información para aprobación humana del presupuesto.
    El grafo se interrumpe aquí con interrupt_before para esperar
    la decisión del usuario.

    Lee: presupuesto, lista_materiales
    Escribe: presupuesto_aprobado, etapa
    """
    presupuesto = state.get("presupuesto", 0)
    materiales = state.get("lista_materiales", [])

    # Generar resumen para el aprobador
    resumen_items = ""
    for item in materiales:
        if isinstance(item, dict):
            resumen_items += f"  • {item.get('material', '?')}: {item.get('cantidad', 0)} unidades\n"

    prompt = (
        f"Genera un resumen ejecutivo para aprobar este presupuesto:\n"
        f"Total: S/ {presupuesto:.2f}\n"
        f"Materiales:\n{resumen_items}"
    )
    _call_llm(prompt)

    # Por defecto se marca como aprobado (en el UI el usuario decide)
    return {
        "presupuesto_aprobado": True,
        "etapa": "presupuesto_aprobado",
        "estado_proceso": "aprobado",
    }


# =============================================================================
# NODO 4: SELECCIONAR PROVEEDOR Y COMPRAR
# =============================================================================

def nodo_seleccionar_proveedor(state: EstadoPedido) -> dict:
    """
    Selecciona el mejor proveedor y registra la compra.

    Lee: lista_materiales, presupuesto, presupuesto_aprobado
    Escribe: proveedor, etapa
    """
    if not state.get("presupuesto_aprobado", False):
        return {
            "proveedor": "Rechazado",
            "etapa": "presupuesto_rechazado",
            "estado_proceso": "cancelado",
        }

    # Cargar proveedores
    suppliers_path = BASE_DIR / "data" / "suppliers.json"
    suppliers = []
    if suppliers_path.exists():
        with open(suppliers_path, encoding="utf-8") as f:
            suppliers = json.load(f).get("proveedores", [])

    # Seleccionar proveedor con mejor cumplimiento
    if suppliers:
        best = max(suppliers, key=lambda s: s.get("historial_cumplimiento", 0))
        proveedor_nombre = best["nombre"]
    else:
        proveedor_nombre = "Proveedor General"

    # Registrar compra
    from tools.purchase_tool import PurchaseTool
    purchase_tool = PurchaseTool()
    materiales = state.get("lista_materiales", [])
    presupuesto = state.get("presupuesto", 0)

    items = materiales if isinstance(materiales, list) else []
    proveedor_id = best["id"] if suppliers else "PROV-DEFAULT"

    purchase_data = purchase_tool.purchase(
        proveedor_id=proveedor_id,
        lista_materiales=items,
        monto_total=presupuesto,
    )

    return {
        "proveedor": purchase_data.get("proveedor", proveedor_nombre),
        "etapa": "compra_registrada",
        "estado_proceso": "comprado",
    }


# =============================================================================
# NODO 5: NOTIFICAR PRODUCCIÓN
# =============================================================================

def nodo_notificar_produccion(state: EstadoPedido) -> dict:
    """
    Notifica al área de producción que los materiales están listos.

    Lee: proveedor, lista_materiales
    Escribe: materiales_recibidos, notificaciones, etapa
    """
    from tools.production_tool import ProductionTool
    prod_tool = ProductionTool()

    materiales = state.get("lista_materiales", [])
    mat_nombres = []
    for item in materiales:
        if isinstance(item, dict):
            mat_nombres.append(item.get("material", "material"))
        else:
            mat_nombres.append(str(item))

    result = prod_tool.notify(
        pedido_ids=["PLAN-SEMANAL"],
        materiales_recibidos=mat_nombres,
        orden_compra_id=f"OC-{state.get('proveedor', 'N/A')}",
    )

    return {
        "materiales_recibidos": True,
        "notificaciones": [result.get("mensaje", "Producción notificada")],
        "etapa": "produccion_notificada",
        "estado_proceso": "completado",
    }
