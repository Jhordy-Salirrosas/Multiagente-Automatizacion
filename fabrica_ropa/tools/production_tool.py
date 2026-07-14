"""
Production Tool — Notifica al área de producción (§3.4).

Envía notificaciones al área de producción cuando los materiales
han sido recibidos y el pedido puede iniciar su fabricación.
"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

from config import BASE_DIR

try:
    from langchain_core.tools import tool as langchain_tool  # type: ignore
except ImportError:
    def langchain_tool(func):
        return func


NOTIFICATIONS_DIR = BASE_DIR / "data" / "notificaciones_produccion"


class ProductionTool:
    """
    Tool de notificación a producción.
    Genera un archivo de notificación para el área de producción.
    """

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or NOTIFICATIONS_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def notify(
        self,
        pedido_ids: list[str],
        materiales_recibidos: list[str],
        orden_compra_id: str = "",
    ) -> dict:
        """
        Notifica a producción que los materiales están listos.

        Args:
            pedido_ids: IDs de los pedidos asociados.
            materiales_recibidos: Lista de materiales recibidos.
            orden_compra_id: ID de la orden de compra.

        Returns:
            Dict con confirmación y ruta de la notificación.
        """
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"notif_produccion_{ts}.json"
        filepath = self.output_dir / filename

        notification = {
            "tipo": "materiales_recibidos",
            "timestamp": datetime.now().isoformat(),
            "pedidos_asociados": pedido_ids,
            "materiales": materiales_recibidos,
            "orden_compra_id": orden_compra_id,
            "mensaje": (
                f"Los materiales de la orden {orden_compra_id} han sido recibidos. "
                f"Se puede iniciar la producción de los pedidos: {', '.join(pedido_ids)}."
            ),
            "estado": "Notificado",
        }

        filepath.write_text(
            json.dumps(notification, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "notificado": True,
            "archivo": str(filepath),
            "pedidos": pedido_ids,
            "mensaje": notification["mensaje"],
        }


@langchain_tool
def notify_production(pedido_ids: str, materiales: str, orden_compra_id: str = "") -> str:
    """Notifica al área de producción que los materiales fueron recibidos.

    Genera una notificación formal para que producción inicie la fabricación.

    Args:
        pedido_ids: JSON list de IDs de pedidos asociados.
        materiales: JSON list de materiales recibidos.
        orden_compra_id: ID de la orden de compra.
    """
    tool = ProductionTool()
    try:
        ids = json.loads(pedido_ids) if isinstance(pedido_ids, str) else pedido_ids
        mats = json.loads(materiales) if isinstance(materiales, str) else materiales
    except (json.JSONDecodeError, TypeError):
        ids = [pedido_ids]
        mats = [materiales]
    result = tool.notify(ids, mats, orden_compra_id)
    return f"Producción notificada: {result['mensaje']}"
