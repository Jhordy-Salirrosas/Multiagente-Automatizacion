"""
Budget Tool — Estima presupuesto de compra de materiales (§3.4).

Calcula el presupuesto semanal utilizando el historial de compras
y los materiales requeridos para los pedidos aprobados.
"""
from __future__ import annotations
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, BASE_DIR

try:
    from langchain_core.tools import tool as langchain_tool  # type: ignore
except ImportError:
    def langchain_tool(func):
        return func


# Cargar catálogo de materiales
MATERIALS_CATALOG_PATH = BASE_DIR / "data" / "materials_catalog.json"


class BudgetTool:
    """
    Tool de estimación de presupuesto.
    Calcula el costo de materiales para los pedidos pendientes.
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or DB_PATH)
        self._materials_catalog = self._load_materials_catalog()

    @staticmethod
    def _load_materials_catalog() -> dict:
        if MATERIALS_CATALOG_PATH.exists():
            with open(MATERIALS_CATALOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def estimate(self, lista_materiales: list[dict]) -> dict:
        """
        Estima el presupuesto para una lista de materiales.

        Args:
            lista_materiales: Lista de dicts con {material, cantidad, unidad}.

        Returns:
            Dict con presupuesto_estimado, desglose y proveedor_recomendado.
        """
        catalogo = self._materials_catalog
        proveedores = self._load_suppliers()
        desglose = []
        total = 0.0

        for item in lista_materiales:
            material = item.get("material", "")
            cantidad = item.get("cantidad", 0)

            # Buscar precio en catálogo
            precio_unit = 0.0
            if material.lower() in catalogo.get("materiales", {}):
                precio_unit = catalogo["materiales"][material.lower()].get(
                    "precio_unitario", 0.0
                )
            else:
                # Precio estimado por defecto
                precio_unit = 15.0

            subtotal = round(precio_unit * cantidad, 2)
            total += subtotal
            desglose.append({
                "material": material,
                "cantidad": cantidad,
                "precio_unitario": precio_unit,
                "subtotal": subtotal,
            })

        # Recomendar proveedor con menor precio promedio
        proveedor_rec = "Proveedor General"
        if proveedores:
            proveedor_rec = proveedores[0].get("nombre", "Proveedor General")

        return {
            "presupuesto_estimado": round(total, 2),
            "desglose": desglose,
            "proveedor_recomendado": proveedor_rec,
            "fecha_estimacion": datetime.now().isoformat(),
        }

    @staticmethod
    def _load_suppliers() -> list[dict]:
        suppliers_path = BASE_DIR / "data" / "suppliers.json"
        if suppliers_path.exists():
            with open(suppliers_path, encoding="utf-8") as f:
                return json.load(f).get("proveedores", [])
        return []

    def get_pending_orders(self) -> list[dict]:
        """Obtiene pedidos pendientes de producción de SQLite."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM pedidos WHERE estado = 'Pagado'"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []


@langchain_tool
def estimate_budget(lista_materiales: str) -> str:
    """Estima el presupuesto de compra de materiales.

    Calcula el costo total basado en el catálogo de materiales y el historial.

    Args:
        lista_materiales: JSON string con lista de {material, cantidad, unidad}.
    """
    tool = BudgetTool()
    try:
        items = json.loads(lista_materiales) if isinstance(lista_materiales, str) else lista_materiales
    except json.JSONDecodeError:
        return "Error: lista_materiales debe ser un JSON válido."
    result = tool.estimate(items)
    return f"Presupuesto estimado: S/ {result['presupuesto_estimado']:.2f}"
