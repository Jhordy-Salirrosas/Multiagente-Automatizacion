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


class SheetsTool:
    """
    Tool de persistencia. Crea/actualiza una tabla 'pedidos' con todas las
    columnas del pedido. El RegistryAgent usa esta tool.
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

    def __init__(self, db_path: str | None = None):
        self.db_path = Path(db_path or DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.SCHEMA)
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
