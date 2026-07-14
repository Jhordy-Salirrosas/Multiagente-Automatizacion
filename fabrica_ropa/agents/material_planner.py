"""
MaterialPlannerAgent — Genera la lista semanal de materiales requeridos (§3.5/§3.6).

Revisa los pedidos aprobados (pagados), consulta el catálogo de materiales
para determinar qué se necesita y genera una lista consolidada.
"""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from agents.base import BaseAgent
from core.mcp_messages import AgentName, MaterialPlan
from core.shared_state import SharedState
from config import DB_PATH, BASE_DIR

try:
    from langsmith import traceable  # type: ignore
except ImportError:
    def traceable(*args, **kwargs):
        def decorator(func): return func
        if args and callable(args[0]): return args[0]
        return decorator


SYSTEM_PROMPT = """Eres un asistente encargado de abastecimiento de una fábrica de ropa.
Tu tarea es transformar los detalles de los pedidos en una lista estructurada
de materiales requeridos para producción.

REGLAS:
- Analiza cada pedido (tipo de prenda, cantidad, acabado).
- Calcula los materiales necesarios según el catálogo.
- Consolida materiales iguales de distintos pedidos.
- Responde con JSON: {"materiales": ["material1", ...], "cantidades": [cant1, ...], "resumen": "..."}
"""

MATERIALS_CATALOG_PATH = BASE_DIR / "data" / "materials_catalog.json"


class MaterialPlannerAgent(BaseAgent):
    """Agente que genera la lista semanal de materiales."""

    def __init__(self):
        super().__init__(
            agent_name=AgentName.MATERIAL_PLANNER,
            system_prompt=SYSTEM_PROMPT,
        )
        self._catalog = self._load_catalog()

    @staticmethod
    def _load_catalog() -> dict:
        if MATERIALS_CATALOG_PATH.exists():
            with open(MATERIALS_CATALOG_PATH, encoding="utf-8") as f:
                return json.load(f)
        return {}

    @traceable(name="MaterialPlannerAgent.plan")
    def plan(self, state: SharedState) -> MaterialPlan:
        """
        Genera la lista de materiales para los pedidos pendientes.

        Returns:
            MaterialPlan con materiales y cantidades consolidadas.
        """
        # Obtener pedidos pagados (pendientes de producción)
        pedidos = self._get_paid_orders()

        if not pedidos:
            result = MaterialPlan(
                pedido_id="PLAN-SEMANAL",
                materiales=["Sin materiales requeridos"],
                cantidades=[0],
            )
            state.material_plan = result
            self.emit_event("materials_planned", count=0)
            return result

        # Calcular materiales necesarios
        materiales_consolidados = self._calculate_materials(pedidos)

        # Usar LLM para generar resumen
        prompt = (
            f"Genera un resumen de la lista de materiales para producción:\n"
            f"Pedidos procesados: {len(pedidos)}\n"
            f"Materiales: {json.dumps(materiales_consolidados, ensure_ascii=False)}\n"
            f"Responde con JSON: {{\"materiales\": [...], \"cantidades\": [...], \"resumen\": \"...\"}}"
        )
        raw = self.run(prompt, state)

        # Parsear o usar cálculo determinístico
        nombres = list(materiales_consolidados.keys())
        cantidades = [round(v, 2) for v in materiales_consolidados.values()]

        try:
            data = json.loads(self.extract_agent_text(raw))
            if "materiales" in data and "cantidades" in data:
                nombres = data["materiales"]
                cantidades = data["cantidades"]
        except (json.JSONDecodeError, TypeError):
            pass

        # LÓGICA DE ALMACÉN INTELIGENTE (Asignación)
        en_stock = []
        a_comprar = []
        
        with state._lock:
            for mat_name, req_qty in zip(nombres, cantidades):
                req_float = float(req_qty)
                stock_actual = state.inventory.get(mat_name, 0.0)
                safety = state.safety_stock.get(mat_name, 0.0)
                max_cap = state.max_capacity.get(mat_name, stock_actual * 2)
                
                # Asignar del stock lo más que se pueda
                asignado = min(req_float, stock_actual)
                
                # El inventario proyectado después de asignar
                inventario_proyectado = stock_actual - asignado
                
                # ¿Se rompe el stock de seguridad? (Punto de Reorden Dinámico)
                if inventario_proyectado < safety:
                    # Comprar lo necesario para llenar el almacén a tope (Max Capacity)
                    faltante_para_tope = max_cap - inventario_proyectado
                    # Nos aseguramos de comprar al menos lo que nos falta para cubrir el pedido
                    # (aunque con la capacidad máxima siempre lo excederá, es buena práctica)
                    faltante_real = req_float - asignado
                    a_comprar_final = max(faltante_para_tope, faltante_real)
                else:
                    a_comprar_final = 0.0
                
                en_stock.append(round(asignado, 2))
                a_comprar.append(round(a_comprar_final, 2))
                
                # Descontar del stock temporalmente
                if mat_name in state.inventory:
                    state.inventory[mat_name] -= asignado

        result = MaterialPlan(
            pedido_id="PLAN-SEMANAL",
            materiales=nombres,
            cantidades=[float(c) for c in cantidades],
            en_stock=en_stock,
            a_comprar=a_comprar
        )
        state.material_plan = result
        self.emit_event("materials_planned", count=len(nombres))
        return result

    def _calculate_materials(self, pedidos: list[dict]) -> dict[str, float]:
        """Calcula materiales consolidados determinísticamente."""
        catalog = self._catalog.get("materiales", {})
        consolidated: dict[str, float] = {}

        for pedido in pedidos:
            tipo = pedido.get("tipo_prenda", "polo").lower()
            cantidad = pedido.get("cantidad", 0)
            acabado = pedido.get("acabado", "ninguno").lower()

            for mat_name, mat_info in catalog.items():
                consumo = mat_info.get("consumo_por_prenda", {})

                # Material base (por tipo de prenda)
                if tipo in consumo:
                    uso = consumo[tipo] * cantidad
                    consolidated[mat_name] = consolidated.get(mat_name, 0) + uso

                # Material de acabado
                if acabado in consumo:
                    uso = consumo[acabado] * cantidad
                    consolidated[mat_name] = consolidated.get(mat_name, 0) + uso

        return {k: round(v, 2) for k, v in consolidated.items() if v > 0}

    @staticmethod
    def _get_paid_orders() -> list[dict]:
        """Obtiene pedidos pagados de SQLite."""
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM pedidos WHERE estado IN ('Pagado', 'Pendiente de pago')"
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception:
            return []

    def _default_mock_response(self, prompt: str) -> str:
        return json.dumps({
            "materiales": ["tela algodón", "hilo industrial", "etiquetas", "botones"],
            "cantidades": [120, 6, 100, 200],
            "resumen": "Lista de materiales para 100 polos y producciones pendientes.",
        }, ensure_ascii=False)
