"""
Sheets Tool — Simula la "Escritura en Google Sheets" del N8N original
usando SQLite local. Mismo esquema de columnas que el Google Sheet.
"""
from __future__ import annotations
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from config import DB_PATH

# LangChain @tool — expone la herramienta como tool LangChain (§3.4)
try:
    from langchain_core.tools import tool as langchain_tool  # type: ignore
except ImportError:
    def langchain_tool(func):
        """No-op si langchain_core no está instalado."""
        return func


class SheetsTool:
    """
    Tool de persistencia. Crea/actualiza tablas con todas las
    columnas del pedido y del proceso de compra. El RegistryAgent usa esta tool.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS pedidos (
        pedido_id           TEXT PRIMARY KEY,
        session_id          TEXT NOT NULL,
        timestamp_registro  TEXT NOT NULL,
        nombre              TEXT NOT NULL,
        email               TEXT NOT NULL,
        tipo_prenda         TEXT NOT NULL,
        cantidad            INTEGER NOT NULL,
        talla               TEXT NOT NULL,
        color               TEXT NOT NULL,
        acabado             TEXT NOT NULL,
        fecha_entrega       TEXT NOT NULL,
        subtotal            REAL NOT NULL,
        descuento_porc      REAL NOT NULL,
        descuento_monto     REAL NOT NULL,
        total               REAL NOT NULL,
        adelanto            REAL NOT NULL,
        estado              TEXT NOT NULL
    );
    """

    SCHEMA_PRESUPUESTOS = """
    CREATE TABLE IF NOT EXISTS presupuestos (
        presupuesto_id      TEXT PRIMARY KEY,
        fecha               TEXT NOT NULL,
        presupuesto_estimado REAL NOT NULL,
        proveedor_recomendado TEXT NOT NULL,
        justificacion       TEXT,
        estado              TEXT NOT NULL,
        materiales_json     TEXT,
        pedidos_asociados   TEXT
    );
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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.SCHEMA)
            conn.execute(self.SCHEMA_PRESUPUESTOS)
            conn.execute(self.SCHEMA_COMPRAS)
            conn.commit()

    def append_row(
        self,
        session_id: str,
        nombre: str,
        email: str,
        tipo_prenda: str,
        cantidad: int,
        talla: str,
        color: str,
        acabado: str,
        fecha_entrega: str,
        subtotal: float,
        descuento_porc: float,
        descuento_monto: float,
        total: float,
        adelanto: float,
        estado: str = "Pendiente de pago",
    ) -> str:
        """Inserta un pedido y devuelve el pedido_id generado."""
        pedido_id = f"PED-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO pedidos VALUES (
                    ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
                )""",
                (
                    pedido_id, session_id, datetime.now().isoformat(),
                    nombre, email, tipo_prenda, cantidad, talla, color,
                    acabado, fecha_entrega,
                    subtotal, descuento_porc, descuento_monto,
                    total, adelanto, estado,
                ),
            )
            conn.commit()
        return pedido_id

    def get_pedido(self, pedido_id: str) -> dict | None:
        """Recupera un pedido por ID."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM pedidos WHERE pedido_id = ?", (pedido_id,)).fetchone()
            return dict(row) if row else None

    def count_pedidos(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]

    # ── Proceso 2: Helpers de consulta ──

    def get_pedidos_by_estado(self, estado: str) -> list[dict]:
        """Obtiene pedidos por estado (para MaterialPlannerAgent)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM pedidos WHERE estado = ?", (estado,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_compras(self) -> list[dict]:
        """Lista todas las compras de materiales."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM compras_materiales").fetchall()
            return [dict(r) for r in rows]

    def get_presupuestos(self) -> list[dict]:
        """Lista todos los presupuestos."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM presupuestos").fetchall()
            return [dict(r) for r in rows]


# =============================================================================
# LangChain Tool — función standalone para uso con agentes LangChain (§3.4)
# =============================================================================

@langchain_tool
def save_order_to_db(
    session_id: str,
    nombre: str,
    email: str,
    tipo_prenda: str,
    cantidad: int,
    talla: str,
    color: str,
    acabado: str,
    fecha_entrega: str,
    subtotal: float,
    descuento_porc: float,
    descuento_monto: float,
    total: float,
    adelanto: float,
) -> str:
    """Guarda un pedido confirmado en la base de datos SQLite.

    Registra todos los datos del pedido y la cotización.
    Devuelve el ID del pedido generado.

    Args:
        session_id: ID de la sesión.
        nombre: Nombre del cliente.
        email: Email del cliente.
        tipo_prenda: Tipo de prenda (polo, camisa, etc.).
        cantidad: Número de unidades.
        talla: Talla(s) del pedido.
        color: Color deseado.
        acabado: Tipo de acabado (ninguno, estampado, bordado).
        fecha_entrega: Fecha de entrega en formato ISO.
        subtotal: Subtotal del pedido.
        descuento_porc: Porcentaje de descuento.
        descuento_monto: Monto del descuento.
        total: Total final.
        adelanto: Monto del adelanto (50%).
    """
    tool = SheetsTool()
    pedido_id = tool.append_row(
        session_id=session_id, nombre=nombre, email=email,
        tipo_prenda=tipo_prenda, cantidad=cantidad, talla=talla,
        color=color, acabado=acabado, fecha_entrega=fecha_entrega,
        subtotal=subtotal, descuento_porc=descuento_porc,
        descuento_monto=descuento_monto, total=total, adelanto=adelanto,
    )
    return f"Pedido registrado con ID: {pedido_id}"
