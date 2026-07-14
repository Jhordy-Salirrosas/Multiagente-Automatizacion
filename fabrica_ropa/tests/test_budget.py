"""Tests de la estimación de presupuestos (BudgetAgent)."""
import pytest
from core.shared_state import SharedState
from core.mcp_messages import MaterialPlan
from agents.budget_agent import BudgetAgent
from tools.budget_tool import estimate_budget

def test_estimate_budget_tool():
    """Verifica el cálculo base de la herramienta de presupuesto."""
    import json
    materiales = [{"material": "tela algodón", "cantidad": 100}, {"material": "hilo industrial", "cantidad": 5}]
    # Según materials_catalog.json (referencial)
    presupuesto = estimate_budget.invoke({"lista_materiales": json.dumps(materiales)})
    
    assert isinstance(presupuesto, str)
    assert "S/" in presupuesto

def test_budget_agent_estimation():
    """Verifica que el agente asigne los campos correctos al estado."""
    agent = BudgetAgent()
    state = SharedState()
    
    # Asignar un plan de materiales ficticio
    state.material_plan = MaterialPlan(
        pedido_id="BATCH-TEST",
        materiales=["tela algodón"],
        cantidades=[100]
    )
    
    # Ejecutar estimación
    result = agent.estimate(state)
    
    assert result is not None
    assert state.budget_result is not None
    assert result.presupuesto_estimado > 0
    assert result.proveedor_recomendado != ""
    assert result.estado == "Pendiente"
    assert "S/" in result.justificacion or len(result.justificacion) > 0
