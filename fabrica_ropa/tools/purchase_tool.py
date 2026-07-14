"""
Purchase Tool — Gestión de compra de materiales con proveedores (§3.4).

Registra órdenes de compra en SQLite, gestiona la comunicación con
proveedores y maneja el fallback a proveedores alternativos.
"""
from __future__ import annotations
import json
import uuid
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from config import DB_PATH, BASE_DIR

try:
    from langchain_core.tools import tool as langchain_tool  # type: ignore
except ImportError:
    def langchain_tool(func):
        return func


SUPPLIERS_PATH = BASE_DIR / "data" / "suppliers.json"


class PurchaseTool:
    """
    Tool de compra de materiales.
    Registra órdenes de compra y coordina con proveedores.
    """

    SCHEMA_COMPRAS = """
    CREATE TABLE IF NOT EXISTS compras_materiales (
        orden_id            TEXT PRIMARY KEY,
        proveedor_id        TEXT NOT NULL,
        proveedor_nombre    TEXT NOT NULL,
        materiales          TEXT NOT NULL,
        monto_total         REAL NOT NULL,
        fecha_orden         TEXT NOT NULL,
        fecha_entrega_est   TEXT NOT NULL,
        estado              TEXT NOT NULL,
        pedidos_asociados   TEXT
    );
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or DB_PATH)
        self._ensure_schema()
        self._suppliers = self._load_suppliers()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.SCHEMA_COMPRAS)
            conn.commit()

    @staticmethod
    def _load_suppliers() -> list[dict]:
        if SUPPLIERS_PATH.exists():
            with open(SUPPLIERS_PATH, encoding="utf-8") as f:
                return json.load(f).get("proveedores", [])
        return []

    def purchase(
        self,
        proveedor_id: str,
        lista_materiales: list[dict],
        monto_total: float,
        pedidos_asociados: list[str] | None = None,
    ) -> dict:
        """
        Registra una orden de compra de materiales.

        Args:
            proveedor_id: ID del proveedor seleccionado.
            lista_materiales: Lista de materiales a comprar.
            monto_total: Monto total de la compra.
            pedidos_asociados: IDs de pedidos que originaron la compra.

        Returns:
            Dict con orden_compra_id y detalles.
        """
        # Buscar proveedor
        proveedor = None
        for p in self._suppliers:
            if p["id"] == proveedor_id:
                proveedor = p
                break

        if not proveedor:
            # Fallback: usar primer proveedor disponible
            if self._suppliers:
                proveedor = self._suppliers[0]
            else:
                proveedor = {"id": "PROV-DEFAULT", "nombre": "Proveedor General",
                             "tiempo_entrega_dias": 7}

        orden_id = f"OC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        fecha_entrega = (
            datetime.now() + timedelta(days=proveedor.get("tiempo_entrega_dias", 7))
        ).strftime("%Y-%m-%d")

        # Registrar en SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO compras_materiales VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    orden_id,
                    proveedor["id"],
                    proveedor["nombre"],
                    json.dumps(lista_materiales, ensure_ascii=False),
                    monto_total,
                    datetime.now().isoformat(),
                    fecha_entrega,
                    "Ordenado",
                    json.dumps(pedidos_asociados or []),
                ),
            )
            conn.commit()

        return {
            "orden_compra_id": orden_id,
            "proveedor": proveedor["nombre"],
            "materiales_confirmados": True,
            "fecha_entrega": fecha_entrega,
            "monto_total": monto_total,
        }

    def get_alternative_supplier(self, proveedor_id_excluir: str) -> dict | None:
        """Busca un proveedor alternativo excluyendo el dado."""
        for p in self._suppliers:
            if p["id"] != proveedor_id_excluir:
                return p
        return None

    def confirm_reception(self, orden_id: str) -> bool:
        """Confirma la recepción de materiales de una orden."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE compras_materiales SET estado = ? WHERE orden_id = ?",
                ("Recibido", orden_id),
            )
            conn.commit()
        return True


@langchain_tool
def purchase_materials(
    proveedor_id: str, lista_materiales: str, monto_total: float
) -> str:
    """Registra una orden de compra de materiales con un proveedor.

    Args:
        proveedor_id: ID del proveedor seleccionado.
        lista_materiales: JSON con lista de materiales a comprar.
        monto_total: Monto total de la compra.
    """
    tool = PurchaseTool()
    try:
        items = json.loads(lista_materiales)
    except (json.JSONDecodeError, TypeError):
        items = [{"material": "general", "cantidad": 1}]
    result = tool.purchase(proveedor_id, items, monto_total)
    return f"Orden {result['orden_compra_id']} registrada con {result['proveedor']}"
