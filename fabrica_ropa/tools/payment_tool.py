"""
Payment Tool — Procesa pagos de pedidos (§3.4).

Valida el pago del cliente, actualiza el estado del pedido en SQLite
y genera un comprobante digital simulado.
"""
from __future__ import annotations
import uuid
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH

try:
    from langchain_core.tools import tool as langchain_tool  # type: ignore
except ImportError:
    def langchain_tool(func):
        return func


class PaymentTool:
    """Tool de procesamiento de pagos. Actualiza estado del pedido y genera comprobante."""

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or DB_PATH)

    def process_payment(
        self,
        pedido_id: str,
        monto: float,
        metodo_pago: str = "transferencia",
    ) -> dict:
        """
        Procesa el pago de un pedido.

        Args:
            pedido_id: ID del pedido a pagar.
            monto: Monto del pago.
            metodo_pago: Método de pago (transferencia, tarjeta, efectivo).

        Returns:
            Dict con estado_pago, comprobante_id y detalles.
        """
        # Verificar que el pedido existe
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM pedidos WHERE pedido_id = ?", (pedido_id,)
            ).fetchone()

        if not row:
            return {
                "pago_confirmado": False,
                "error": f"Pedido {pedido_id} no encontrado.",
            }

        pedido = dict(row)
        adelanto = pedido.get("adelanto", 0)

        # Validar monto (tolerancia del 1%)
        if monto < adelanto * 0.99:
            return {
                "pago_confirmado": False,
                "error": f"Monto insuficiente. Se requiere S/ {adelanto:.2f}, recibido S/ {monto:.2f}.",
            }

        # Generar comprobante
        comprobante_id = f"COMP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Actualizar estado del pedido
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE pedidos SET estado = ? WHERE pedido_id = ?",
                ("Pagado", pedido_id),
            )
            conn.commit()

        return {
            "pago_confirmado": True,
            "comprobante_id": comprobante_id,
            "pedido_id": pedido_id,
            "monto": monto,
            "metodo_pago": metodo_pago,
            "timestamp": datetime.now().isoformat(),
        }


@langchain_tool
def process_payment(pedido_id: str, monto: float, metodo_pago: str = "transferencia") -> str:
    """Procesa el pago de un pedido y actualiza su estado.

    Valida el monto, actualiza el estado en la base de datos y genera un comprobante.

    Args:
        pedido_id: ID del pedido a pagar.
        monto: Monto del pago en soles.
        metodo_pago: Método de pago utilizado.
    """
    tool = PaymentTool()
    result = tool.process_payment(pedido_id, monto, metodo_pago)
    if result["pago_confirmado"]:
        return f"Pago confirmado. Comprobante: {result['comprobante_id']}"
    return f"Error en pago: {result.get('error', 'desconocido')}"
